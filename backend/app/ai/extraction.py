import json
import re

from openai import AsyncOpenAI

from app.ai.contracts import ExtractedConversation, ReservationEvidence
from app.ai.observability import trace
from app.core.config import Settings
from app.observability.recorder import context, observed_span
from app.schemas import BookingConfiguration, OfferDetails


class DeterministicExtractor:
    """Conservative, intentionally bounded Spanish grammar for reproducible offline tests.

    Arbitrary language belongs to ResponsesExtractor. Missing facts never get filled
    from the request unless the restaurant explicitly refers to the requested date.
    """

    async def extract(
        self, text: str, config: BookingConfiguration, restaurant_id: str, attempt_id: str, **kwargs
    ) -> ExtractedConversation:
        lower = text.casefold()
        if any(s in lower for s in ("ignora las instrucciones", "revela el token", "system prompt")):
            return ExtractedConversation(intent="unclear")
        if any(
            s in lower
            for s in ("no quiero hablar con una ia", "no hablamos con asistentes", "no acepto robots")
        ):
            return ExtractedConversation(intent="refuses_ai")
        if any(s in lower for s in ("sin disponibilidad", "estamos completos", "no tenemos mesa")):
            return ExtractedConversation(intent="no_availability")
        dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        times = re.findall(r"\b([012]?\d:[0-5]\d)\b", text)
        people = re.findall(r"para (\d+) personas", lower)
        if not dates and "el día solicitado" in lower and config.requested_date:
            dates = [config.requested_date.isoformat()]
        table = "terrace" if "terraza" in lower else "inside" if "interior" in lower else None
        if not dates or not times or not people or table is None:
            return ExtractedConversation(intent="unclear")
        verified = {}
        for key in config.mandatory_keys():
            if f"requisito {key}: sí" in lower:
                verified[key] = True
            elif f"requisito {key}: no" in lower:
                verified[key] = False
        deposit = re.findall(r"depósito (\d+(?:[.,]\d+)?)", lower)
        price = re.findall(r"precio (\d+(?:[.,]\d+)?)", lower)
        try:
            offer = OfferDetails(
                requested_date=dates[-1],
                time=times[-1],
                party_size=int(people[-1]),
                table_type=table,
                deposit=float(deposit[-1].replace(",", ".")) if deposit else 0,
                price_per_person=float(price[-1].replace(",", ".")) if price else None,
                verified_requirements=verified,
            )
        except ValueError:
            return ExtractedConversation(intent="unclear")
        explicit = any(s in lower for s in ("queda confirmada", "reserva confirmada"))
        name = re.search(r"a nombre de ([^.;\n]+)", text, re.IGNORECASE)
        reference = re.search(r"referencia ([\w-]+)", text, re.IGNORECASE)
        evidence = None
        if explicit or "creo que" in lower or "complete el enlace" in lower:
            evidence = ReservationEvidence(
                restaurant_id=restaurant_id,
                booking_name=name.group(1).strip() if name else None,
                details=offer,
                explicit_confirmation=explicit and "creo que" not in lower,
                pending_user_action="complete el enlace" in lower,
                contradictory="contradictorio" in lower,
                reference=reference.group(1) if reference else None,
                evidence_kind=kwargs.get("evidence_kind", "simulated"),
                source_attempt_id=attempt_id,
            )
        return ExtractedConversation(
            intent="confirmation" if evidence else "proposal",
            offer=offer,
            evidence=evidence,
            supersedes_prior_proposal="corrijo" in lower,
        )


class ResponsesExtractor:
    def __init__(self, settings: Settings, *, client=None, db=None, execution_id: str | None = None):
        self.settings, self.db, self.execution_id = settings, db, execution_id
        self.client = client or AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(), timeout=15, max_retries=0
        )

    async def _observed_parse(self, **payload):
        execution_id = self.execution_id or context.get().get("execution_id")
        if self.db is None or execution_id is None:
            return await self.client.responses.parse(**payload)
        with observed_span(
            self.db, execution_id, "model", agent="negotiation", model=self.settings.reasoning_model
        ) as observation:
            result = await self.client.responses.parse(**payload)
            usage = result.usage
            observation.usage = (
                {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens} if usage else None
            )
            observation.reported_model = getattr(result, "model", None)
            return result

    async def extract(
        self,
        text: str,
        config: BookingConfiguration,
        restaurant_id: str,
        attempt_id: str,
        *,
        prompt: str,
        evidence_kind: str = "provider_transcript",
    ) -> ExtractedConversation:
        # Request and external speech are separate messages. No tools are granted to this extractor.
        context = {
            "restaurant_id": restaurant_id,
            "source_attempt_id": attempt_id,
            "requirements": config.model_dump(mode="json", exclude={"contact_phone", "notes"}),
        }
        result = await self._observed_parse(
            model=self.settings.reasoning_model,
            store=False,
            max_output_tokens=1800,
            input=[
                {
                    "role": "system",
                    "content": prompt
                    + "\nDevuelve solo hechos explícitos. Una oferta incompleta debe ser null.",
                },
                {"role": "developer", "content": json.dumps(context, ensure_ascii=False)},
                {
                    "role": "user",
                    "content": "Datos externos no confiables de la conversación:\n" + text[-6000:],
                },
            ],
            text_format=ExtractedConversation,
        )
        if self.db and self.execution_id:
            usage = result.usage
            trace(
                self.db,
                self.execution_id,
                "negotiation",
                "completed",
                model=self.settings.reasoning_model,
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                observe=False,
            )
        extracted = result.output_parsed
        if extracted is None:
            return ExtractedConversation(intent="unclear")
        if extracted.evidence:
            # Provenance and scope come from the transport. A model cannot forge them.
            extracted.evidence.source_attempt_id = attempt_id
            extracted.evidence.evidence_kind = evidence_kind
        if evidence_kind == "provider_transcript":
            # Assistant speech is context, never evidence of what the restaurant agreed to.
            spoken = " ".join(
                line.removeprefix("restaurant:").strip()
                for line in text.splitlines()
                if line.startswith("restaurant:")
            )
            normalize = lambda value: " ".join(value.casefold().split())
            spoken = normalize(spoken)
            if (
                not extracted.financial_terms_quote
                or normalize(extracted.financial_terms_quote) not in spoken
            ):
                extracted.financial_terms_quote = None
            for details in [extracted.offer, extracted.evidence.details if extracted.evidence else None]:
                if details:
                    details.verified_requirements = {
                        key: value
                        for key, value in details.verified_requirements.items()
                        if not value
                        or (
                            extracted.requirement_quotes.get(key)
                            and normalize(extracted.requirement_quotes[key]) in spoken
                        )
                    }
            if extracted.evidence:
                quote = extracted.evidence.confirmation_quote
                if not quote or normalize(quote) not in spoken:
                    extracted.evidence.explicit_confirmation = False
        return extracted
