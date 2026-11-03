from typing import Protocol

from pydantic import Field, HttpUrl

from app.schemas import Category, CategoryCatalog, Contract

CUISINES = {
    "italian": "Italiana",
    "spanish": "Española",
    "navarrese": "Navarra",
    "basque": "Vasca",
    "mediterranean": "Mediterránea",
    "japanese": "Japonesa",
    "chinese": "China",
    "korean": "Coreana",
    "thai": "Tailandesa",
    "indian": "India",
    "mexican": "Mexicana",
    "american": "Americana",
    "french": "Francesa",
    "peruvian": "Peruana",
    "arab": "Árabe",
    "fusion": "Fusión",
    "international": "Internacional",
    "other": "Otras",
    "asian": "Asiática",
    "vietnamese": "Vietnamita",
    "indonesian": "Indonesia",
    "malaysian": "Malasia",
    "turkish": "Turca",
    "greek": "Griega",
}
DIETARY_OPTIONS = {"vegetarian": "Vegetariano", "vegan": "Vegano", "gluten_free": "Opciones sin gluten"}
ASIAN_CUISINES = {
    "asian",
    "japanese",
    "chinese",
    "korean",
    "thai",
    "indian",
    "vietnamese",
    "indonesian",
    "malaysian",
}
ESTABLISHMENTS = {
    "fast_food": "Comida rápida",
    "burger": "Hamburguesería",
    "pizzeria": "Pizzería",
    "grill": "Asador",
    "seafood": "Marisquería",
    "steakhouse": "Steakhouse",
    "traditional": "Restaurante tradicional",
    "gastrobar": "Gastrobar",
    "fine_dining": "Alta cocina",
    "cafe": "Cafetería con comidas",
    "buffet": "Buffet",
    "other": "Otros",
}


def normalize_categories(tags: list[str], catalog: dict[str, str]) -> list[str]:
    return sorted({tag if tag in catalog else "other" for tag in tags})


def category_catalog() -> CategoryCatalog:
    return CategoryCatalog(
        cuisine_types=[Category(id=k, label=v) for k, v in CUISINES.items()],
        establishment_types=[Category(id=k, label=v) for k, v in ESTABLISHMENTS.items()],
        dietary_options=[Category(id=k, label=v) for k, v in DIETARY_OPTIONS.items()],
    )


class RestaurantRecord(Contract):
    id: str
    source: str
    external_id: str
    name: str
    municipality: str
    region: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    website_url: HttpUrl | None = None
    cuisine_types: list[str]
    establishment_types: list[str]
    dietary_options: list[str] = Field(default_factory=list)
    is_simulated: bool = False


class RestaurantProvider(Protocol):
    def records(self) -> list[RestaurantRecord]: ...


class MockRestaurantProvider:
    def records(self) -> list[RestaurantRecord]:
        # Fictional establishments; coordinates are representative town locations.
        rows = [
            (
                "madrid-1",
                "Mesa del Sol [SIMULADO]",
                "Madrid",
                "Madrid",
                40.4168,
                -3.7038,
                ["spanish", "mediterranean"],
                ["traditional"],
            ),
            (
                "madrid-2",
                "Pasta de Prueba [SIMULADO]",
                "Madrid",
                "Madrid",
                40.425,
                -3.710,
                ["italian"],
                ["pizzeria"],
            ),
            (
                "madrid-3",
                "Asador de Prueba [SIMULADO]",
                "Pozuelo",
                "Madrid",
                40.435,
                -3.813,
                ["basque", "spanish"],
                ["grill"],
            ),
            (
                "madrid-4",
                "Sakura de Prueba [SIMULADO]",
                "Alcobendas",
                "Madrid",
                40.537,
                -3.637,
                ["japanese"],
                ["traditional"],
            ),
            (
                "madrid-5",
                "Taco de Prueba [SIMULADO]",
                "Getafe",
                "Madrid",
                40.305,
                -3.732,
                ["mexican"],
                ["gastrobar"],
            ),
            (
                "navarra-1",
                "Mesa del Arga [SIMULADO]",
                "Pamplona",
                "Navarra",
                42.8125,
                -1.6458,
                ["navarrese", "spanish"],
                ["traditional"],
            ),
            (
                "navarra-2",
                "Huerta de Prueba [SIMULADO]",
                "Tudela",
                "Navarra",
                42.061,
                -1.605,
                ["navarrese"],
                ["fine_dining"],
            ),
            (
                "navarra-3",
                "Pasta del Ega [SIMULADO]",
                "Estella-Lizarra",
                "Navarra",
                42.67,
                -2.031,
                ["italian"],
                ["pizzeria"],
            ),
            (
                "navarra-4",
                "Parrilla de Prueba [SIMULADO]",
                "Tafalla",
                "Navarra",
                42.526,
                -1.675,
                ["american"],
                ["burger", "fast_food"],
            ),
            (
                "navarra-5",
                "Fusión de Prueba [SIMULADO]",
                "Olite",
                "Navarra",
                42.48,
                -1.651,
                ["fusion"],
                ["gastrobar"],
            ),
        ]
        return [
            RestaurantRecord(
                id=rid,
                source="mock",
                external_id=rid,
                name=name,
                municipality=town,
                region=region,
                latitude=lat,
                longitude=lon,
                cuisine_types=normalize_categories(cuisines, CUISINES),
                establishment_types=normalize_categories(kinds, ESTABLISHMENTS),
                is_simulated=True,
            )
            for rid, name, town, region, lat, lon, cuisines, kinds in rows
        ]
