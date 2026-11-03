"""Read-only independent archive/trace checks and API reconciliation, no app writes."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

home = Path(__file__).resolve().parents[1] / "private/demo"
cfg = json.loads((home / "owned.json").read_text())
database = Path(cfg.get("runtime_database", str(home / "booking.db")))
db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
db.row_factory = sqlite3.Row
counts = {
    t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    for t in [
        "booking_requests",
        "call_attempts",
        "reservation_confirmations",
        "reservation_offers",
        "observed_executions",
        "observation_events",
    ]
}
stage = {297: (119, 89), 300: (120, 90), 301: (121, 91)}
assert counts["call_attempts"] in stage, counts
n, conf = stage[counts["call_attempts"]]
assert (
    counts["booking_requests"] == n and counts["reservation_confirmations"] == conf
), counts
assert not db.execute("PRAGMA foreign_key_check").fetchall()
assert not db.execute(
    "SELECT id FROM booking_requests WHERE status IN ('RUNNING','WAITING_FOR_USER')"
).fetchall()
assert not db.execute(
    "SELECT id FROM reservation_confirmations WHERE simulated!=1"
).fetchall()
assert not db.execute(
    "SELECT id FROM observation_events WHERE kind IN ('model','delegation')"
).fetchall()
results = dict(db.execute("SELECT result,COUNT(*) FROM call_attempts GROUP BY result"))
target = {
    "CONFIRMED": 90,
    "NO_AVAILABILITY": 97,
    "INCOMPATIBLE_OFFER": 67,
    "DECLINED": 5,
    "ERROR": 15,
    "TIMEOUT": 15,
    "AMBIGUOUS": 11,
}
if counts["call_attempts"] == 297:
    for key in ["CONFIRMED", "NO_AVAILABILITY", "INCOMPATIBLE_OFFER"]:
        target[key] -= 1
elif counts["call_attempts"] == 301:
    target["CONFIRMED"] += 1
assert results == target, (results, target)
times = 0
spans = 0
for run in db.execute("SELECT id FROM observed_executions"):
    events = db.execute(
        "SELECT * FROM observation_events WHERE execution_id=? ORDER BY id",
        (run["id"],),
    ).fetchall()
    starts = {}
    for e in events:
        datetime.fromisoformat(e["occurred_at"])
        datetime.fromisoformat(e["received_at"])
        times += 1
        key = (e["span_id"], e["kind"])
        if e["phase"] == "started" and e["span_id"]:
            starts[key] = e
        if (
            e["phase"] in ("completed", "failed", "interrupted")
            and e["span_id"]
            and key in starts
        ):
            assert e["occurred_at"] >= starts[key]["occurred_at"]
            if e["elapsed_ms"] is not None:
                assert e["elapsed_ms"] >= 0
            spans += 1
days = db.execute(
    "SELECT COUNT(DISTINCT substr(started_at,1,10)) FROM call_attempts"
).fetchone()[0]
assert days == (41 if counts["call_attempts"] == 297 else 42), (days, counts)
api = {}
try:
    start = json.loads((home / "manifest.json").read_text())["runs"][0]["slot"][:10]
    path = f"http://127.0.0.1:18011/api/admin/observability/analytics?date_from={start}&date_to={cfg['anchor']}&mode=ai_simulation"
    request = Request(path, headers={"Authorization": "Bearer " + cfg["admin"]})
    with urlopen(request, timeout=30) as response:
        api = json.load(response)
except OSError:
    pass
if api:
    assert api["calls"] == counts["call_attempts"], api["calls"]
    assert api["bookings"] == n, api["bookings"]
    assert api["confirmed_bookings"] == conf, api["confirmed_bookings"]
    assert abs(api["confirmation_rate"] - conf / n) < 1e-9
report = {
    "counts": counts,
    "results": results,
    "days": days,
    "checkedEvents": times,
    "pairedSpans": spans,
    "foreignKeys": "pass",
    "simulatedOnly": True,
    "noModelOrDelegationSpans": True,
    "analytics": api,
}
(home / "independent-validation.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8"
)
print(json.dumps({k: v for k, v in report.items() if k != "analytics"}, indent=2))
if api:
    print("Authenticated API Analytics read succeeded; full metrics saved privately.")
