"""Configuration-only readiness report. No network, audio, credentials or numbers returned."""

import re
from urllib.parse import urlsplit

from app.core.config import Settings


def readiness(settings: Settings) -> dict:
    public = urlsplit(settings.telephony_public_origin or "")
    phone = r"\+[1-9]\d{7,14}"
    audio = {
        "OPENAI_API_KEY": bool(settings.openai_api_key),
        "VOICE_SANDBOX_ENABLED": settings.voice_sandbox_enabled,
    }
    telephony = {
        "OPENAI_API_KEY": bool(settings.openai_api_key),
        "REAL_TELEPHONY_ENABLED": settings.real_telephony_enabled,
        "TWILIO_ACCOUNT_SID": bool(re.fullmatch(r"AC[0-9a-fA-F]{32}", settings.twilio_account_sid or "")),
        "TWILIO_AUTH_TOKEN": bool(settings.twilio_auth_token),
        "TWILIO_PHONE_NUMBER": bool(re.fullmatch(phone, settings.twilio_phone_number or "")),
        "TELEPHONY_ALLOWED_NUMBERS": len(settings.telephony_allowed_numbers) == 1
        and all(re.fullmatch(phone, n) for n in settings.telephony_allowed_numbers),
        "TELEPHONY_PUBLIC_ORIGIN": bool(
            public.scheme == "https"
            and public.hostname
            and public.path in {"", "/"}
            and not any([public.username, public.password, public.query, public.fragment])
        ),
        "TELEPHONY_COST_PER_MINUTE": bool(settings.telephony_cost_per_minute),
        "LIVE_COST_PER_MINUTE": bool(settings.live_cost_per_minute),
        "REASONING_RESERVED_COST_PER_CALL": bool(settings.reasoning_reserved_cost_per_call),
        "CALLING_HOURS_VALID": settings.telephony_start_hour < settings.telephony_end_hour,
    }
    return {
        "audio": {
            "configuration_ready": all(audio.values()),
            "missing_or_invalid": [k for k, ok in audio.items() if not ok],
        },
        "own_number_call": {
            "configuration_ready": all(telephony.values()),
            "missing_or_invalid": [k for k, ok in telephony.items() if not ok],
        },
        "external_connections_made": False,
        "audio_validated": False,
        "real_call_validated": False,
        "acceptance_scenarios": [
            {"id": scenario, "real_validation": "pending", "executed_by_preflight": False}
            for scenario in [
                "interruptions",
                "corrections",
                "silence",
                "alternative_offers",
                "deposit_approval",
                "connection_loss",
            ]
        ],
        "still_required": [
            "account/model access",
            "microphone/speaker test with consent",
            "signed gateway tunnel test",
            "explicit own-number authorization, expiry and budget",
            "human verification of call outcome and hangup",
        ],
    }
