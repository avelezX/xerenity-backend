"""
Backfill historical FNC internal coffee reference prices to xerenity.coffee_prices.

Source: fnc_precio_interno_diario.csv (8,493 daily rows from 2003 to present)
Target: xerenity.coffee_prices (fuente='FNC', tipo_precio='precio_interno_carga')

Behavior:
- Filters rows where precio_interno_carga is not null
- Inserts in batches of 500 with Prefer: resolution=ignore-duplicates
  (ON CONFLICT DO NOTHING -- does not overwrite rows already present)
- Prints progress per batch
- Prints total inserted at the end
"""

import json
import os
import math
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env.local")

SUPABASE_URL = os.getenv("XTY_URL")
SUPABASE_KEY = os.getenv("XTY_TOKEN")
COLLECTOR_BEARER = os.getenv("COLLECTOR_BEARER")

TABLE = "coffee_prices"
FUENTE = "FNC"
TIPO_PRECIO = "precio_interno_carga"
CSV_PATH = "fnc_precio_interno_diario.csv"
BATCH_SIZE = 500

db = requests.Session()
db.headers.update({
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {COLLECTOR_BEARER}",
    "Content-Type": "application/json",
    "Accept-Profile": "xerenity",
    "Content-Profile": "xerenity",
    "Prefer": "return=minimal",
})


def fetch_existing_fechas() -> set[str]:
    """Fetch all fechas already in the DB for (FNC, precio_interno_carga)."""
    existing: set[str] = set()
    page_size = 1000
    offset = 0
    while True:
        headers = {"Range-Unit": "items", "Range": f"{offset}-{offset + page_size - 1}"}
        resp = db.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}"
            f"?fuente=eq.{FUENTE}&tipo_precio=eq.{TIPO_PRECIO}&select=fecha",
            headers=headers,
        )
        if resp.status_code not in (200, 206):
            print(f"  fetch existing error: {resp.status_code} {resp.text[:200]}")
            break
        rows = resp.json()
        if not rows:
            break
        existing.update(r["fecha"] for r in rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return existing


def load_rows() -> list[dict]:
    df = pd.read_csv(CSV_PATH)
    df = df[df["precio_interno_carga"].notna()].copy()
    # Drop duplicate fechas -- PostgREST ignore-duplicates does not handle
    # intra-batch conflicts; the whole batch rolls back on the first 23505.
    before = len(df)
    df = df.drop_duplicates(subset=["fecha"], keep="first")
    if len(df) < before:
        print(f"  Dropped {before - len(df)} duplicate fecha row(s) from CSV")
    df["precio_interno_carga"] = df["precio_interno_carga"].astype(int)
    return [
        {
            "fecha": str(row["fecha"]),
            "fuente": FUENTE,
            "tipo_precio": TIPO_PRECIO,
            "valor": int(row["precio_interno_carga"]),
            "unidad": "COP",
        }
        for _, row in df.iterrows()
    ]


def insert_batch(batch: list[dict]) -> int:
    resp = db.post(f"{SUPABASE_URL}/rest/v1/{TABLE}", data=json.dumps(batch))
    if resp.status_code in (200, 201):
        return len(batch)
    print(f"  batch error: {resp.status_code} {resp.text[:200]}")
    return 0


def main():
    print("FNC Historical Backfill")
    print("=" * 50)

    all_rows = load_rows()
    csv_total = len(all_rows)
    print(f"  CSV rows (non-null precio_interno_carga): {csv_total}")

    print("  Fetching existing fechas from Supabase...")
    existing = fetch_existing_fechas()
    print(f"  Existing fechas in DB: {len(existing)}")

    rows = [r for r in all_rows if r["fecha"] not in existing]
    to_insert = len(rows)
    skipped_already = csv_total - to_insert
    print(f"  Already in DB (skipped): {skipped_already}")
    print(f"  To insert: {to_insert}")

    if to_insert == 0:
        print("\nNothing to backfill. Done.")
        return

    num_batches = math.ceil(to_insert / BATCH_SIZE)
    print(f"  Batch size: {BATCH_SIZE} -- {num_batches} batches")
    print(f"  Insert range: {rows[0]['fecha']} -> {rows[-1]['fecha']}")
    print()

    inserted_total = 0
    for i in range(0, to_insert, BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        inserted = insert_batch(batch)
        inserted_total += inserted
        print(f"  Batch {batch_num:>3}/{num_batches}: inserted {inserted}/{len(batch)}")

    print()
    print(f"Done. Total inserted: {inserted_total} / {to_insert}")


if __name__ == "__main__":
    main()
