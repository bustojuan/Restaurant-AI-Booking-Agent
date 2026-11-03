import json

import pytest
from conftest import IDS, TOKEN, make_booking
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.migrate import upgrade
from app.providers.images import ImageCatalogEntry, RestaurantIdentity, VerifiedCatalogImageProvider
from app.providers.restaurants import CUISINES, normalize_categories
from app.schemas import ImageAsset


@pytest.mark.parametrize(
    "params",
    [
        {"q": "Pasta", "region": "Madrid", "cuisine_types": "italian"},
        {"municipality": "madrid", "bbox": "-3.72,40.41,-3.69,40.44"},
        {"latitude": 40.4168, "longitude": -3.7038, "radius_km": 2, "sort": "distance"},
        {"region": "Navarra", "establishment_types": "pizzeria"},
        {"cuisine_types": ["spanish", "mediterranean"]},
    ],
)
def test_combined_search(client, params):
    response = client.get("/api/restaurants", params=params)
    assert response.status_code == 200
    page = response.json()
    assert page["total"] > 0
    for r in page["items"]:
        assert -90 <= r["latitude"] <= 90
        assert -180 <= r["longitude"] <= 180
        assert r["is_simulated"] is True
        assert r["primary_image_url"] is None
        assert r["has_photo"] is False
        assert r["images"] == []
        assert r["website_url"] is None
        assert r["rating"] is None
        assert r["phone"] is None


@pytest.mark.parametrize(
    "params",
    [
        {"bbox": "40,400,41,500"},
        {"bbox": "-3,40,-4,41"},
        {"bbox": "invalid"},
        {"bbox": "nan,40,-3,41"},
        {"latitude": 40},
        {"latitude": 91, "longitude": 0},
        {"radius_km": 5},
        {"sort": "distance"},
        {"offset": -1},
        {"limit": 101},
    ],
)
def test_invalid_search(client, params):
    assert client.get("/api/restaurants", params=params).status_code == 422


def test_pagination_unknown_data_categories_and_selection(client):
    first = client.get("/api/restaurants?limit=3&offset=0").json()
    second = client.get("/api/restaurants?limit=3&offset=3").json()
    assert first["total"] == second["total"] == 10
    assert not {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}
    assert client.get("/api/restaurants?min_rating=3").json()["total"] == 0
    assert client.get("/api/restaurants?max_price=3").json()["total"] == 0
    assert "navarrese" in {c["id"] for c in client.get("/api/restaurants/categories").json()["cuisine_types"]}
    assert normalize_categories(["italian", "unknown", "italian"], CUISINES) == ["italian", "other"]
    booking = make_booking(client, ids=[IDS[3], IDS[0]])
    page = client.get(f"/api/restaurants?region=Madrid&booking_id={booking['id']}").json()
    selected = next(r for r in page["items"] if r["id"] == IDS[0])
    assert selected["selected_position"] == 1


def test_favorites_are_idempotent_and_separate_from_selection(client):
    booking = make_booking(client, ids=[])
    for _ in range(2):
        assert client.post("/api/favorites", json={"restaurant_id": IDS[0]}).status_code == 200
    assert client.get("/api/favorites").json()["total"] == 1
    assert client.get("/api/restaurants?favorites_only=true").json()["total"] == 1
    assert client.get(f"/api/restaurants/{IDS[0]}").json()["is_favorite"] is True
    assert client.get(f"/api/bookings/{booking['id']}").json()["restaurants"] == []
    for _ in range(2):
        assert client.delete(f"/api/favorites/{IDS[0]}").status_code == 204
    assert client.get("/api/favorites").json()["total"] == 0


def asset(url="https://example.test/photo.jpg"):
    # Contract-only test URLs; never shipped as restaurant photographs.
    return {
        "url": url,
        "source": "operator-test-catalog",
        "source_page_url": "https://example.test/source",
        "attribution": "Author (CC BY 4.0)",
        "creator": "Author",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "rights_evidence_url": "https://example.test/evidence",
        "rights_verified": True,
    }


def test_image_provider_matches_exact_identity_and_requires_rights():
    provider = VerifiedCatalogImageProvider(
        [ImageCatalogEntry(source="osm", external_id="node/123", images=[ImageAsset(**asset())])]
    )
    assert len(provider.images_for(RestaurantIdentity(source="osm", external_id="node/123"))) == 1
    assert provider.images_for(RestaurantIdentity(source="osm", external_id="node/124")) == []
    assert provider.images_for(RestaurantIdentity(source="mock", external_id="node/123")) == []
    for invalid in [
        {**asset(), "rights_verified": False},
        {**asset(), "license": "unknown"},
        {**asset(), "url": "file:///private/photo"},
        {**asset(), "attribution": ""},
    ]:
        with pytest.raises(ValidationError):
            ImageAsset(**invalid)


def test_restaurant_image_contract_and_revocation(settings, tmp_path):
    upgrade(settings.database_url)
    catalog = tmp_path / "images.json"
    catalog.write_text(
        json.dumps(
            [
                {
                    "source": "mock",
                    "external_id": IDS[0],
                    "images": [asset(), asset("https://example.test/second.jpg")],
                }
            ]
        ),
        encoding="utf-8",
    )
    settings.image_catalog_path = str(catalog)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(create_app(settings), headers=headers) as client:
        r = client.get(f"/api/restaurants/{IDS[0]}").json()
        assert r["has_photo"] is True
        assert r["primary_image_url"] == asset()["url"]
        assert r["images"][0]["attribution"] == asset()["attribution"]
        assert len(r["additional_images"]) == 1
        assert client.get(f"/api/restaurants/{IDS[1]}").json()["has_photo"] is False
    catalog.write_text("[]", encoding="utf-8")
    with TestClient(create_app(settings), headers=headers) as client:
        assert client.get(f"/api/restaurants/{IDS[0]}").json()["has_photo"] is False
