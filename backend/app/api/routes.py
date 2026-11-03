import asyncio
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.api.dependencies import Version, authenticate
from app.core.errors import DomainError
from app.models import BookingEvent, FavoriteRestaurant, ReservationOffer, SimulationScenario, WorkspaceState
from app.providers.restaurants import category_catalog
from app.repositories import require_booking, require_restaurant
from app.schemas import (
    BookingCreate,
    BookingDetail,
    BookingPage,
    BookingPatch,
    BookingStatus,
    BookingSummary,
    CategoryCatalog,
    EventOut,
    EventPage,
    FavoriteInput,
    OfferOut,
    QueueInsert,
    QueueOrder,
    RestaurantOut,
    RestaurantPage,
    ScenarioOut,
    StartRequest,
    UserDecision,
    WorkspaceOut,
    WorkspaceUpdate,
)
from app.services import bookings, execution, restaurants

router = APIRouter(prefix="/api", dependencies=[Depends(authenticate)])
ws_router = APIRouter(prefix="/api")
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


@router.get("/restaurants/categories", response_model=CategoryCatalog, tags=["Restaurants"])
def categories():
    return category_catalog()


@router.get("/restaurants", response_model=RestaurantPage, tags=["Restaurants"])
def search_restaurants(
    request: Request,
    q: str | None = Query(default=None, max_length=200),
    municipality: str | None = Query(default=None, max_length=200),
    region: Literal["Madrid", "Navarra"] | None = None,
    cuisine_types: Annotated[list[str] | None, Query()] = None,
    establishment_types: Annotated[list[str] | None, Query()] = None,
    favorites_only: bool = False,
    bbox: str | None = Query(default=None, description="west,south,east,north in longitude,latitude (WGS84)"),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float | None = Query(default=None, gt=0, le=200),
    min_rating: float | None = Query(default=None, ge=0, le=5),
    max_price: int | None = Query(default=None, ge=1, le=4),
    sort: Literal["name", "distance", "rating", "price"] = "name",
    limit: Limit = 50,
    offset: Offset = 0,
    booking_id: str | None = None,
    catalog: Literal["all", "real", "simulated", "auto"] = "all",
    cuisine_group: Literal["asian"] | None = None,
    dietary_options: Annotated[list[str] | None, Query()] = None,
):
    bounds = None
    if bbox:
        try:
            west, south, east, north = [float(v) for v in bbox.split(",")]
            if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
                raise ValueError
            bounds = west, south, east, north
        except ValueError:
            raise DomainError(
                "invalid_bbox", "Use west,south,east,north with valid WGS84 bounds", 422
            ) from None
    if (latitude is None) != (longitude is None):
        raise DomainError("invalid_coordinates", "Latitude and longitude must be provided together", 422)
    if (radius_km is not None or sort == "distance") and latitude is None:
        raise DomainError("coordinates_required", "Radius and distance sorting require coordinates", 422)
    with request.app.state.db.transaction() as session:
        if booking_id:
            require_booking(session, booking_id)
        return restaurants.search(
            session,
            q=q,
            municipality=municipality,
            region=region,
            cuisine_types=cuisine_types,
            establishment_types=establishment_types,
            favorites_only=favorites_only,
            bbox=bounds,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            min_rating=min_rating,
            max_price=max_price,
            sort=sort,
            limit=limit,
            offset=offset,
            booking_id=booking_id,
            catalog=catalog,
            cuisine_group=cuisine_group,
            dietary_options=dietary_options,
        )


@router.get("/restaurants/{restaurant_id}", response_model=RestaurantOut, tags=["Restaurants"])
def restaurant_detail(request: Request, restaurant_id: str):
    with request.app.state.db.transaction() as session:
        return restaurants.restaurant_out(
            require_restaurant(session, restaurant_id), restaurants.favorite_ids(session)
        )


@router.get("/favorites", response_model=RestaurantPage, tags=["Favorites"])
def favorites(request: Request, limit: Limit = 50, offset: Offset = 0):
    with request.app.state.db.transaction() as session:
        return restaurants.search(session, favorites_only=True, limit=limit, offset=offset)


