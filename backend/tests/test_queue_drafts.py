from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import IDS, TOKEN, current, make_booking, versioned
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import BookingRestaurant


def ids(booking):
    return [row["restaurant"]["id"] for row in booking["restaurants"]]


def test_insert_append_reorder_remove_and_contiguous_positions(client):
    booking = make_booking(client, ids=[IDS[0], IDS[1]], config={})
    path = f"/api/bookings/{booking['id']}/restaurants"
    added = versioned(client, "POST", path, booking["version"], {"restaurant_id": IDS[2], "position": 1})
    assert added.status_code == 200
    booking = added.json()
    assert ids(booking) == [IDS[0], IDS[2], IDS[1]]
    appended = versioned(client, "POST", path, booking["version"], {"restaurant_id": IDS[3]})
    assert appended.status_code == 200
    booking = appended.json()
    order = [IDS[3], IDS[1], IDS[2], IDS[0]]
    reordered = versioned(client, "PUT", path + "/order", booking["version"], {"restaurant_ids": order})
    assert reordered.status_code == 200
    assert ids(reordered.json()) == order
    removed = versioned(client, "DELETE", path + f"/{IDS[2]}", reordered.json()["version"])
    assert removed.status_code == 200
    assert ids(removed.json()) == [IDS[3], IDS[1], IDS[0]]
    assert [r["position"] for r in removed.json()["restaurants"]] == [0, 1, 2]
    with client.app.state.db.transaction() as session:
        persisted = session.scalars(
            select(BookingRestaurant)
            .where(BookingRestaurant.booking_id == booking["id"])
            .order_by(BookingRestaurant.position)
        ).all()
        assert [r.restaurant_id for r in persisted] == [IDS[3], IDS[1], IDS[0]]


@pytest.mark.parametrize("bad_order", [[IDS[0]], [IDS[0], IDS[0]], [IDS[0], IDS[3]], []])
def test_invalid_order_is_atomic(client, bad_order):
    booking = make_booking(client, ids=IDS[:2])
    before = current(client, booking["id"])
    result = versioned(
        client,
        "PUT",
        f"/api/bookings/{booking['id']}/restaurants/order",
        booking["version"],
        {"restaurant_ids": bad_order},
    )
    assert result.status_code == 422
    assert current(client, booking["id"]) == before


def test_duplicate_and_invalid_insert_do_not_change_version(client):
    booking = make_booking(client, ids=IDS[:2])
    path = f"/api/bookings/{booking['id']}/restaurants"
    duplicate = versioned(client, "POST", path, booking["version"], {"restaurant_id": IDS[0]})
    assert duplicate.status_code == 409
    for position in [-1, 3]:
        result = versioned(
            client, "POST", path, booking["version"], {"restaurant_id": IDS[2], "position": position}
        )
        assert result.status_code == 422
    missing = versioned(client, "POST", path, booking["version"], {"restaurant_id": "missing"})
    assert missing.status_code == 404
    assert current(client, booking["id"]) == booking


def test_concurrent_saves_only_one_wins(client):
    booking = make_booking(client, ids=IDS[:2])
    path = f"/api/bookings/{booking['id']}"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                versioned, client, "PATCH", path, booking["version"], {"configuration": {"notes": note}}
            )
            for note in ["first", "second"]
        ]
        responses = [f.result() for f in futures]
    assert sorted(r.status_code for r in responses) == [200, 409]
    winner = next(r.json() for r in responses if r.status_code == 200)
    assert current(client, booking["id"]) == winner


def test_error_after_queue_rewrite_rolls_back_everything(client, monkeypatch):
    from app.services import bookings

    booking = make_booking(client, ids=IDS[:2])
    before = current(client, booking["id"])
    events_before = client.get(f"/api/bookings/{booking['id']}/events").json()

    def fail_to_emit(*args, **kwargs):
        raise RuntimeError("Injected failure after queue rewrite")

    with monkeypatch.context() as patch:
        patch.setattr(bookings, "emit", fail_to_emit)
        with pytest.raises(RuntimeError, match="Injected failure"):
            versioned(
                client,
                "POST",
                f"/api/bookings/{booking['id']}/restaurants",
                booking["version"],
                {"restaurant_id": IDS[2], "position": 0},
            )
    assert current(client, booking["id"]) == before
    assert client.get(f"/api/bookings/{booking['id']}/events").json() == events_before


