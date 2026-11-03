from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models import (
    BookingEvent,
    BookingRequest,
    BookingRestaurant,
    ReservationConfirmation,
    ReservationOffer,
    WorkspaceState,
    now,
)
from app.repositories import attempts, queue, require_booking, require_restaurant
from app.schemas import (
    AttemptOut,
    BookingConfiguration,
    BookingCreate,
    BookingDetail,
    BookingPage,
    BookingSummary,
    ConfirmationOut,
    EventOut,
    EventPage,
    OfferOut,
    QueueEntry,
    RestaurantRef,
)
from app.services.restaurants import favorite_ids, restaurant_out


def check_version(booking: BookingRequest | WorkspaceState, expected_version: int) -> None:
    if booking.version != expected_version:
        raise DomainError("version_conflict", "Resource changed; reload it before applying your edits")


def editable(booking: BookingRequest) -> None:
    if booking.status != "DRAFT":
        raise DomainError("booking_not_editable", "Only drafts can be edited")


def attempt_out(session: Session, attempt) -> AttemptOut:
    return AttemptOut.model_validate(
        {
            **{k: getattr(attempt, k) for k in AttemptOut.model_fields if hasattr(attempt, k)},
            "restaurant_name": require_restaurant(session, attempt.restaurant_id).name,
        }
    )


def summary(session: Session, booking: BookingRequest) -> BookingSummary:
    rows = queue(session, booking.id)
    refs = {
        row.restaurant_id: RestaurantRef(
            id=row.restaurant_id,
            name=require_restaurant(session, row.restaurant_id).name,
            position=row.position,
        )
        for row in rows
    }
    calls = attempts(session, booking.id)
    offers = session.scalars(
        select(ReservationOffer)
        .where(ReservationOffer.booking_id == booking.id, ReservationOffer.approval_pending.is_(True))
        .order_by(ReservationOffer.id)
    ).all()
    current = next((call for call in calls if call.status == "RUNNING"), None)
    if current is None and booking.status == "WAITING_FOR_USER" and offers:
        current = next((call for call in calls if call.id == offers[0].attempt_id), None)
    contacted = {call.restaurant_id for call in calls}
    confirmation = session.scalar(
        select(ReservationConfirmation).where(ReservationConfirmation.booking_id == booking.id)
    )
    config = BookingConfiguration.model_validate(booking.configuration)
    return BookingSummary(
        id=booking.id,
        status=booking.status,
        version=booking.version,
        requested_date=config.requested_date,
        preferred_time=config.preferred_time,
        party_size=config.party_size,
        current_restaurant=refs.get(current.restaurant_id) if current else None,
        current_call_status=current.status if current else None,
        contacted_restaurants=[attempt_out(session, call) for call in calls],
        pending_restaurants=[ref for rid, ref in refs.items() if rid not in contacted],
        total_restaurants=len(rows),
        completed_attempts=sum(call.completed_at is not None for call in calls),
        pending_approvals=[OfferOut.model_validate(offer) for offer in offers],
        confirmation=ConfirmationOut.model_validate(confirmation) if confirmation else None,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
        started_at=booking.started_at,
        finished_at=booking.finished_at,
    )


def detail(session: Session, booking: BookingRequest) -> BookingDetail:
    favorites = favorite_ids(session)
    return BookingDetail(
        id=booking.id,
        status=booking.status,
        version=booking.version,
        configuration=BookingConfiguration.model_validate(booking.configuration),
        restaurants=[
            QueueEntry(
                position=row.position,
                restaurant=restaurant_out(
                    require_restaurant(session, row.restaurant_id),
                    favorites,
                    row.position,
                ),
            )
            for row in queue(session, booking.id)
        ],
        summary=summary(session, booking),
    )


def emit(
    session: Session,
    booking: BookingRequest,
    event_type: str,
    *,
    bump: bool = True,
    activity: dict | None = None,
) -> None:
    if bump:
        booking.version += 1
    booking.updated_at = now()
    session.flush()
    snapshot = summary(session, booking)
    event = BookingEvent(
        booking_id=booking.id,
        event_type=event_type,
        payload={
            "summary": snapshot.model_dump(mode="json"),
            **({"activity": activity} if activity else {}),
        },
    )
    session.add(event)
    session.flush()
    from app.observability.recorder import record_business

    record_business(session, booking, event_type, event.event_id)


