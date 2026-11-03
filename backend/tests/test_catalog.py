import json

import httpx
import pytest
from conftest import current, make_booking

from app.models import BookingRequest
from app.providers.overpass import OverpassRestaurantProvider, parse_element, website
from app.services.catalog import import_catalog


def element(identifier=123, **tags):
    return {
        "type": "node",
        "id": identifier,
        "lat": 40.4168,
        "lon": -3.7038,
        "tags": {"name": "Proveedor de prueba", "amenity": "restaurant", **tags},
    }


def test_parser_preserves_identity_and_leaves_unknowns_empty():
    record = parse_element(
        element(
            cuisine="sushi;pizza", **{"diet:vegan": "yes", "image": "https://example.test/unlicensed.jpg"}
        ),
        "Madrid",
    )
    assert record.id == "osm-node-123"
    assert record.external_id == "node/123"
    assert record.cuisine_types == ["italian", "japanese"]
    assert record.dietary_options == ["vegan"]
    assert record.phone is None and record.website_url is None
    assert record.municipality == "" and record.is_simulated is False
    assert parse_element(element(disused="yes"), "Madrid") is None
    assert parse_element({**element(), "lat": 99}, "Madrid") is None
    assert (
        parse_element({**element(), "type": "way", "center": {"lat": 42, "lon": -1}}, "Navarra").latitude
        == 42
    )
    for url in ["javascript:alert(1)", "file:///private", "https://user:secret@example.test"]:
        assert website(url) is None
    assert website("example.test/menu") == "https://example.test/menu"


def test_cache_offline_and_failed_refresh_preserve_snapshot(tmp_path):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"elements": [element()]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        provider = OverpassRestaurantProvider("Madrid", tmp_path, client=client)
        assert len(provider.records()) == 1
        provider.records()
        provider.records(offline=True)
        assert len(calls) == 1
    snapshot = (tmp_path / "overpass-madrid.json").read_bytes()
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"remark": "timeout", "elements": [element()]})
            )
        ) as client,
        pytest.raises(ValueError, match="Incomplete"),
    ):
        OverpassRestaurantProvider("Madrid", tmp_path, client=client).records(force=True)
    assert (tmp_path / "overpass-madrid.json").read_bytes() == snapshot
    assert json.loads(snapshot)["license"] == "ODbL-1.0"
    with pytest.raises(ValueError, match="offline"):
        OverpassRestaurantProvider("Navarra", tmp_path).records(offline=True)


def test_upsert_keeps_favorites_drafts_order_and_protects_active(client):
    db = client.app.state.db
    record = parse_element(
        element(cuisine="sushi", **{"diet:vegetarian": "yes", "addr:city": "Madrid"}), "Madrid"
    )
    assert import_catalog(db, [record])["created"] == 1
    client.post("/api/favorites", json={"restaurant_id": record.id})
    booking = make_booking(client, ids=[record.id, "navarra-1"])
    assert import_catalog(db, [record])["unchanged"] == 1
    changed = record.model_copy(update={"name": "Nombre actualizado"})
    assert import_catalog(db, [changed])["updated"] == 1
    assert current(client, booking["id"])["version"] == booking["version"]
    assert [r["restaurant"]["id"] for r in current(client, booking["id"])["restaurants"]] == [
        record.id,
        "navarra-1",
    ]
    assert client.get("/api/favorites").json()["items"][0]["id"] == record.id
    response = client.get(
        "/api/restaurants",
        params={
            "catalog": "auto",
            "region": "Madrid",
            "cuisine_group": "asian",
            "dietary_options": "vegetarian",
            "q": "Madrid",
        },
    ).json()
    assert response["total"] == 1
    restaurant = response["items"][0]
    assert restaurant["source_url"] == "https://www.openstreetmap.org/node/123"
    assert restaurant["data_attribution"] and restaurant["has_photo"] is False
    assert restaurant["rating"] is None
    assert client.get("/api/restaurants?catalog=auto&region=Madrid&q=SIMULADO").json()["total"] == 0
    assert client.get("/api/restaurants?catalog=auto&region=Navarra").json()["total"] == 5
    with db.transaction(write=True) as session:
        session.get(BookingRequest, booking["id"]).status = "RUNNING"
    assert import_catalog(db, [record])["protected_active"] == 1
    assert client.get(f"/api/restaurants/{record.id}").json()["name"] == changed.name


def test_import_rolls_back_whole_batch_on_id_collision(client):
    db = client.app.state.db
    first = parse_element(element(), "Madrid")
    collision = parse_element(element(456), "Madrid").model_copy(update={"id": "madrid-1"})
    with pytest.raises(ValueError, match="collision"):
        import_catalog(db, [first, collision])
    assert client.get(f"/api/restaurants/{first.id}").status_code == 404
