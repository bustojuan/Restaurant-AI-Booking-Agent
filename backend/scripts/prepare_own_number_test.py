"""Prepare a clearly labelled fixture pointing ONLY to an explicitly allowlisted own number.

This script creates no external connections and makes no calls.
"""

import argparse
import re
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.db.session import Database
from app.models import Restaurant
from app.schemas import BookingCreate
from app.services.bookings import create_booking

parser = argparse.ArgumentParser(
    description="Preparar una ficha de prueba para un número propio; no realiza llamadas"
)
parser.add_argument("--prepare-own-number-fixture", action="store_true", required=True)
parser.parse_args()
settings = get_settings()
if len(settings.telephony_allowed_numbers) != 1:
    raise SystemExit(
        "Configura exactamente un número propio en TELEPHONY_ALLOWED_NUMBERS para esta primera prueba"
    )
phone = settings.telephony_allowed_numbers[0]
if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
    raise SystemExit("El número propio debe usar formato E.164")
db = Database(settings.database_url)
try:
    with db.transaction(write=True) as session:
        identifier = f"own-number-test-{uuid4()}"
        restaurant = Restaurant(
            id=identifier,
            source="own-number-test",
            external_id=identifier,
            name="PRUEBA EN NÚMERO PROPIO [NO ES UN RESTAURANTE REAL]",
            municipality="Madrid",
            region="Madrid",
            latitude=40.4168,
            longitude=-3.7038,
            phone=phone,
            is_simulated=True,
            cuisine_types=["other"],
            establishment_types=["other"],
        )
        session.add(restaurant)
        session.flush()
        future = datetime.now(ZoneInfo("Europe/Madrid")) + timedelta(days=14)
        result = create_booking(
            session,
            BookingCreate(
                configuration={
                    "customer_name": "Cliente de prueba autorizado",
                    "contact_phone": phone,
                    "requested_date": future.date(),
                    "preferred_time": "21:00",
                    "adults": 2,
                },
                restaurant_ids=[restaurant.id],
            ),
        )
    print(
        f"Borrador de prueba preparado: booking_id={result.id}, version={result.version}. No se ha realizado ninguna llamada."
    )
finally:
    db.engine.dispose()