@router.post("/favorites", response_model=RestaurantOut, tags=["Favorites"])
def add_favorite(request: Request, payload: FavoriteInput):
    with request.app.state.db.transaction(write=True) as session:
        restaurant = require_restaurant(session, payload.restaurant_id)
        if session.get(FavoriteRestaurant, payload.restaurant_id) is None:
            session.add(FavoriteRestaurant(restaurant_id=payload.restaurant_id))
            session.flush()
        return restaurants.restaurant_out(restaurant, restaurants.favorite_ids(session))


@router.delete("/favorites/{restaurant_id}", status_code=204, tags=["Favorites"])
def remove_favorite(request: Request, restaurant_id: str):
    with request.app.state.db.transaction(write=True) as session:
        favorite = session.get(FavoriteRestaurant, restaurant_id)
        if favorite:
            session.delete(favorite)


@router.get("/bookings", response_model=BookingPage, tags=["Bookings"])
def list_bookings(
    request: Request,
    status: Annotated[list[BookingStatus] | None, Query()] = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    with request.app.state.db.transaction() as session:
        return bookings.list_bookings(session, status, limit, offset)


@router.post("/bookings", response_model=BookingDetail, status_code=201, tags=["Bookings"])
def create_booking(request: Request, response: Response, payload: BookingCreate):
    with request.app.state.db.transaction(write=True) as session:
        result = bookings.create_booking(session, payload)
        etag(response, result.version)
        return result


@router.get("/bookings/{booking_id}", response_model=BookingDetail, tags=["Bookings"])
def booking_detail(request: Request, response: Response, booking_id: str):
    with request.app.state.db.transaction() as session:
        result = bookings.detail(session, require_booking(session, booking_id))
        etag(response, result.version)
        return result


@router.patch("/bookings/{booking_id}", response_model=BookingDetail, tags=["Bookings"])
def patch_booking(
    request: Request, response: Response, booking_id: str, payload: BookingPatch, version: Version
):
    with request.app.state.db.transaction(write=True) as session:
        result = bookings.patch_booking(
            session, booking_id, version, payload.configuration.model_dump(mode="json", exclude_unset=True)
        )
        etag(response, result.version)
        return result


@router.delete("/bookings/{booking_id}", status_code=204, tags=["Bookings"])
def delete_booking(request: Request, booking_id: str, version: Version):
    with request.app.state.db.transaction(write=True) as session:
        bookings.delete_booking(session, booking_id, version)


@router.post("/bookings/{booking_id}/restaurants", response_model=BookingDetail, tags=["Queue"])
def insert_restaurant(
    request: Request, response: Response, booking_id: str, payload: QueueInsert, version: Version
):
    with request.app.state.db.transaction(write=True) as session:
        result = bookings.modify_queue(
            session, booking_id, version, add=payload.restaurant_id, position=payload.position
        )
        etag(response, result.version)
        return result


@router.put("/bookings/{booking_id}/restaurants/order", response_model=BookingDetail, tags=["Queue"])
def reorder(request: Request, response: Response, booking_id: str, payload: QueueOrder, version: Version):
    with request.app.state.db.transaction(write=True) as session:
        result = bookings.modify_queue(session, booking_id, version, order=payload.restaurant_ids)
        etag(response, result.version)
        return result


@router.delete(
    "/bookings/{booking_id}/restaurants/{restaurant_id}", response_model=BookingDetail, tags=["Queue"]
)
def remove_restaurant(
    request: Request, response: Response, booking_id: str, restaurant_id: str, version: Version
):
    with request.app.state.db.transaction(write=True) as session:
        result = bookings.modify_queue(session, booking_id, version, remove=restaurant_id)
        etag(response, result.version)
        return result


@router.post("/bookings/{booking_id}/start", response_model=BookingSummary, tags=["Execution"])
def start(request: Request, response: Response, booking_id: str, payload: StartRequest, version: Version):
    with request.app.state.db.transaction(write=True) as session:
        result = execution.start(
            session,
            booking_id,
            version,
            payload.scenario_id,
            mode=payload.mode,
            authorization=payload.call_authorization,
            settings=request.app.state.settings,
        )
        etag(response, result.version)
        return result


@router.post("/bookings/{booking_id}/cancel", response_model=BookingSummary, tags=["Execution"])
def cancel(request: Request, response: Response, booking_id: str, version: Version):
    with request.app.state.db.transaction(write=True) as session:
        result = execution.cancel(session, booking_id, version)
        etag(response, result.version)
        return result


@router.post("/bookings/{booking_id}/decisions", response_model=BookingSummary, tags=["Execution"])
def decide(request: Request, response: Response, booking_id: str, payload: UserDecision, version: Version):
    with request.app.state.db.transaction(write=True) as session:
        result = execution.decide(session, booking_id, version, payload.offer_id, payload.approve)
        etag(response, result.version)
        return result


@router.get("/bookings/{booking_id}/offers", response_model=list[OfferOut], tags=["Execution"])
def offers(request: Request, booking_id: str):
    with request.app.state.db.transaction() as session:
        require_booking(session, booking_id)
        return [
            OfferOut.model_validate(offer)
            for offer in session.scalars(
                select(ReservationOffer)
                .where(ReservationOffer.booking_id == booking_id)
                .order_by(ReservationOffer.id)
            )
        ]


@router.get("/bookings/{booking_id}/events", response_model=EventPage, tags=["Events"])
def events(
    request: Request, booking_id: str, after_event_id: int = Query(default=0, ge=0), limit: Limit = 50
):
    with request.app.state.db.transaction() as session:
        return bookings.event_page(session, booking_id, after_event_id, limit)


@router.get("/simulations/scenarios", response_model=list[ScenarioOut], tags=["Simulations"])
def scenarios(request: Request):
    with request.app.state.db.transaction() as session:
        return [
            ScenarioOut.model_validate(s)
            for s in session.scalars(select(SimulationScenario).order_by(SimulationScenario.id))
        ]


@router.get("/workspace", response_model=WorkspaceOut, tags=["Workspace"])
def workspace(request: Request, response: Response):
    with request.app.state.db.transaction() as session:
        result = WorkspaceOut.model_validate(session.get(WorkspaceState, 1))
        etag(response, result.version)
        return result


@router.put("/workspace", response_model=WorkspaceOut, tags=["Workspace"])
def update_workspace(request: Request, response: Response, payload: WorkspaceUpdate, version: Version):
    with request.app.state.db.transaction(write=True) as session:
        state = session.get(WorkspaceState, 1)
        bookings.check_version(state, version)
        if payload.active_draft_id:
            bookings.editable(require_booking(session, payload.active_draft_id))
        state.active_draft_id, state.version = payload.active_draft_id, state.version + 1
        session.flush()
        result = WorkspaceOut.model_validate(state)
        etag(response, result.version)
        return result


@ws_router.websocket("/events/ws", name="booking_events")
async def stream_events(
    websocket: WebSocket, after_event_id: int = Query(default=0, ge=0), booking_id: str | None = None
):
    settings = websocket.app.state.settings
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        if (
            not isinstance(auth, dict)
            or not isinstance(auth.get("token"), str)
            or not secrets.compare_digest(
                auth["token"].encode(), settings.local_api_token.get_secret_value().encode()
            )
        ):
            await websocket.close(code=1008)
            return
        if booking_id:

            def check_booking():
                with websocket.app.state.db.transaction() as session:
                    require_booking(session, booking_id)

            await asyncio.to_thread(check_booking)
        cursor = after_event_id

        def read_page(after):
            with websocket.app.state.db.transaction() as session:
                statement = select(BookingEvent).where(BookingEvent.event_id > after)
                if booking_id:
                    statement = statement.where(BookingEvent.booking_id == booking_id)
                return [
                    EventOut.model_validate(event)
                    for event in session.scalars(statement.order_by(BookingEvent.event_id).limit(100))
                ]

        while True:
            page = await asyncio.to_thread(read_page, cursor)
            for event in page:
                await websocket.send_json(event.model_dump(mode="json"))
                cursor = event.event_id
            if len(page) == 100:
                continue
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=0.1)
                if message["type"] == "websocket.disconnect":
                    return
            except TimeoutError:
                continue
    except (WebSocketDisconnect, RuntimeError):
        return
    except (TimeoutError, ValueError, DomainError):
        await websocket.close(code=1008)
