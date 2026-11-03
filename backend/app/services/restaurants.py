import re
import unicodedata
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BookingRestaurant, FavoriteRestaurant, Restaurant
from app.providers.restaurants import ASIAN_CUISINES
from app.schemas import RestaurantOut, RestaurantPage


def folded(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))


def distance_km(lat: float, lon: float, lat2: float, lon2: float) -> float:
    dlat, dlon = radians(lat2 - lat), radians(lon2 - lon)
    a = sin(dlat / 2) ** 2 + cos(radians(lat)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(min(1.0, a)))


def restaurant_out(
    restaurant: Restaurant, favorites: set[str], position: int | None = None, distance: float | None = None
) -> RestaurantOut:
    images = restaurant.images
    source = {}
    if restaurant.source == "openstreetmap" and re.fullmatch(
        r"(node|way|relation)/[0-9]+", restaurant.external_id
    ):
        source = {
            "source_url": f"https://www.openstreetmap.org/{restaurant.external_id}",
            "data_attribution": "© OpenStreetMap contributors · ODbL 1.0",
            "data_license_url": "https://www.openstreetmap.org/copyright",
        }
    return RestaurantOut(
        **{k: getattr(restaurant, k) for k in RestaurantOut.model_fields if hasattr(restaurant, k)},
        primary_image_url=images[0]["url"] if images else None,
        additional_images=images[1:],
        has_photo=bool(images),
        is_favorite=restaurant.id in favorites,
        selected_position=position,
        distance_km=distance,
        **source,
    )


def favorite_ids(session: Session) -> set[str]:
    return set(session.scalars(select(FavoriteRestaurant.restaurant_id)))


def search(
    session: Session,
    *,
    q: str | None = None,
    municipality: str | None = None,
    region: str | None = None,
    cuisine_types: list[str] | None = None,
    establishment_types: list[str] | None = None,
    favorites_only: bool = False,
    bbox: tuple[float, float, float, float] | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_km: float | None = None,
    min_rating: float | None = None,
    max_price: int | None = None,
    sort: str = "name",
    limit: int = 50,
    offset: int = 0,
    booking_id: str | None = None,
    catalog: str = "all",
    cuisine_group: str | None = None,
    dietary_options: list[str] | None = None,
) -> RestaurantPage:
    statement = select(Restaurant)
    if favorites_only:
        statement = statement.join(FavoriteRestaurant)
    if region:
        statement = statement.where(Restaurant.region == region)
    if catalog == "auto":
        real = select(Restaurant.id).where(Restaurant.is_simulated.is_(False))
        if region:
            real = real.where(Restaurant.region == region)
        catalog = "real" if session.scalar(real.limit(1)) else "simulated"
    if catalog in {"real", "simulated"}:
        statement = statement.where(Restaurant.is_simulated.is_(catalog == "simulated"))
    if min_rating is not None:
        statement = statement.where(Restaurant.rating >= min_rating)
    if max_price is not None:
        statement = statement.where(Restaurant.price_range <= max_price)
    if bbox:
        west, south, east, north = bbox
        statement = statement.where(
            Restaurant.longitude.between(west, east), Restaurant.latitude.between(south, north)
        )
    # Local bounded catalog; text/category/radius filtering stays provider independent.
    restaurants = session.scalars(statement).all()
    favorites = favorite_ids(session)
    positions = (
        dict(
            session.execute(
                select(BookingRestaurant.restaurant_id, BookingRestaurant.position).where(
                    BookingRestaurant.booking_id == booking_id
                )
            ).all()
        )
        if booking_id
        else {}
    )
    items = []
    for restaurant in restaurants:
        if q and folded(q) not in folded(
            " ".join([restaurant.name, restaurant.municipality, restaurant.region, restaurant.address or ""])
        ):
            continue
        if municipality and folded(municipality) != folded(restaurant.municipality):
            continue
        if cuisine_types and not set(cuisine_types).issubset(restaurant.cuisine_types):
            continue
        if establishment_types and not set(establishment_types).issubset(restaurant.establishment_types):
            continue
        if cuisine_group == "asian" and not ASIAN_CUISINES.intersection(restaurant.cuisine_types):
            continue
        if dietary_options and not set(dietary_options).issubset(restaurant.dietary_options):
            continue
        distance = (
            distance_km(latitude, longitude, restaurant.latitude, restaurant.longitude)
            if latitude is not None and longitude is not None
            else None
        )
        if radius_km is not None and distance > radius_km:
            continue
        items.append(restaurant_out(restaurant, favorites, positions.get(restaurant.id), distance))
    if sort == "distance":
        items.sort(key=lambda r: (r.distance_km, r.id))
    elif sort == "rating":
        items.sort(key=lambda r: (r.rating is None, -(r.rating or 0), r.id))
    elif sort == "price":
        items.sort(key=lambda r: (r.price_range is None, r.price_range or 0, r.id))
    else:
        items.sort(key=lambda r: (folded(r.name), r.id))
    return RestaurantPage(items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset)
