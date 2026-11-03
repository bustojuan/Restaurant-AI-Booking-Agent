from sqlalchemy import select

from app.ai.models import AIExecution
from app.ai.prompts import prompt_bundle
from app.core.errors import DomainError


def prepare_execution(session, booking, mode, authorization, settings):
    if settings is None:
        raise DomainError("ai_not_configured", "AI runtime settings are required", 503)
    if mode == "ai_simulation" and settings.ai_extraction_mode == "responses" and not settings.openai_api_key:
        raise DomainError("credentials_missing", "Responses extraction requires OpenAI credentials", 422)
    if mode == "real_telephony":
        from app.voice.authorization import validate_authorization

        validate_authorization(session, booking, authorization, settings)
    elif mode != "ai_simulation" or authorization is not None:
        raise DomainError("invalid_mode", "Invalid execution mode or authorization", 422)
    if session.scalar(select(AIExecution).where(AIExecution.booking_id == booking.id)):
        raise DomainError("execution_exists", "AI execution already exists")
    session.add(
        AIExecution(
            booking_id=booking.id,
            mode=mode,
            prompts=prompt_bundle(),
            authorization=authorization.model_dump(mode="json") if authorization else None,
        )
    )