def validate_ids(session: Session, ids: list[str]) -> None:
    if len(ids) != len(set(ids)):
        raise DomainError("duplicate_restaurant", "Restaurant IDs must be unique", 422)
    if len(ids) > 100:
        raise DomainError("queue_limit", "A queue can contain at most 100 restaurants", 422)
    for restaurant_id in ids:
        require_restaurant(session, restaurant_id)


def replace_queue(session: Session, booking_id: str, ids: list[str]) -> None:
    # Delete and reinsert within the SAME locked transaction. Readers see the old or new order.
    session.execute(delete(BookingRestaurant).where(BookingRestaurant.booking_id == booking_id))
    session.flush()
    session.add_all(
        [
            BookingRestaurant(booking_id=booking_id, restaurant_id=rid, position=position)
            for position, rid in enumerate(ids)
        ]
    )
    session.flush()


def create_booking(session: Session, payload: BookingCreate) -> BookingDetail:
    validate_ids(session, payload.restaurant_ids)
    booking = BookingRequest(configuration=payload.configuration.model_dump(mode="json"))
    session.add(booking)
    session.flush()
    replace_queue(session, booking.id, payload.restaurant_ids)
    emit(session, booking, "booking.created", bump=False)
    return detail(session, booking)


def patch_booking(session: Session, booking_id: str, expected: int, changes: dict) -> BookingDetail:
    booking = require_booking(session, booking_id)
    check_version(booking, expected)
    editable(booking)
    try:
        configuration = BookingConfiguration.model_validate({**booking.configuration, **changes})
    except ValidationError:
        raise DomainError("invalid_configuration", "Invalid booking configuration", 422) from None
    booking.configuration = configuration.model_dump(mode="json")
    emit(session, booking, "booking.updated")
    return detail(session, booking)


def modify_queue(
    session: Session,
    booking_id: str,
    expected: int,
    *,
    add: str | None = None,
    position: int | None = None,
    order: list[str] | None = None,
    remove: str | None = None,
) -> BookingDetail:
    booking = require_booking(session, booking_id)
    check_version(booking, expected)
    editable(booking)
    ids = [row.restaurant_id for row in queue(session, booking_id)]
    if add is not None:
        require_restaurant(session, add)
        if add in ids:
            raise DomainError("duplicate_restaurant", "Restaurant is already in this queue")
        if position is not None and position > len(ids):
            raise DomainError("invalid_position", "Insertion position exceeds queue length", 422)
        ids.insert(len(ids) if position is None else position, add)
    elif remove is not None:
        if remove not in ids:
            raise DomainError("not_found", "Restaurant is not in this queue", 404)
        ids.remove(remove)
    elif order is not None:
        if len(order) != len(set(order)) or set(order) != set(ids):
            raise DomainError(
                "invalid_order", "Order must contain every selected restaurant exactly once", 422
            )
        ids = order
    validate_ids(session, ids)
    replace_queue(session, booking_id, ids)
    emit(session, booking, "restaurant.selected" if add is not None else "booking.updated")
    return detail(session, booking)


def delete_booking(session: Session, booking_id: str, expected: int) -> None:
    booking = require_booking(session, booking_id)
    check_version(booking, expected)
    editable(booking)
    workspace = session.get(WorkspaceState, 1)
    if workspace and workspace.active_draft_id == booking_id:
        workspace.active_draft_id = None
        workspace.version += 1
        session.flush()
    session.delete(booking)


def list_bookings(session: Session, statuses: list[str] | None, limit: int, offset: int) -> BookingPage:
    query = select(BookingRequest)
    if statuses:
        query = query.where(BookingRequest.status.in_(statuses))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    bookings = session.scalars(
        query.order_by(BookingRequest.updated_at.desc(), BookingRequest.id).offset(offset).limit(limit)
    ).all()
    return BookingPage(items=[summary(session, b) for b in bookings], total=total, limit=limit, offset=offset)


def event_page(session: Session, booking_id: str, after: int, limit: int) -> EventPage:
    require_booking(session, booking_id)
    events = session.scalars(
        select(BookingEvent)
        .where(
            BookingEvent.booking_id == booking_id,
            BookingEvent.event_id > after,
        )
        .order_by(BookingEvent.event_id)
        .limit(limit + 1)
    ).all()
    page = events[:limit]
    return EventPage(
        items=[EventOut.model_validate(event) for event in page],
        next_after_event_id=page[-1].event_id if page else after,
        has_more=len(events) > limit,
    )
