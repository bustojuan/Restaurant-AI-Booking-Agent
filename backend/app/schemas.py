from datetime import UTC, date, datetime, time
from enum import StrEnum
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, create_model, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, allow_inf_nan=False)


class BookingStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    CONFIRMED = "CONFIRMED"
    EXHAUSTED = "EXHAUSTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class AttemptStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class AttemptResult(StrEnum):
    NO_AVAILABILITY = "NO_AVAILABILITY"
    INCOMPATIBLE_OFFER = "INCOMPATIBLE_OFFER"
    OFFER_ACCEPTABLE = "OFFER_ACCEPTABLE"
    USER_APPROVAL_REQUIRED = "USER_APPROVAL_REQUIRED"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    DECLINED = "DECLINED"
    CONFIRMED = "CONFIRMED"
    NOT_CONFIRMED = "NOT_CONFIRMED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"
    DECLINED_AI = "DECLINED_AI"
    DISCONNECTED = "DISCONNECTED"
    AMBIGUOUS = "AMBIGUOUS"
    UNCERTAIN = "UNCERTAIN"


class ImageAsset(Contract):
    url: HttpUrl
    source: str = Field(min_length=1)
    source_page_url: HttpUrl
    attribution: str = Field(min_length=1)
    creator: str = Field(min_length=1)
    license: Literal["CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "OWNER_PERMISSION"]
    license_url: HttpUrl
    rights_evidence_url: HttpUrl
    rights_verified: Literal[True]


class RestaurantOut(Contract):
    id: str
    source: str
    external_id: str
    name: str
    municipality: str
    region: str
    latitude: float
    longitude: float
    address: str | None
    postal_code: str | None
    country: str
    phone: str | None
    website_url: HttpUrl | None
    cuisine_types: list[str]
    establishment_types: list[str]
    dietary_options: list[str] = Field(
        default_factory=list,
        description="Menu options declared by the data source, not verified allergy safety",
    )
    source_url: HttpUrl | None = None
    data_attribution: str | None = None
    data_license_url: HttpUrl | None = None
    price_range: int | None
    rating: float | None
    review_count: int | None
    primary_image_url: HttpUrl | None
    additional_images: list[ImageAsset]
    images: list[ImageAsset]
    has_photo: bool
    is_favorite: bool
    is_simulated: bool
    distance_km: float | None = None
    selected_position: int | None = None
    updated_at: str


class RestaurantPage(Contract):
    items: list[RestaurantOut]
    total: int
    limit: int
    offset: int


class Category(Contract):
    id: str
    label: str


class CategoryCatalog(Contract):
    cuisine_types: list[Category]
    establishment_types: list[Category]
    dietary_options: list[Category] = Field(default_factory=list)


class DietaryRequirement(Contract):
    kind: Literal["celiac", "allergy", "intolerance", "diet", "other"]
    code: str = Field(min_length=1, max_length=80)
    instructions: str = Field(default="", max_length=500)
    mandatory: bool = True


class Requirement(Contract):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")
    value: str | bool | float
    mandatory: bool = True


class BookingConfiguration(Contract):
    customer_name: str | None = Field(default=None, min_length=1, max_length=120)
    contact_phone: str | None = Field(default=None, min_length=5, max_length=30)
    requested_date: date | None = None
    preferred_time: time | None = None
    adults: int = Field(default=2, ge=1, le=100)
    children: int = Field(default=0, ge=0, le=100)
    high_chairs: int = Field(default=0, ge=0, le=100)
    flexibility_minutes: int = Field(default=0, ge=0, le=240)
    area: str | None = Field(default=None, max_length=200)
    budget_per_person: float | None = Field(default=None, gt=0, le=10000)
    strict_budget: bool = False
    table_type: Literal["indifferent", "inside", "terrace"] = "indifferent"
    table_type_mandatory: bool = False
    accessibility_required: bool = False
    stroller_space: bool = False
    special_occasion: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    dietary_requirements: list[DietaryRequirement] = Field(default_factory=list, max_length=40)
    requirements: list[Requirement] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def coherent(self):
        if self.high_chairs > self.children:
            raise ValueError("high_chairs cannot exceed children")
        if self.strict_budget and self.budget_per_person is None:
            raise ValueError("strict_budget requires budget_per_person")
        if self.preferred_time and self.preferred_time.tzinfo:
            raise ValueError("preferred_time must be a local Europe/Madrid time without offset")
        keys = [r.key for r in self.requirements]
        codes = [r.code for r in self.dietary_requirements]
        if len(set(keys)) != len(keys) or len(set(codes)) != len(codes):
            raise ValueError("Requirement keys and dietary codes must be unique")
        return self

    @property
    def party_size(self) -> int:
        return self.adults + self.children

    def validate_start(self) -> None:
        if not all((self.customer_name, self.contact_phone, self.requested_date, self.preferred_time)):
            raise ValueError("Name, phone, date and preferred_time are required to start")
        local = datetime.combine(self.requested_date, self.preferred_time)
        zone = ZoneInfo("Europe/Madrid")
        aware = local.replace(tzinfo=zone)
        if aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != local:
            raise ValueError("Requested local time does not exist due to daylight saving time")
        if aware.utcoffset() != local.replace(tzinfo=zone, fold=1).utcoffset():
            raise ValueError("Requested local time is ambiguous due to daylight saving time")
        if aware <= datetime.now(UTC):
            raise ValueError("Requested date/time must be in the future")

    def mandatory_keys(self) -> set[str]:
        keys = {f"dietary:{r.code}" for r in self.dietary_requirements if r.mandatory}
        keys |= {f"requirement:{r.key}" for r in self.requirements if r.mandatory}
        if self.accessibility_required:
            keys.add("accessibility")
        if self.stroller_space:
            keys.add("stroller_space")
        if self.high_chairs:
            keys.add("high_chairs")
        return keys


class BookingCreate(Contract):
    configuration: BookingConfiguration = Field(default_factory=BookingConfiguration)
    restaurant_ids: list[str] = Field(default_factory=list, max_length=100)


BookingConfigurationPatch = create_model(
    "BookingConfigurationPatch",
    __base__=Contract,
    **{
        name: (
            (
                Annotated[field.annotation | None, *field.metadata]
                if field.metadata
                else field.annotation | None
            ),
            None,
        )
        for name, field in BookingConfiguration.model_fields.items()
    },
)


class BookingPatch(Contract):
    configuration: BookingConfigurationPatch


class QueueInsert(Contract):
    restaurant_id: str
    position: int | None = Field(
        default=None, ge=0, description="Zero-based insertion index; omitted = append"
    )


class QueueOrder(Contract):
    restaurant_ids: list[str] = Field(max_length=100)


class QueueEntry(Contract):
    position: int
    restaurant: RestaurantOut


class AttemptOut(Contract):
    id: str
    restaurant_id: str
    restaurant_name: str
    sequence: int
    status: AttemptStatus
    result: AttemptResult | None
    started_at: str
    completed_at: str | None
    duration_ms: int | None


class OfferDetails(Contract):
    requested_date: date
    time: time
    party_size: int
    table_type: Literal["indifferent", "inside", "terrace"]
    price_per_person: float | None = None
    deposit: float = Field(default=0, ge=0)
    financial_conditions: list[str] = Field(default_factory=list, max_length=20)
    verified_requirements: dict[str, bool] = Field(default_factory=dict)


class OfferOut(Contract):
    id: str
    booking_id: str
    attempt_id: str
    details: OfferDetails
    evaluation: Literal["ACCEPTABLE", "UNACCEPTABLE", "REQUIRES_USER_APPROVAL", "INSUFFICIENT_INFORMATION"]
    decision: Literal["APPROVED", "REJECTED"] | None
    approval_pending: bool


class ConfirmationOut(Contract):
    id: str
    booking_id: str
    restaurant_id: str
    attempt_id: str
    reference: str | None
    details: OfferDetails
    simulated: bool
    confirmed_at: str


class RestaurantRef(Contract):
    id: str
    name: str
    position: int


class BookingSummary(Contract):
    id: str
    status: BookingStatus
    version: int
    requested_date: date | None
    preferred_time: time | None
    timezone: Literal["Europe/Madrid"] = "Europe/Madrid"
    party_size: int
    current_restaurant: RestaurantRef | None
    current_call_status: AttemptStatus | None
    contacted_restaurants: list[AttemptOut]
    pending_restaurants: list[RestaurantRef]
    total_restaurants: int
    completed_attempts: int
    pending_approvals: list[OfferOut]
    confirmation: ConfirmationOut | None
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None


class BookingDetail(Contract):
    id: str
    status: BookingStatus
    version: int
    configuration: BookingConfiguration
    restaurants: list[QueueEntry]
    summary: BookingSummary


class BookingPage(Contract):
    items: list[BookingSummary]
    total: int
    limit: int
    offset: int


class EventPayload(Contract):
    summary: BookingSummary
    activity: "AgentActivity | None" = None


class AgentActivity(Contract):
    trace_id: int
    execution_id: str
    agent: Literal[
        "supervisor", "planning", "research", "voice", "negotiation", "verification", "memory", "evaluation"
    ]
    phase: Literal["started", "completed", "failed"]
    tool: str | None
    elapsed_ms: int | None


class EventOut(Contract):
    event_id: int
    event_type: Literal[
        "booking.created",
        "booking.updated",
        "restaurant.selected",
        "booking.started",
        "call.started",
        "call.completed",
        "alternative.proposed",
        "user.approval_required",
        "user.decision_received",
        "booking.confirmed",
        "booking.exhausted",
        "booking.cancelled",
        "booking.failed",
        "agent.activity",
    ]
    schema_version: Literal[1]
    booking_id: str
    timestamp: str
    payload: EventPayload


class EventPage(Contract):
    items: list[EventOut]
    next_after_event_id: int
    has_more: bool


class CallAuthorization(Contract):
    explicit_authorization: Literal[True]
    own_test_numbers_only: Literal[True]
    audio_processing_consent: Literal[True]
    max_calls: int = Field(ge=1, le=10)
    max_duration_seconds: int = Field(ge=10, le=600)
    max_estimated_cost_eur: float = Field(gt=0, le=100)
    expires_at: datetime


class StartRequest(Contract):
    scenario_id: str = "priority-success"
    mode: Literal["simulation", "ai_simulation", "real_telephony"] = "simulation"
    call_authorization: CallAuthorization | None = None


class UserDecision(Contract):
    offer_id: str
    approve: bool


class FavoriteInput(Contract):
    restaurant_id: str


class WorkspaceUpdate(Contract):
    active_draft_id: str | None


class WorkspaceOut(WorkspaceUpdate):
    version: int


class ScenarioOut(Contract):
    id: str
    name: str
    outcomes: list[str]


class ErrorDetail(Contract):
    code: str
    message: str


class ErrorResponse(Contract):
    error: ErrorDetail
