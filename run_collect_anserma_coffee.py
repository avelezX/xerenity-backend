"""
Runner: Collect Anserma coffee prices from the public Google Sheet.
Stores in xerenity.coffee_prices with fuente='ANSERMA'.

Inserts 5 rows per run (one per tipo_precio). Idempotent via
UNIQUE(fecha, fuente, tipo_precio) + Prefer: merge-duplicates.

Schedule: Daily (sheet is updated once per business day).
"""

import json
import os
import requests
from dotenv import load_dotenv

load_dotenv(".env.local")

from src.collectors.anserma_coffee import fetch_anserma_prices

SUPABASE_URL = os.getenv("XTY_URL")
SUPABASE_KEY = os.getenv("XTY_TOKEN")
COLLECTOR_BEARER = os.getenv("COLLECTOR_BEARER")

TABLE = "coffee_prices"
FUENTE = "ANSERMA"

db = requests.Session()
db.headers.update({
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {COLLECTOR_BEARER}",
    "Content-Type": "application/json",
    "Accept-Profile": "xerenity",
    "Content-Profile": "xerenity",
    "Prefer": "resolution=merge-duplicates,return=minimal",
})


def count_existing(fecha: str) -> int:
    resp = db.get(
        f"{SUPABASE_URL}/rest/v1/{TABLE}"
        f"?fecha=eq.{fecha}&fuente=eq.{FUENTE}&select=tipo_precio"
    )
    if resp.status_code == 200:
        return len(resp.json())
    return 0


def upsert_rows(rows: list[dict]) -> int:
    resp = db.post(f"{SUPABASE_URL}/rest/v1/{TABLE}", data=json.dumps(rows))
    if resp.status_code in (200, 201):
        return len(rows)
    print(f"  upsert error: {resp.status_code} {resp.text[:200]}")
    return 0


def main():
    print("Anserma Coffee Prices Collector")
    print("=" * 50)

    data = fetch_anserma_prices()
    if data is None:
        print("No data fetched from Anserma. Aborting.")
        return

    fecha = data["fecha"]
    prices = data["prices"]
    print(f"  Fecha: {fecha}")
    for tipo, valor in prices.items():
        print(f"    {tipo:<28s} ${valor:,}")

    existing = count_existing(fecha)
    if existing >= len(prices):
        print(f"  Ya existen {existing} filas para {fecha} / {FUENTE}, nada que insertar.")
        return

    rows = [
        {
            "fecha": fecha,
            "fuente": FUENTE,
            "tipo_precio": tipo,
            "valor": valor,
            "unidad": "COP",
        }
        for tipo, valor in prices.items()
    ]

    inserted = upsert_rows(rows)
    print(f"  Upserted {inserted} rows")


if __name__ == "__main__":
    main()
