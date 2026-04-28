"""
run_compute_marks.py — Daily market marks snapshot

Computes all curves from the latest available data and stores one row
in market_marks (upsert by fecha). Intended to run daily at ~21:30 UTC,
after all collectors have finished (SOFR ~21:00, FXEmpire ~21:00).

Usage:
    python run_compute_marks.py             # uses today's date
    python run_compute_marks.py 2026-03-03  # specific date (backfill)

Output row in market_marks:
    fecha    | fx_spot | sofr_on | ibr (JSONB) | sofr (JSONB) | ndf (JSONB)
"""
import sys
import os
from datetime import date

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)

import QuantLib as ql

from pricing.data.market_data import MarketDataLoader
from pricing.curves.curve_manager import CurveManager


def compute_marks(target_date: str = None) -> dict:
    """
    Fetch all market data, build curves, return structured marks dict.
    target_date: ISO string or None for latest available.
    """
    loader = MarketDataLoader()
    cm = CurveManager()

    # ── Fetch ──
    # NDF forwards no longer come from FXEmpire — they're derived from
    # interest rate parity using the IBR + SOFR curves we already build.
    # See "── NDF outright forwards ──" block below.
    ibr_quotes = loader.fetch_ibr_quotes(target_date=target_date)
    sofr_df    = loader.fetch_sofr_curve(target_date=target_date)
    # Use live SET-ICAP tick here — this is the job that WRITES the mark.
    fx_spot    = loader.fetch_usdcop_spot_live(target_date=target_date)
    sofr_on    = loader.fetch_sofr_spot(target_date=target_date)

    if not ibr_quotes:
        raise RuntimeError("No IBR data available")
    if sofr_df.empty:
        raise RuntimeError("No SOFR data available")
    if fx_spot is None:
        raise RuntimeError("No FX spot available")

    # ── Build curves ──
    cm.build_ibr_curve(ibr_quotes)
    cm.build_sofr_curve(sofr_df)
    cm.set_fx_spot(fx_spot)

    # ── IBR nodes (% EA) ──
    ibr_payload = {k: round(v, 6) for k, v in cm.status()["ibr"]["nodes"].items()}

    # ── SOFR zero rates by tenor_months ──
    sofr_tenors = [1, 3, 6, 12, 18, 24, 36, 60, 84, 120, 180, 240, 360, 480, 600]
    sofr_payload = {}
    for m in sofr_tenors:
        dt = cm.valuation_date + ql.Period(m, ql.Months)
        sofr_payload[str(m)] = round(cm.sofr_zero_rate(dt) * 100, 6)

    # ── NDF outright forwards from interest rate parity ──
    # F(T) = S × DF_USD(T) / DF_COP(T) — standard textbook IRP.
    #
    # Replaces the old FXEmpire scrape entirely. The scraper had been
    # broken since 2026-03-12 and was producing absurd forward points
    # (~5x too high) because run_compute_marks kept reusing month-old
    # mid values against a fresh spot.
    #
    # Trade-off: this gives us the *theoretical* forward, not the
    # market-observed one. The difference (NDF basis) reflects
    # convertibility risk + cross-currency basis. For a portfolio
    # mark-to-model with monthly horizons that's fine; if the desk
    # later needs market basis, add a manual override layer.
    NDF_TENORS_MONTHS = [1, 2, 3, 6, 9, 12]
    ndf_payload = {}
    for months in NDF_TENORS_MONTHS:
        dt = cm.valuation_date + ql.Period(months, ql.Months)
        df_sofr = cm.sofr_discount(dt)   # USD-leg DF
        df_ibr  = cm.ibr_discount(dt)    # COP-leg DF
        f_market = fx_spot * df_sofr / df_ibr
        fwd_pts  = f_market - fx_spot
        deval_ea = (f_market / fx_spot) ** (12 / months) - 1
        ndf_payload[str(months)] = {
            "fwd_pts_cop": round(fwd_pts, 4),
            "F_market":    round(f_market, 4),
            "deval_ea":    round(deval_ea * 100, 4),
        }

    return {
        "ibr_quotes":  ibr_quotes,   # kept for fecha inference
        "fx_spot":     fx_spot,
        "sofr_on":     round(sofr_on * 100, 6) if sofr_on else None,
        "ibr":         ibr_payload,
        "sofr":        sofr_payload,
        "ndf":         ndf_payload,
        "loader":      loader,
        "target_date": target_date,
        "sofr_df":     sofr_df,
    }


def infer_fecha(marks: dict) -> str:
    """
    Determine the trading date for this marks snapshot.

    When running live (target_date=None) we always use today — individual
    data sources may have slightly different dates (e.g. SOFR closes at
    21:00 UTC so it may be yesterday's) but the snapshot represents today's
    mark set. For backfill runs, use the explicit target_date.
    """
    return marks["target_date"] or date.today().isoformat()


def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"run_compute_marks — {date.today().isoformat()}")
    print(f"  target_date: {target_date or 'latest available'}")
    print()

    # ── Compute ──
    print("  Computing curves...")
    marks = compute_marks(target_date)
    fecha = infer_fecha(marks)
    print(f"  Fecha marcas: {fecha}")
    print(f"  FX spot:      {marks['fx_spot']:,.2f} COP/USD")
    print(f"  SOFR ON:      {marks['sofr_on']:.4f}%" if marks["sofr_on"] else "  SOFR ON:      N/A")
    print(f"  IBR nodes:    {len(marks['ibr'])}")
    print(f"  SOFR tenores: {len(marks['sofr'])}")
    print(f"  NDF tenores:  {len(marks['ndf'])}")
    print()

    # ── Store ──
    print("  Storing to market_marks...")
    loader = marks["loader"]
    loader.store_marks(
        fecha=fecha,
        fx_spot=marks["fx_spot"],
        sofr_on=marks["sofr_on"],
        ibr=marks["ibr"],
        sofr=marks["sofr"],
        ndf=marks["ndf"],
    )
    print(f"  Stored OK — fecha={fecha}")
    print()
    print("Done!")


if __name__ == "__main__":
    main()
