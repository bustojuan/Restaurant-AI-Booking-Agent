from sqlalchemy import select

from app.models import BookingRequest, BookingRestaurant, Restaurant, now
from app.providers.restaurants import RestaurantRecord


def import_catalog(db, records: list[RestaurantRecord]) -> dict[str, int]:
    """Atomic upsert by immutable source identity. Never delete selected/favorite rows."""
    stats = {"created": 0, "updated": 0, "unchanged": 0, "protected_active": 0}
    if len({(r.source, r.external_id) for r in records}) != len(records):
        raise ValueError("Duplicate source identity in catalog")
    with db.transaction(write=True) as session:
        existing = {(r.source, r.external_id): r for r in session.scalars(select(Restaurant))}
        protected = set(
            session.scalars(
                select(BookingRestaurant.restaurant_id)
                .join(BookingRequest)
                .where(BookingRequest.status.in_(["RUNNING", "WAITING_FOR_USER", "READY"]))
            )
        )
        for record in records:
            values = record.model_dump(mode="json")
            row = existing.get((record.source, record.external_id))
            if row is None:
                if session.get(Restaurant, record.id) is not None:
                    raise ValueError("Catalog ID collision")
                row = Restaurant(**values)
                session.add(row)
                existing[(record.source, record.external_id)] = row
                stats["created"] += 1
            elif row.id in protected:
                stats["protected_active"] += 1
            elif any(getattr(row, key) != value for key, value in values.items() if key != "id"):
                for key, value in values.items():
                    if key != "id":
                        setattr(row, key, value)
                row.updated_at = now()
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1
    return stats
