from sqlalchemy import select

from app.db.session import Database
from app.models import Restaurant, SimulationScenario, WorkspaceState, now
from app.providers.images import RestaurantIdentity, RestaurantImageProvider
from app.providers.restaurants import MockRestaurantProvider

SCENARIOS = [
    (
        "priority-success",
        "Sin plazas, hora incompatible y confirmación",
        ["NO_AVAILABILITY", "INCOMPATIBLE_TIME", "CONFIRM"],
    ),
    ("all-full", "Todos completos", ["NO_AVAILABILITY"]),
    ("approval", "Depósito simulado que requiere aprobación", ["REQUIRES_APPROVAL"]),
    ("confirm-first", "Confirma el primer restaurante", ["CONFIRM"]),
    ("no-confirmation", "Oferta aceptable sin confirmación", ["NO_CONFIRMATION"]),
    ("timeout", "Timeout de contacto simulado", ["TIMEOUT"]),
    ("errors", "Error de contacto simulado", ["ERROR"]),
    ("missing-evidence", "Falta verificar requisitos obligatorios", ["INSUFFICIENT_INFORMATION"]),
]

SCENARIOS += [
    ("ai-incompatible", "Alternativa fuera del margen autorizado", ["INCOMPATIBLE_TIME"]),
    ("ai-valid-alternative", "Alternativa válida de 15 minutos", ["AI_VALID_ALTERNATIVE"]),
    ("ai-correction", "Corrección posterior a una hora incompatible", ["AI_CORRECTION"]),
    ("ai-ambiguous", "Respuesta ambigua sin condiciones completas", ["AI_AMBIGUOUS"]),
    ("ai-refuses", "El restaurante rechaza hablar con IA", ["AI_REFUSAL"]),
    ("ai-injection", "Intento de cambiar instrucciones internas", ["AI_INJECTION"]),
    ("ai-disconnect", "El restaurante cuelga antes de proponer", ["AI_DISCONNECT"]),
    ("ai-connection-error", "Desconexión durante la confirmación", ["AI_CONNECTION_ERROR"]),
    ("ai-incomplete-confirmation", "Confirmación aparente incompleta", ["AI_INCOMPLETE_CONFIRMATION"]),
    ("ai-interruption", "Interrupción de turno simulada, sin audio real", ["AI_INTERRUPTION"]),
]


def bootstrap(db: Database, image_provider: RestaurantImageProvider, seed_mock: bool) -> None:
    with db.transaction(write=True) as session:
        if session.get(WorkspaceState, 1) is None:
            session.add(WorkspaceState(id=1))
        for sid, name, outcomes in SCENARIOS:
            if session.get(SimulationScenario, sid) is None:
                session.add(SimulationScenario(id=sid, name=name, outcomes=outcomes))
        if seed_mock:
            for record in MockRestaurantProvider().records():
                if session.get(Restaurant, record.id) is None:
                    session.add(Restaurant(**record.model_dump(mode="json")))
        session.flush()
        # Catalog is the source of truth for media; removing an entry revokes its display on restart.
        for restaurant in session.scalars(select(Restaurant)):
            assets = image_provider.images_for(
                RestaurantIdentity(
                    source=restaurant.source,
                    external_id=restaurant.external_id,
                )
            )
            images = [asset.model_dump(mode="json") for asset in assets]
            if restaurant.images != images:
                restaurant.images, restaurant.updated_at = images, now()
