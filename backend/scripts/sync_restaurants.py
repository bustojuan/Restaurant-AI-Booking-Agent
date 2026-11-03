"""Refresh local OSM catalog without dialing, touching favorites or deleting drafts."""

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from app.db.session import Database
from app.migrate import upgrade
from app.providers.overpass import DEFAULT_ENDPOINT, REGIONS, OverpassRestaurantProvider
from app.services.catalog import import_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=["all", *REGIONS], default="all")
    parser.add_argument("--cache-dir", type=Path, default=Path("data"))
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--force", action="store_true", help="Refresh even if less than 24 hours old")
    parser.add_argument("--offline", action="store_true", help="Only import existing snapshots")
    args = parser.parse_args()
    settings = get_settings()
    records, counts = [], {}
    for region in REGIONS if args.region == "all" else [args.region]:
        batch = OverpassRestaurantProvider(region, args.cache_dir, endpoint=args.endpoint).records(
            force=args.force, offline=args.offline
        )
        counts[region] = len(batch)
        records.extend(batch)
    upgrade(settings.database_url)
    db = Database(settings.database_url)
    try:
        stats = import_catalog(db, records)
    finally:
        db.engine.dispose()
    # Counts only: never log phone numbers, user configuration or credentials.
    print(
        json.dumps(
            {"source": "OpenStreetMap", "license": "ODbL-1.0", "regions": counts, **stats}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