def test_concurrent_insert_and_reorder_share_version(client):
    booking = make_booking(client, ids=IDS[:2])
    base = f"/api/bookings/{booking['id']}/restaurants"
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(versioned, client, "POST", base, booking["version"], {"restaurant_id": IDS[2]})
        second = pool.submit(
            versioned,
            client,
            "PUT",
            base + "/order",
            booking["version"],
            {"restaurant_ids": list(reversed(IDS[:2]))},
        )
        results = [first.result(), second.result()]
    assert sorted(r.status_code for r in results) == [200, 409]
    assert ids(current(client, booking["id"])) in [IDS[:3], list(reversed(IDS[:2]))]


def test_required_and_stale_version(client):
    booking = make_booking(client, ids=[])
    path = f"/api/bookings/{booking['id']}"
    assert client.patch(path, json={"configuration": {"notes": "x"}}).status_code == 428
    for invalid in ["*", "W/1", "-1", "0", '"1', "1,2"]:
        assert (
            client.patch(path, headers={"If-Match": invalid}, json={"configuration": {}}).status_code == 422
        )
    result = versioned(client, "PATCH", path, booking["version"], {"configuration": {"notes": "saved"}})
    assert result.status_code == 200
    assert result.headers["etag"] == f'"{result.json()["version"]}"'
    assert versioned(client, "PATCH", path, booking["version"], {"configuration": {}}).status_code == 409


def test_draft_autosave_active_pointer_favorites_survive_restart(settings):
    from app.migrate import upgrade

    upgrade(settings.database_url)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(create_app(settings), headers=headers) as client:
        booking = make_booking(client, ids=[IDS[3], IDS[0]], config={})
        patch = versioned(
            client,
            "PATCH",
            f"/api/bookings/{booking['id']}",
            booking["version"],
            {"configuration": {"notes": "autosave", "children": 1, "high_chairs": 1}},
        )
        assert patch.status_code == 200
        saved = patch.json()
        state = client.get("/api/workspace").json()
        assert (
            versioned(
                client, "PUT", "/api/workspace", state["version"], {"active_draft_id": booking["id"]}
            ).status_code
            == 200
        )
        assert client.post("/api/favorites", json={"restaurant_id": IDS[0]}).status_code == 200
        # Map/list consume the same read-only explorer route, including selection overlays.
        for query in [
            "region=Navarra",
            "region=Madrid&cuisine_types=italian",
            "bbox=-4,40,-3,41",
            "sort=name",
        ]:
            assert client.get(f"/api/restaurants?{query}&booking_id={booking['id']}").status_code == 200
        restored = current(client, booking["id"])
        assert restored["configuration"] == saved["configuration"]
        assert ids(restored) == [IDS[3], IDS[0]]
        assert restored["version"] == saved["version"]
    with TestClient(create_app(settings), headers=headers) as client:
        restored = current(client, booking["id"])
        assert restored["configuration"] == saved["configuration"]
        assert ids(restored) == [IDS[3], IDS[0]]
        assert client.get("/api/workspace").json()["active_draft_id"] == booking["id"]
        assert [r["id"] for r in client.get("/api/favorites").json()["items"]] == [IDS[0]]
        assert client.get("/api/bookings?status=DRAFT").json()["items"][0]["id"] == booking["id"]
        assert (
            versioned(client, "DELETE", f"/api/bookings/{booking['id']}", restored["version"]).status_code
            == 204
        )
        assert client.get("/api/workspace").json()["active_draft_id"] is None
        assert client.get(f"/api/bookings/{booking['id']}").status_code == 404
        assert client.get("/api/favorites").json()["total"] == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"adults": 0},
        {"children": -1},
        {"high_chairs": 1},
        {"unknown": True},
        {"adults": None},
        {"strict_budget": True},
        {"preferred_time": "21:00:00+01:00"},
    ],
)
def test_invalid_partial_configuration_preserves_draft(client, patch):
    booking = make_booking(client, config={})
    response = versioned(
        client, "PATCH", f"/api/bookings/{booking['id']}", booking["version"], {"configuration": patch}
    )
    assert response.status_code == 422
    assert current(client, booking["id"]) == booking


def test_workspace_concurrency_and_missing_draft(client):
    booking = make_booking(client, config={})
    state = client.get("/api/workspace").json()
    result = versioned(client, "PUT", "/api/workspace", state["version"], {"active_draft_id": booking["id"]})
    assert result.status_code == 200
    assert (
        versioned(client, "PUT", "/api/workspace", state["version"], {"active_draft_id": None}).status_code
        == 409
    )
    assert (
        versioned(
            client, "PUT", "/api/workspace", result.json()["version"], {"active_draft_id": "missing"}
        ).status_code
        == 404
    )
