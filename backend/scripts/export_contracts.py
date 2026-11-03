"""Run from backend: python scripts/export_contracts.py"""

import json
from pathlib import Path

from pydantic import TypeAdapter

from app.ai.contracts import (
    BookingPlan,
    ExtractedConversation,
    NegotiationDecision,
    ResearchResult,
    VerificationResult,
)
from app.ai.runtime import AIRuntime
from app.core.config import Settings
from app.main import create_app
from app.observability.contracts import ObservationEventOut
from app.providers.calls import MockCallProvider
from app.schemas import EventOut
from app.services.execution import BookingExecutionService

target = Path(__file__).resolve().parents[1] / "contracts"
target.mkdir(exist_ok=True)
app = create_app(Settings(_env_file=None, local_api_token="schema-export-only-never-used-for-a-server"))
(target / "openapi.json").write_text(
    json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
(target / "booking-event.schema.json").write_text(
    json.dumps(EventOut.model_json_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
print(f"Contracts exported to {target}")
(target / "observation-event.schema.json").write_text(
    json.dumps(ObservationEventOut.model_json_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
agent_contract = TypeAdapter(
    BookingPlan | ResearchResult | NegotiationDecision | VerificationResult | ExtractedConversation
)
(target / "ai-contracts.schema.json").write_text(
    json.dumps(agent_contract.json_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
runtime = AIRuntime(
    app.state.db, BookingExecutionService(app.state.db, MockCallProvider(0), 5), app.state.settings, None
)
(target / "ai-graph.mmd").write_text(runtime.graph.get_graph().draw_mermaid() + "\n", encoding="utf-8")
