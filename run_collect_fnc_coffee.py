"""
Runner: Collect FNC internal coffee reference price from federaciondecafeteros.org.
Stores in xerenity.coffee_prices with fuente='FNC', tipo_precio='precio_interno_carga'.

Idempotent via UNIQUE(fecha, fuente, tipo_precio) + Prefer: merge-duplicates.

Schedule: Daily (FNC updates once per business day).
"""

import json
import os
import requests
from dotenv import load_dotenv

load_dotenv(".env.local")

from src.collectors.fnc_coffee import fetch_fnc_precio_interno

SUPABASE_URL = os.getenv("XTY_URL")
SUPABASE_KEY = os.getenv("XTY_TOKEN")
COLLECTOR_BEARER = os.getenv("COLLECTOR_BEARER")

TABLE = "coffee_prices"
FUENTE = "FNC"
TIPO_PRECIO = "precio_interno_carga"

db = requests.Session()
db.headers.update({
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {COLLECTOR_BEARER}",
    "Content-Type": "application/json",
    "Accept-Profile": "xerenity",
    "Content-Profile": "xerenity",
    "Prefer": "resolution=merge-duplicates,return=minimal",
})


def exists(fecha: str) -> bool:
    resp = db.get(
        f"{SUPABASE_URL}/rest/v1/{TABLE}"
        f"?fecha=eq.{fecha}&fuente=eq.{FUENTE}&tipo_precio=eq.{TIPO_PRECIO}"
        f"&select=fecha&limit=1"
    )
    if resp.status_code == 200 and resp.json():
        return True
    return False


def upsert_row(row: dict) -> bool:
    resp = db.post(f"{SUPABASE_URL}/rest/v1/{TABLE}", data=json.dumps([row]))
    if resp.status_code in (200, 201):
        return True
    print(f"  upsert error: {resp.status_code} {resp.text[:200]}")
    return False


def main():
    print("FNC Coffee Price Collector")
    print("=" * 50)

    data = fetch_fnc_precio_interno()
    if data is None:
        print("No data fetched from FNC. Aborting.")
        return

    fecha = data["fecha"]
    valor = data["valor"]
    print(f"  Fecha:  {fecha}")
    print(f"  Precio: ${valor:,} COP/carga")

    if exists(fecha):
        print(f"  Ya existe fila para {fecha} / {FUENTE} / {TIPO_PRECIO}, nada que insertar.")
        return

    row = {
        "fecha": fecha,
        "fuente": FUENTE,
        "tipo_precio": TIPO_PRECIO,
        "valor": valor,
        "unidad": "COP",
    }

    if upsert_row(row):
        print("  Inserted 1 row")
    else:
        print("  Failed to insert")


if __name__ == "__main__":
    main()
