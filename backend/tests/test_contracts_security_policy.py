import pytest
from conftest import TOKEN, configuration
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.migrate import migration_config, upgrade
from app.schemas import BookingConfiguration, OfferDetails
from app.services.negotiation import NegotiationPolicyService


def test_rest_auth_and_safe_validation(client):
    assert client.get("/api/health", headers={"Authorization": ""}).status_code == 200
    assert client.get("/api/bookings", headers={"Authorization": ""}).status_code == 401
    assert client.post(
        "/api/bookings", json={"configuration": {"secret-unknown-input": "sensitive"}}
    ).json() == {
        "error": {"code": "validation_error", "message": "Invalid request parameters or body"},
    }
    assert client.get("/api/restaurants", headers={"Host": "evil.test"}).status_code == 400


@pytest.mark.parametrize(
    "token,origin", [("bad-token", None), ("token-con-caracteres-é", None), (TOKEN, "https://evil.test")]
)
def test_websocket_auth_and_origin(client, token, origin):
    with pytest.raises(WebSocketDisconnect) as closed:
        headers = {"origin": origin} if origin else {}
        with client.websocket_connect("/api/events/ws", headers=headers) as websocket:
            websocket.send_json({"token": token})
            websocket.receive_json()
    assert closed.value.code == 1008


def test_openapi_contracts_and_shared_response_schemas(client):
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    assert "HTTPBearer" in spec["components"]["securitySchemes"]
    assert {"primary_image_url", "images", "additional_images", "website_url", "has_photo"}.issubset(
        schemas["RestaurantOut"]["properties"]
    )
    assert "pending_approvals" in schemas["BookingSummary"]["properties"]
    assert schemas["BookingConfigurationPatch"]["additionalProperties"] is False
    assert "adults" in schemas["BookingConfigurationPatch"]["properties"]
    assert "428" in spec["paths"]["/api/bookings/{booking_id}"]["patch"]["responses"]
    # WebSocket frames are not in OpenAPI paths; EventOut is exposed via REST using the same model.
    assert "EventOut" in schemas
    assert "/api/restaurants/search" not in spec["paths"]


def test_migration_upgrade_downgrade_and_metadata_match(settings):
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    from alembic import command
    from app.db.session import Database
    from app.models import Base

    config = migration_config(settings.database_url)
    upgrade(settings.database_url)
    db = Database(settings.database_url)
    with db.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    db.engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["mode"] == "simulation"


def test_second_executor_cannot_use_same_database(client, settings):
    with pytest.raises(RuntimeError, match="Another executor"), TestClient(create_app(settings)):
        pass


def offer_for(config):
    return OfferDetails(
        requested_date=config.requested_date,
        time=config.preferred_time,
        party_size=config.party_size,
        table_type=config.table_type,
        verified_requirements=dict.fromkeys(config.mandatory_keys(), True),
    )


def test_negotiation_evidence_hard_constraints_and_approval():
    config = BookingConfiguration(
        **{
            **configuration(),
            "accessibility_required": True,
            "dietary_requirements": [{"kind": "allergy", "code": "nuts"}],
        }
    )
    policy = NegotiationPolicyService()
    offer = offer_for(config)
    assert policy.evaluate(config, offer) == "ACCEPTABLE"
    assert (
        policy.evaluate(config, offer.model_copy(update={"verified_requirements": {}}))
        == "INSUFFICIENT_INFORMATION"
    )
    assert (
        policy.evaluate(config, offer.model_copy(update={"verified_requirements": {"dietary:nuts": False}}))
        == "UNACCEPTABLE"
    )
    assert policy.evaluate(config, offer.model_copy(update={"party_size": 9})) == "UNACCEPTABLE"
    assert policy.evaluate(config, offer.model_copy(update={"deposit": 20})) == "REQUIRES_USER_APPROVAL"


def test_negotiation_budget_table_and_time():
    config = BookingConfiguration(
        **{
            **configuration(),
            "budget_per_person": 30,
            "strict_budget": True,
            "table_type": "terrace",
            "table_type_mandatory": True,
        }
    )
    policy = NegotiationPolicyService()
    offer = offer_for(config)
    assert policy.evaluate(config, offer) == "INSUFFICIENT_INFORMATION"
    assert policy.evaluate(config, offer.model_copy(update={"price_per_person": 40})) == "UNACCEPTABLE"
    assert policy.evaluate(config, offer.model_copy(update={"price_per_person": 20})) == "ACCEPTABLE"
    assert policy.evaluate(config, offer.model_copy(update={"table_type": "inside"})) == "UNACCEPTABLE"


@pytest.mark.parametrize("day,clock", [("2030-03-31", "02:30"), ("2030-10-27", "02:30")])
def test_dst_ambiguous_and_nonexistent_times(day, clock):
    config = BookingConfiguration(**{**configuration(), "requested_date": day, "preferred_time": clock})
    with pytest.raises(ValueError):
        config.validate_start()
