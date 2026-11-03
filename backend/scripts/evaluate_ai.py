"""Offline objective evaluations. No model requests, audio or external telephone calls."""

import argparse
import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.ai.agents import EvaluationAgent
from app.core.config import Settings
from app.main import create_app
from app.migrate import upgrade


def evaluate_offline(output: Path | None = None):
    cases = json.loads(
        (Path(__file__).parents[1] / "app/ai/evaluations/scenarios.json").read_text(encoding="utf-8")
    )
    results = []
    with tempfile.TemporaryDirectory(prefix="baria-evaluations-") as temporary:
        settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{Path(temporary) / 'evaluation.db'}",
            local_api_token="offline-evaluation-local-token-only",
            ai_extraction_mode="deterministic",
            openai_api_key=None,
            real_telephony_enabled=False,
            voice_sandbox_enabled=False,
            langsmith_tracing_enabled=False,
            call_delay_seconds=0.02,
        )
        upgrade(settings.database_url)
        with TestClient(
            create_app(settings), headers={"Authorization": "Bearer offline-evaluation-local-token-only"}
        ) as client:
            for case in cases:
                started = time.perf_counter()
                future = datetime.now(ZoneInfo("Europe/Madrid")) + timedelta(days=14)
                created = client.post(
                    "/api/bookings",
                    json={
                        "configuration": {
                            "customer_name": "Cliente de evaluación",
                            "contact_phone": "+34000000000",
                            "adults": 4,
                            "requested_date": future.date().isoformat(),
                            "preferred_time": "21:00",
                            "flexibility_minutes": 30,
                            "table_type": "terrace",
                            "dietary_requirements": [{"kind": "celiac", "code": "gluten"}],
                        },
                        "restaurant_ids": ["madrid-1"],
                    },
                )
                created.raise_for_status()
                booking = created.json()
                settings.call_delay_seconds = 0.2 if case.get("cancel") else 0.01
                response = client.post(
                    f"/api/bookings/{booking['id']}/start",
                    headers={"If-Match": str(booking["version"])},
                    json={"mode": "ai_simulation", "scenario_id": case["scenario"]},
                )
                response.raise_for_status()
                deadline = time.monotonic() + 10
                cancelled = False
                while time.monotonic() < deadline:
                    observed = client.get(f"/api/bookings/{booking['id']}").json()
                    if (
                        case.get("cancel")
                        and not cancelled
                        and observed["summary"]["current_call_status"] == "RUNNING"
                    ):
                        cancelled = (
                            client.post(
                                f"/api/bookings/{booking['id']}/cancel",
                                headers={"If-Match": str(observed["version"])},
                            ).status_code
                            == 200
                        )
                    if observed["status"] in {
                        "CONFIRMED",
                        "EXHAUSTED",
                        "FAILED",
                        "WAITING_FOR_USER",
                        "CANCELLED",
                    }:
                        break
                    time.sleep(0.01)
                calls = observed["summary"]["contacted_restaurants"]
                passed = (
                    observed["status"] == case["status"]
                    and bool(calls)
                    and calls[-1]["result"] == case["result"]
                )
                confirmation = observed["summary"]["confirmation"]
                if case.get("time_offset_minutes") and confirmation:
                    passed &= confirmation["details"]["time"] == "21:15:00"
                report = EvaluationAgent().evaluate(client.app.state.db, booking["id"])
                passed &= report.passed
                results.append(
                    {
                        "id": case["id"],
                        "passed": passed,
                        "expected_status": case["status"],
                        "observed_status": observed["status"],
                        "result": calls[-1]["result"] if calls else None,
                        "latency_ms": round((time.perf_counter() - started) * 1000),
                        "objective_checks": report.checks,
                    }
                )
    report = {
        "scope": "offline_deterministic_simulation",
        "cases": len(results),
        "passed": sum(r["passed"] for r in results),
        "success_rate": sum(r["passed"] for r in results) / len(results),
        "false_confirmations": sum(
            r["observed_status"] == "CONFIRMED" and r["expected_status"] != "CONFIRMED" for r in results
        ),
        "model_requests": 0,
        "telephone_calls": 0,
        "real_audio_tested": False,
        "results": results,
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("docs/ai-evaluation-report.json"))
    result = evaluate_offline(parser.parse_args().output)
    print(json.dumps({key: value for key, value in result.items() if key != "results"}, indent=2))
    if result["passed"] != result["cases"]:
        raise SystemExit(1)
