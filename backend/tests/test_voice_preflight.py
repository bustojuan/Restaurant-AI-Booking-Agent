import json

from app.voice.preflight import readiness


def test_preparing_own_number_does_not_rewrite_selected_restaurants(client, settings, monkeypatch):
    import runpy
    import sys

    from conftest import current, make_booking

    existing = make_booking(client, ids=["madrid-1"])
    before = client.get("/api/restaurants/madrid-1").json()
    settings.telephony_allowed_numbers = ["+34910000003"]
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["prepare_own_number_test.py", "--prepare-own-number-fixture"])
    runpy.run_path("scripts/prepare_own_number_test.py", run_name="__main__")
    assert client.get("/api/restaurants/madrid-1").json() == before
    assert current(client, existing["id"])["version"] == existing["version"]
    entries = client.get("/api/restaurants?q=PRUEBA EN NÚMERO PROPIO").json()["items"]
    assert len(entries) == 1 and entries[0]["source"] == "own-number-test"
    assert entries[0]["phone"] == "+34910000003"


def test_readiness_reports_missing_configuration_without_secrets(settings):
    result = readiness(settings)
    assert result["audio"]["configuration_ready"] is False
    assert result["own_number_call"]["configuration_ready"] is False
    assert result["external_connections_made"] is False
    assert len(result["acceptance_scenarios"]) == 6
    assert all(
        s["real_validation"] == "pending" and not s["executed_by_preflight"]
        for s in result["acceptance_scenarios"]
    )
    settings.openai_api_key = "never-print-this-secret"
    settings.voice_sandbox_enabled = True
    settings.twilio_account_sid = "AC" + "a" * 32
    settings.twilio_auth_token = "another-private-secret"
    settings.twilio_phone_number = "+34910000002"
    settings.telephony_allowed_numbers = ["+34910000003"]
    settings.telephony_public_origin = "https://gateway.example.test"
    settings.real_telephony_enabled = True
    settings.telephony_cost_per_minute = 1
    settings.live_cost_per_minute = 1
    settings.reasoning_reserved_cost_per_call = 1
    result = readiness(settings)
    assert result["audio"]["configuration_ready"] is True
    assert result["own_number_call"]["configuration_ready"] is True
    assert result["real_call_validated"] is False
    serialized = json.dumps(result)
    for private in [
        "never-print-this-secret",
        "another-private-secret",
        "+34910000002",
        "+34910000003",
        settings.twilio_account_sid,
    ]:
        assert private not in serialized
    settings.telephony_public_origin = "https://user:secret@example.test"
    assert "TELEPHONY_PUBLIC_ORIGIN" in readiness(settings)["own_number_call"]["missing_or_invalid"]
