"""Image lookup is separate from restaurant discovery; no name/proximity matching."""

import json
from pathlib import Path
from typing import Protocol

from pydantic import Field, TypeAdapter

from app.schemas import Contract, ImageAsset


class RestaurantIdentity(Contract):
    source: str
    external_id: str


class ImageCatalogEntry(RestaurantIdentity):
    images: list[ImageAsset] = Field(max_length=20)


class RestaurantImageProvider(Protocol):
    def images_for(self, identity: RestaurantIdentity) -> list[ImageAsset]: ...


class NoImageProvider:
    def images_for(self, identity: RestaurantIdentity) -> list[ImageAsset]:
        return []


class VerifiedCatalogImageProvider:
    """Operator-curated rights and identity evidence; never downloads/scrapes images.

    rights_verified is an operator assertion, not automated legal verification.
    Unknown identities have no photo. Order determines the primary image.
    """

    def __init__(self, entries: list[ImageCatalogEntry]):
        self.catalog: dict[tuple[str, str], list[ImageAsset]] = {}
        for entry in entries:
            key = (entry.source, entry.external_id)
            if key in self.catalog:
                raise ValueError(f"Duplicate image catalog identity: {key}")
            self.catalog[key] = entry.images

    @classmethod
    def from_file(cls, path: str):
        entries = TypeAdapter(list[ImageCatalogEntry]).validate_python(
            json.loads(Path(path).read_text(encoding="utf-8"))
        )
        return cls(entries)

    def images_for(self, identity: RestaurantIdentity) -> list[ImageAsset]:
        return self.catalog.get((identity.source, identity.external_id), []).copy()
