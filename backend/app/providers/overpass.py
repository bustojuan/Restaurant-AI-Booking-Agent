"""Manual, cached OpenStreetMap discovery; never called by browsing or booking."""

import json
import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from pydantic import HttpUrl, TypeAdapter, ValidationError

from app.providers.restaurants import CUISINES, DIETARY_OPTIONS, RestaurantRecord

REGIONS = {"Madrid": "ES-MD", "Navarra": "ES-NC"}
DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
ATTRIBUTION = "© OpenStreetMap contributors"
LICENSE_URL = "https://www.openstreetmap.org/copyright"
_http_url = TypeAdapter(HttpUrl)


def query_for(region: str) -> str:
    iso = REGIONS[region]
    return (
        "[out:json][timeout:90][maxsize:134217728];"
        f'area["ISO3166-2"="{iso}"]["boundary"="administrative"]["admin_level"="4"]->.region;'
        'nwr["amenity"~"^(restaurant|fast_food)$"]["name"](area.region);out center tags;'
    )


def text(value) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def website(value) -> str | None:
    value = text(value)
    if not value:
        return None
    if "://" not in value and re.match(r"^[\w.-]+\.[a-z]{2,}([/:]|$)", value, re.IGNORECASE):
        value = "https://" + value
    try:
        url = _http_url.validate_python(value)
        if url.username or url.password:
            return None
        return str(url)
    except ValidationError:
        return None


def parse_element(element: dict, region: str) -> RestaurantRecord | None:
    tags = element.get("tags", {})
    kind, identifier = element.get("type"), element.get("id")
    if not isinstance(tags, dict) or kind not in {"node", "way", "relation"}:
        return None
    if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0:
        return None
    if tags.get("amenity") not in {"restaurant", "fast_food"} or not text(tags.get("name")):
        return None
    if any(tags.get(key) in {"yes", "true", "1"} for key in ("disused", "abandoned", "demolished")):
        return None
    point = element if kind == "node" else element.get("center", {})
    try:
        lat, lon = float(point["lat"]), float(point["lon"])
        if not math.isfinite(lat) or not math.isfinite(lon):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    # Explicit tag mappings only. A burger is an establishment type, not proof of American cuisine.
    raw_cuisines = {v.strip().lower() for v in (text(tags.get("cuisine")) or "").split(";") if v.strip()}
    aliases = {
        "sushi": "japanese",
        "ramen": "japanese",
        "tapas": "spanish",
        "navarra": "navarrese",
        "navarran": "navarrese",
    }
    cuisines = {aliases.get(v, v) for v in raw_cuisines}
    cuisines = cuisines.intersection(CUISINES)
    establishments = {"fast_food"} if tags["amenity"] == "fast_food" else set()
    for tag, category in {
        "pizza": "pizzeria",
        "burger": "burger",
        "steak_house": "steakhouse",
        "barbecue": "grill",
        "seafood": "seafood",
    }.items():
        if tag in raw_cuisines:
            establishments.add(category)
    if "pizza" in raw_cuisines:
        cuisines.add("italian")
    street = text(tags.get("addr:street")) or text(tags.get("addr:place"))
    number = text(tags.get("addr:housenumber"))
    address = text(tags.get("addr:full")) or (", ".join(v for v in [street, number] if v) if street else None)
    try:
        return RestaurantRecord(
            id=f"osm-{kind}-{identifier}",
            source="openstreetmap",
            external_id=f"{kind}/{identifier}",
            name=text(tags.get("name")),
            region=region,
            municipality=next(
                (
                    text(tags.get(key))
                    for key in ("addr:city", "addr:town", "addr:municipality", "addr:village")
                    if text(tags.get(key))
                ),
                "",
            ),
            latitude=lat,
            longitude=lon,
            address=address,
            postal_code=text(tags.get("addr:postcode")),
            phone=text(tags.get("contact:phone")) or text(tags.get("phone")),
            website_url=website(tags.get("contact:website")) or website(tags.get("website")),
            cuisine_types=sorted(cuisines) or ["other"],
            establishment_types=sorted(establishments) or ["other"],
            dietary_options=[key for key in DIETARY_OPTIONS if tags.get(f"diet:{key}") in {"yes", "only"}],
        )
    except ValidationError:
        return None


class OverpassRestaurantProvider:
    def __init__(
        self,
        region: str,
        cache_dir: Path,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        client: httpx.Client | None = None,
    ):
        if region not in REGIONS:
            raise ValueError("Supported regions: Madrid, Navarra")
        url = httpx.URL(endpoint)
        if url.scheme != "https" or not url.host or url.userinfo or url.fragment:
            raise ValueError("Overpass requires an HTTPS endpoint")
        self.region, self.cache_dir, self.endpoint, self.client = region, cache_dir, endpoint, client

    def records(self, *, force: bool = False, offline: bool = False) -> list[RestaurantRecord]:
        path = self.cache_dir / f"overpass-{self.region.lower()}.json"
        cached = None
        if path.exists():
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
                if (
                    isinstance(candidate, dict)
                    and candidate.get("region") == self.region
                    and candidate.get("schema_version") == 1
                ):
                    fetched = datetime.fromisoformat(candidate["fetched_at"])
                    if offline or (
                        not force and timedelta(0) <= datetime.now(UTC) - fetched < timedelta(days=1)
                    ):
                        cached = candidate["response"]
            except (ValueError, TypeError, KeyError):
                pass
        if offline and cached is None:
            raise ValueError(f"No usable offline snapshot for {self.region}")
        payload = cached if cached is not None else self._download()
        if (
            not isinstance(payload, dict)
            or payload.get("remark")
            or not isinstance(payload.get("elements"), list)
        ):
            raise ValueError("Incomplete/invalid Overpass response; existing catalog preserved")
        records = {}
        for element in payload["elements"]:
            record = parse_element(element, self.region) if isinstance(element, dict) else None
            if record:
                records[record.id] = record
        if not records:
            raise ValueError(f"No named restaurants in {self.region}; snapshot was not imported")
        if cached is None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            snapshot = {
                "schema_version": 1,
                "region": self.region,
                "fetched_at": datetime.now(UTC).isoformat(),
                "endpoint": self.endpoint,
                "query": query_for(self.region),
                "attribution": ATTRIBUTION,
                "license": "ODbL-1.0",
                "license_url": LICENSE_URL,
                "response": payload,
            }
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
        return list(records.values())

    def _download(self):
        if self.client is not None:
            return self._request(self.client)
        with httpx.Client(
            timeout=120,
            follow_redirects=False,
            headers={"User-Agent": "BARIA-Desktop/0.1 (manual regional catalog refresh)"},
        ) as client:
            return self._request(client)

    def _request(self, client: httpx.Client):
        # One regional request, bounded download, no retry storm and no requests while browsing.
        with client.stream("POST", self.endpoint, data={"data": query_for(self.region)}) as response:
            response.raise_for_status()
            buffer = bytearray()
            for chunk in response.iter_bytes():
                buffer.extend(chunk)
                if len(buffer) > 50_000_000:
                    raise ValueError("Overpass response exceeded the 50 MB download limit")
            return json.loads(buffer)
