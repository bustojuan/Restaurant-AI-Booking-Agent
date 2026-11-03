from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models import BookingRequest, BookingRestaurant, CallAttempt, Restaurant


def require_booking(session: Session, booking_id: str) -> BookingRequest:
    booking = session.get(BookingRequest, booking_id)
    if booking is None:
        raise DomainError("not_found", "Booking not found", 404)
    return booking


def require_restaurant(session: Session, restaurant_id: str) -> Restaurant:
    restaurant = session.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise DomainError("not_found", "Restaurant not found", 404)
    return restaurant


def queue(session: Session, booking_id: str) -> list[BookingRestaurant]:
    return list(
        session.scalars(
            select(BookingRestaurant)
            .where(BookingRestaurant.booking_id == booking_id)
            .order_by(BookingRestaurant.position)
        )
    )


def attempts(session: Session, booking_id: str) -> list[CallAttempt]:
    return list(
        session.scalars(
            select(CallAttempt).where(CallAttempt.booking_id == booking_id).order_by(CallAttempt.sequence)
        )
    )
