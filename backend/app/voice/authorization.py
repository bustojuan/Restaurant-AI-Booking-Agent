import re
from datetime import UTC, datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from app.core.errors import DomainError
from app.repositories import queue, require_restaurant


def estimated_call_cost(settings, seconds: int) -> float:
    rates = (
        settings.telephony_cost_per_minute,
        settings.live_cost_per_minute,
        settings.reasoning_reserved_cost_per_call,
    )
    if any(value is None for value in rates):
        raise DomainError(
            "cost_limits_unconfigured",
            "Configure conservative voice, telephony and reasoning cost limits",
            422,
        )
    return (rates[0] + rates[1]) * seconds / 60 + rates[2]


def validate_authorization(session, booking, authorization, settings, *, at: datetime | None = None):
    if not settings.real_telephony_enabled:
        raise DomainError("real_telephony_disabled", "Real telephony is disabled", 403)
    if not authorization:
        raise DomainError("call_authorization_required", "Explicit call authorization is required", 422)
    current = at or datetime.now(UTC)
    if authorization.expires_at.tzinfo is None or authorization.expires_at <= current:
        raise DomainError(
            "authorization_expired", "Call authorization must have a future timezone-aware expiry", 422
        )
    if not all(
        (
            settings.openai_api_key,
            settings.twilio_account_sid,
            settings.twilio_auth_token,
            settings.twilio_phone_number,
        )
    ):
        raise DomainError("credentials_missing", "Voice and telephony credentials are required", 422)
    if not re.fullmatch(r"AC[0-9a-fA-F]{32}", settings.twilio_account_sid):
        raise DomainError("invalid_account", "Invalid Twilio account SID", 422)
    parsed = urlsplit(settings.telephony_public_origin or "")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username
    ):
        raise DomainError(
            "invalid_public_origin", "Configure an HTTPS public origin for the isolated voice gateway", 422
        )
    local_hour = current.astimezone(ZoneInfo("Europe/Madrid")).hour
    if not settings.telephony_start_hour <= local_hour < settings.telephony_end_hour:
        raise DomainError(
            "outside_calling_hours", "Current time is outside the configured calling hours", 403
        )
    rows = queue(session, booking.id)
    if len(rows) > authorization.max_calls or authorization.max_duration_seconds > settings.voice_max_seconds:
        raise DomainError("call_limit_exceeded", "Queue or duration exceeds the authorized limits", 422)
    for phone in [
        settings.twilio_phone_number,
        *[require_restaurant(session, row.restaurant_id).phone for row in rows],
    ]:
        if not phone or not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
            raise DomainError("invalid_phone", "Every phone must use valid E.164 format", 422)
    if any(
        require_restaurant(session, row.restaurant_id).phone not in settings.telephony_allowed_numbers
        for row in rows
    ):
        raise DomainError(
            "phone_not_authorized", "Only explicitly allowlisted own test numbers may be called", 403
        )
    if (
        estimated_call_cost(settings, authorization.max_duration_seconds) * len(rows)
        > authorization.max_estimated_cost_eur
    ):
        raise DomainError(
            "budget_exceeded", "Conservative reserved cost exceeds the authorized estimated budget", 422
        )
