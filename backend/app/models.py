from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


def now() -> str:
    return datetime.now(UTC).isoformat()


class Base(DeclarativeBase):
    pass


class Restaurant(Base):
    __tablename__ = "restaurants"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str]
    external_id: Mapped[str]
    name: Mapped[str] = mapped_column(index=True)
    municipality: Mapped[str] = mapped_column(index=True)
    region: Mapped[str] = mapped_column(index=True)
    latitude: Mapped[float]
    longitude: Mapped[float]
    address: Mapped[str | None]
    postal_code: Mapped[str | None]
    country: Mapped[str] = mapped_column(default="ES")
    phone: Mapped[str | None]
    website_url: Mapped[str | None]
    cuisine_types: Mapped[list] = mapped_column(JSON, default=list)
    establishment_types: Mapped[list] = mapped_column(JSON, default=list)
    dietary_options: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    price_range: Mapped[int | None]
    rating: Mapped[float | None]
    review_count: Mapped[int | None]
    images: Mapped[list] = mapped_column(JSON, default=list)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[str] = mapped_column(default=now)
    __table_args__ = (
        UniqueConstraint("source", "external_id"),
        CheckConstraint("latitude >= -90 AND latitude <= 90"),
        CheckConstraint("longitude >= -180 AND longitude <= 180"),
    )


class FavoriteRestaurant(Base):
    __tablename__ = "favorite_restaurants"
    restaurant_id: Mapped[str] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[str] = mapped_column(default=now)


class BookingRequest(Base):
    __tablename__ = "booking_requests"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    status: Mapped[str] = mapped_column(default="DRAFT", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    scenario_id: Mapped[str | None] = mapped_column(ForeignKey("simulation_scenarios.id"))
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)
    started_at: Mapped[str | None]
    finished_at: Mapped[str | None]
    __table_args__ = (
        CheckConstraint("version >= 1"),
        CheckConstraint(
            "status IN ('DRAFT','READY','RUNNING','WAITING_FOR_USER','CONFIRMED',"
            "'EXHAUSTED','CANCELLED','FAILED')"
        ),
    )


class BookingRestaurant(Base):
    __tablename__ = "booking_restaurants"
    booking_id: Mapped[str] = mapped_column(
        ForeignKey("booking_requests.id", ondelete="CASCADE"), primary_key=True
    )
    restaurant_id: Mapped[str] = mapped_column(ForeignKey("restaurants.id"), primary_key=True)
    position: Mapped[int]
    __table_args__ = (UniqueConstraint("booking_id", "position"), CheckConstraint("position >= 0"))


class CallAttempt(Base):
    __tablename__ = "call_attempts"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("booking_requests.id", ondelete="CASCADE"), index=True)
    restaurant_id: Mapped[str] = mapped_column(ForeignKey("restaurants.id"))
    sequence: Mapped[int]
    status: Mapped[str]
    result: Mapped[str | None]
    started_at: Mapped[str] = mapped_column(default=now)
    completed_at: Mapped[str | None]
    duration_ms: Mapped[int | None]
    __table_args__ = (
        UniqueConstraint("booking_id", "restaurant_id"),
        UniqueConstraint("booking_id", "sequence"),
    )


class ReservationOffer(Base):
    __tablename__ = "reservation_offers"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("booking_requests.id", ondelete="CASCADE"), index=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempts.id", ondelete="CASCADE"))
    details: Mapped[dict] = mapped_column(JSON)
    evaluation: Mapped[str]
    decision: Mapped[str | None]
    approval_pending: Mapped[bool] = mapped_column(default=False)
    provider_confirmation_expected: Mapped[bool] = mapped_column(default=False)


class ReservationConfirmation(Base):
    __tablename__ = "reservation_confirmations"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(
        ForeignKey("booking_requests.id", ondelete="CASCADE"), unique=True
    )
    restaurant_id: Mapped[str] = mapped_column(ForeignKey("restaurants.id"))
    attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempts.id", ondelete="CASCADE"))
    reference: Mapped[str | None]
    details: Mapped[dict] = mapped_column(JSON)
    simulated: Mapped[bool] = mapped_column(default=True)
    confirmed_at: Mapped[str] = mapped_column(default=now)


class BookingEvent(Base):
    __tablename__ = "booking_events"
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booking_id: Mapped[str] = mapped_column(ForeignKey("booking_requests.id", ondelete="CASCADE"))
    event_type: Mapped[str]
    schema_version: Mapped[int] = mapped_column(default=1)
    timestamp: Mapped[str] = mapped_column(default=now)
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        Index("ix_events_booking_cursor", "booking_id", "event_id"),
        {"sqlite_autoincrement": True},
    )


class SimulationScenario(Base):
    __tablename__ = "simulation_scenarios"
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    outcomes: Mapped[list] = mapped_column(JSON)


class WorkspaceState(Base):
    __tablename__ = "workspace_state"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    active_draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("booking_requests.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (CheckConstraint("id = 1"),)
