"""Read-only, evidence-linked explanations. Never run agents or business transitions."""

from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import select

from app.models import ReservationOffer
from app.observability.center_contracts import (
    AttemptEvidence,
    AttemptExplanation,
    AttemptFact,
    AttemptOffer,
    AttemptReview,
    AttemptTerms,
)
from app.observability.models import ObservationEvent
from app.schemas import BookingConfiguration, OfferDetails


def explain_attempt(session, attempt, booking, ai, run, voice, confirmation):
    evidence = lambda kind, identity, label: AttemptEvidence(kind=kind, id=identity, label=label)
    request_ref = evidence("request", booking.id, "Solicitud guardada")
    call_ref = evidence("call", attempt.id, "Resultado del intento")
    facts, offers = [], []
    try:
        config = BookingConfiguration.model_validate(booking.configuration)
        requested = AttemptTerms(
            requested_date=config.requested_date,
            time=config.preferred_time,
            party_size=config.party_size,
            table_type=config.table_type,
            flexibility_minutes=config.flexibility_minutes,
        )
    except ValidationError:
        config, requested = None, None

    def fact(code, message, *refs):
        facts.append(AttemptFact(code=code, message=message, evidence=list(refs)))

    if requested and requested.time:
        fact(
            "requested",
            f"Se solicitó mesa para {requested.party_size} personas el "
            f"{requested.requested_date} a las {requested.time.strftime('%H:%M')}, con "
            f"{requested.flexibility_minutes} minutos de flexibilidad.",
            request_ref,
        )
    for offer in session.scalars(
        select(ReservationOffer)
        .where(ReservationOffer.attempt_id == attempt.id)
        .order_by(ReservationOffer.id)
    ):
        try:
            details = OfferDetails.model_validate(offer.details)
        except ValidationError:
            fact(
                "offer_unavailable",
                "La oferta conservada no tiene un formato verificable.",
                evidence("offer", offer.id, "Oferta conservada"),
            )
            continue
        offer_ref = evidence("offer", offer.id, "Oferta " + offer.id[:8])
        evaluation_ref = evidence("evaluation", offer.id, "Evaluación guardada")
        offers.append(
            AttemptOffer(
                id=offer.id,
                terms=AttemptTerms(
                    requested_date=details.requested_date,
                    time=details.time,
                    party_size=details.party_size,
                    table_type=details.table_type,
                    deposit=details.deposit,
                ),
                evaluation=offer.evaluation,
                approval_pending=offer.approval_pending,
                decision=offer.decision,
            )
        )
        fact(
            "offered",
            f"La oferta guardada es para {details.party_size} personas el "
            f"{details.requested_date} a las {details.time.strftime('%H:%M')}.",
            offer_ref,
        )
        # Describe a demonstrable mismatch, not an invented historical agent explanation.
        if config and config.requested_date and config.preferred_time and offer.evaluation == "UNACCEPTABLE":
            if details.requested_date != config.requested_date:
                fact(
                    "date_mismatch",
                    "La fecha ofrecida difiere de la solicitada.",
                    request_ref,
                    offer_ref,
                    evaluation_ref,
                )
            if details.party_size != config.party_size:
                fact(
                    "party_mismatch",
                    "El número de personas ofrecido difiere del solicitado.",
                    request_ref,
                    offer_ref,
                    evaluation_ref,
                )
            minutes = (
                abs(
                    (
                        datetime.combine(details.requested_date, details.time)
                        - datetime.combine(config.requested_date, config.preferred_time)
                    ).total_seconds()
                )
                / 60
            )
            if details.requested_date == config.requested_date and minutes > config.flexibility_minutes:
                fact(
                    "time_outside_window",
                    f"La oferta se evaluó como incompatible. La diferencia "
                    f"horaria es de {minutes:g} minutos y supera los {config.flexibility_minutes} "
                    "minutos autorizados.",
                    request_ref,
                    offer_ref,
                    evaluation_ref,
                )
        labels = {
            "ACCEPTABLE": "La evaluación guardada indica que la oferta cumple las condiciones; por sí sola no confirma una reserva.",
            "UNACCEPTABLE": "La evaluación guardada clasifica la oferta como incompatible.",
            "INSUFFICIENT_INFORMATION": "La evaluación guardada indica que faltan datos para aceptar la oferta.",
            "REQUIRES_USER_APPROVAL": "La oferta requiere autorización del usuario antes de aceptarse.",
        }
        fact(
            "evaluation",
            labels.get(offer.evaluation, "Evaluación conservada: " + offer.evaluation),
            evaluation_ref,
        )

    simulated = (
        confirmation.simulated
        if confirmation
        else ai.mode != "real_telephony"
        if ai
        else (run.mode != "real_telephony" if run else None)
    )
    if confirmation:
        fact(
            "confirmed",
            "Existe una confirmación simulada persistida."
            if confirmation.simulated
            else "Existe una confirmación persistida por el backend.",
            evidence("confirmation", confirmation.id, "Confirmación " + confirmation.id[:8]),
        )
    if run:
        for event in session.scalars(
            select(ObservationEvent)
            .where(
                ObservationEvent.execution_id == run.id,
                ObservationEvent.call_attempt_id == attempt.id,
                ObservationEvent.kind.in_(
                    ["backend.call.completed", "backend.booking.confirmed", "backend.call_reconciliation"]
                ),
            )
            .order_by(ObservationEvent.id)
        ):
            fact(
                "business_event",
                {
                    "backend.call.completed": "El backend registró la finalización del intento.",
                    "backend.booking.confirmed": "El backend registró la confirmación de la reserva.",
                    "backend.call_reconciliation": "Se conserva una revisión realizada por el operador.",
                }[event.kind],
                AttemptEvidence(
                    kind="event", id=event.event_id, label=f"Evento #{event.id}", event_cursor=event.id
                ),
            )

    review = AttemptReview(
        category="none",
        title="Resultado registrado",
        message="Consulta la oferta, la confirmación y los eventos que respaldan este intento.",
    )
    outcomes = {
        "NO_AVAILABILITY": "El resultado guardado indica que no había disponibilidad.",
        "INCOMPATIBLE_OFFER": "El intento terminó con una oferta incompatible.",
        "NOT_CONFIRMED": "El intento terminó sin obtener una confirmación verificada.",
        "DECLINED_AI": "El resultado guardado indica una negativa a conversar con la IA.",
        "DECLINED": "El usuario rechazó la propuesta.",
        "USER_APPROVAL_REQUIRED": "El intento requiere aprobación del usuario para la propuesta guardada.",
        "CANCELLED": "Se canceló la ejecución; este resultado no acredita la cancelación de una reserva externa.",
    }
    if attempt.result in outcomes:
        fact("outcome", outcomes[attempt.result], call_ref)
    ambiguous = attempt.result in {"AMBIGUOUS", "UNCERTAIN", "INTERRUPTED", "DISCONNECTED", "TIMEOUT"}
    if voice and voice.action == "RECONCILED_NO_RESERVATION":
        review = AttemptReview(
            category="reconciled",
            title="Ausencia de reserva verificada por el operador",
            message="La revisión está registrada. La ejecución sigue detenida; no hay rellamada ni reanudación automática.",
            automatic_continuation=False,
        )
    elif not confirmation and (
        (voice and (voice.transport_state == "UNCERTAIN" or voice.action == "RECONCILE"))
        or (ambiguous and attempt.status == "FAILED")
        or (ambiguous and voice and voice.accepted_offer)
    ):
        review = AttemptReview(
            category="review_required",
            title="Podría existir una reserva: requiere revisión",
            message="No hay confirmación verificada. Un resultado fallido no demuestra que el restaurante no haya reservado. No se debe continuar ni repetir el contacto sin comprobarlo.",
            automatic_continuation=False,
            reconciliation_available=bool(
                ai
                and ai.mode == "real_telephony"
                and voice
                and voice.external_call_sid
                and booking.status in {"FAILED", "CANCELLED"}
            ),
            steps=[
                "Comprueba con el establecimiento si existe una reserva antes de crear otra.",
                "Comprueba también que la llamada ha terminado; colgar no demuestra que no haya reserva.",
                "Si existe reserva, resuélvela con el establecimiento. El panel no la confirma ni cancela por inferencia.",
                "Si has verificado que no existe reserva, un operador puede registrar la revisión mediante la operación de reconciliación existente, que comprueba el proveedor y la versión. No reanuda la ejecución.",
            ],
        )
    elif ambiguous or attempt.result == "INSUFFICIENT_INFORMATION":
        safe = bool(
            attempt.status == "COMPLETED"
            and voice
            and not voice.accepted_offer
            and voice.transport_state in {"ENDED", "SIMULATED"}
        )
        review = AttemptReview(
            category="continue" if safe else "unknown",
            title="Sin propuesta aceptada: se podía continuar"
            if safe
            else "Información insuficiente para descartar una reserva",
            message="El intento terminó sin oferta aceptada registrada. El motor podía seguir con la cola; consulta el estado final de la reserva."
            if safe
            else "La captura conservada no permite asegurar qué ocurrió. Revisa el resultado antes de repetir el contacto.",
            automatic_continuation=True if safe else None,
            steps=[]
            if safe
            else ["Verifica con el establecimiento si existe una reserva antes de repetir el contacto."],
        )
    if ambiguous or attempt.result == "INSUFFICIENT_INFORMATION":
        if simulated and review.category in {"review_required", "unknown"}:
            review.message = "Este intento simulado reproduce una confirmación no verificable. No acredita una reserva real. En una llamada real, el proceso debe detenerse hasta revisar lo ocurrido."
            review.steps.insert(
                0,
                "En esta simulación, revisa las evidencias del escenario; no contactes al restaurante por este resultado. Los pasos siguientes se aplican a intentos reales.",
            )
        fact("ambiguity", review.message, call_ref)
    return AttemptExplanation(
        requested=requested,
        offers=offers,
        facts=facts,
        review=review,
        booking_status=booking.status,
        booking_version=booking.version,
        simulated=simulated,
    )
