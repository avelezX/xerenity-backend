"""
FastAPI pricing endpoints.

The CurveManager is created as a singleton at module level.
It gets initialized on the first /pricing/curves/build call.
"""
import QuantLib as ql
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException

from pricing.curves.curve_manager import CurveManager
from pricing.data.market_data import MarketDataLoader
from pricing.instruments.ndf import NdfPricer
from pricing.instruments.ibr_swap import IbrSwapPricer
from pricing.instruments.tes_bond import TesBondPricer
from pricing.instruments.xccy_swap import XccySwapPricer, validate_amortization_schedule
from pricing.portfolio import PortfolioEngine
from utilities.date_functions import datetime_to_ql

from server.pricing_api.schemas import (
    BuildCurvesRequest,
    BumpRequest,
    NdfRequest,
    NdfPnlRequest,
    IbrSwapRequest,
    TesBondRequest,
    TesBondSpreadRequest,
    TesBondCarryRequest,
    TesPortfolioBatchRequest,
    XccySwapRequest,
    XccyPnlRequest,
    AmortizationValidateRequest,
    PortfolioRepriceRequest,
)

router = APIRouter(prefix="/pricing", tags=["pricing"])

# Singleton instances
_cm: CurveManager | None = None
_loader: MarketDataLoader | None = None
_tes_catalog: Optional[dict] = None


def _get_cm() -> CurveManager:
    """Get or create the CurveManager singleton."""
    global _cm
    if _cm is None:
        _cm = CurveManager()
    return _cm


def _get_loader() -> MarketDataLoader:
    """Get or create the MarketDataLoader singleton."""
    global _loader
    if _loader is None:
        _loader = MarketDataLoader()
    return _loader


def _ensure_curves_built() -> None:
    """Raise HTTPException if no curves have been built."""
    cm = _get_cm()
    if cm.ibr_curve is None and cm.sofr_curve is None:
        raise HTTPException(
            status_code=400,
            detail="Curves not built. Call POST /pricing/curves/build first.",
        )


def _parse_date(s: str) -> ql.Date:
    """Parse an ISO date string (YYYY-MM-DD) into a QuantLib Date."""
    dt = datetime.strptime(s, "%Y-%m-%d")
    return datetime_to_ql(dt)


def _get_tes_catalog() -> dict:
    """
    Fetch and cache the TES bond catalog from the database.

    Returns:
        dict mapping bond name to bond info dict.
    """
    global _tes_catalog
    if _tes_catalog is None:
        loader = _get_loader()
        df = loader.fetch_tes_bond_info()
        if df.empty:
            _tes_catalog = {}
        else:
            _tes_catalog = {}
            for _, row in df.iterrows():
                _tes_catalog[row["name"]] = {
                    "name": row["name"],
                    "issue_date": row["emision"].strftime("%Y-%m-%d") if hasattr(row["emision"], "strftime") else str(row["emision"]),
                    "maturity_date": row["maduracion"].strftime("%Y-%m-%d") if hasattr(row["maduracion"], "strftime") else str(row["maduracion"]),
                    "coupon_rate": float(row["cupon"]),
                    "currency": row["moneda"],
                }
    return _tes_catalog


def _refresh_tes_catalog() -> dict:
    """Force refresh of the TES bond catalog from the database."""
    global _tes_catalog
    _tes_catalog = None
    return _get_tes_catalog()


def _resolve_bond_params(
    bond_name: Optional[str],
    issue_date: Optional[str],
    maturity_date: Optional[str],
    coupon_rate: Optional[float],
) -> tuple[str, str, float]:
    """
    Resolve bond parameters from catalog lookup or explicit values.

    Args:
        bond_name: Optional bond name for catalog lookup.
        issue_date: Optional explicit issue date.
        maturity_date: Optional explicit maturity date.
        coupon_rate: Optional explicit coupon rate.

    Returns:
        Tuple of (issue_date_str, maturity_date_str, coupon_rate).

    Raises:
        HTTPException: If bond not found or required fields missing.
    """
    if bond_name:
        catalog = _get_tes_catalog()
        if bond_name not in catalog:
            raise HTTPException(
                400,
                f"Bond '{bond_name}' not found in catalog. "
                f"Available: {list(catalog.keys())[:10]}...",
            )
        bond_info = catalog[bond_name]
        issue_date = issue_date or bond_info["issue_date"]
        maturity_date = maturity_date or bond_info["maturity_date"]
        coupon_rate = coupon_rate if coupon_rate is not None else bond_info["coupon_rate"]
    else:
        if not issue_date or not maturity_date or coupon_rate is None:
            raise HTTPException(
                400,
                "Provide either bond_name for catalog lookup, "
                "or issue_date + maturity_date + coupon_rate.",
            )

    return issue_date, maturity_date, coupon_rate


# ── Curve Endpoints ──


@router.post("/curves/build")
def build_curves(req: BuildCurvesRequest = None):
    """Build or rebuild all curves from latest market data."""
    cm = _get_cm()
    loader = _get_loader()
    results = cm.build_all(loader)
    return {"status": "ok", "curves": results, "full_status": cm.status()}


@router.get("/curves/status")
def curves_status():
    """Get current curve build status and node values."""
    return _get_cm().status()


@router.post("/curves/bump")
def bump_curve(req: BumpRequest):
    """Bump a curve (parallel shift or single node)."""
    _ensure_curves_built()
    cm = _get_cm()

    if req.node and req.rate_pct is not None:
        if req.curve == "ibr":
            cm.set_ibr_node(req.node, req.rate_pct)
        elif req.curve == "sofr":
            cm.set_sofr_node(int(req.node), req.rate_pct)
        else:
            raise HTTPException(400, f"Unknown curve: {req.curve}")
        return {"status": "node_set", "curve": req.curve, "node": req.node, "rate_pct": req.rate_pct}

    elif req.bps is not None:
        if req.curve == "ibr":
            cm.bump_ibr(req.bps)
        elif req.curve == "sofr":
            cm.bump_sofr(req.bps)
        else:
            raise HTTPException(400, f"Unknown curve: {req.curve}")
        return {"status": "bumped", "curve": req.curve, "bps": req.bps}

    raise HTTPException(400, "Provide either (node + rate_pct) or bps")


@router.post("/curves/reset")
def reset_curves():
    """Reset all curves to original market values."""
    _get_cm().reset_to_market()
    return {"status": "reset"}


# ── NDF Endpoints ──


@router.post("/ndf")
def price_ndf(req: NdfRequest):
    """Price a USD/COP NDF."""
    _ensure_curves_built()
    cm = _get_cm()
    ndf = NdfPricer(cm)
    mat = _parse_date(req.maturity_date)

    if req.use_market_forward and req.market_forward is not None:
        result = ndf.price_from_market_points(
            notional_usd=req.notional_usd,
            strike=req.strike,
            maturity_date=mat,
            market_forward=req.market_forward,
            direction=req.direction,
            spot=req.spot,
        )
    else:
        result = ndf.price(
            notional_usd=req.notional_usd,
            strike=req.strike,
            maturity_date=mat,
            direction=req.direction,
            spot=req.spot,
        )

    # Convert datetime to string for JSON
    if "maturity" in result and hasattr(result["maturity"], "isoformat"):
        result["maturity"] = result["maturity"].isoformat()

    return result


@router.get("/ndf/implied-curve")
def ndf_implied_curve():
    """Get implied forward curve vs market forwards."""
    _ensure_curves_built()
    cm = _get_cm()
    loader = _get_loader()
    ndf = NdfPricer(cm)

    cop_fwd = loader.fetch_cop_forwards()
    if cop_fwd.empty:
        raise HTTPException(404, "No COP forward data available")

    df = ndf.implied_curve(cop_fwd)
    return df.to_dict(orient="records")


@router.post("/ndf/pnl")
def ndf_pnl(req: NdfPnlRequest):
    """
    P&L from inception for an NDF, decomposed into FX and rate components.

    At trade inception the NDF was at-market (NPV=0). The current NPV
    is attributed to FX spot movement vs interest rate curve changes.
    """
    _ensure_curves_built()
    cm = _get_cm()
    ndf = NdfPricer(cm)

    result = ndf.pnl_inception(
        notional_usd=req.notional_usd,
        strike=req.strike,
        maturity_date=_parse_date(req.maturity_date),
        direction=req.direction,
        spot=req.spot,
        fx_inception=req.fx_inception,
    )

    if "maturity" in result and hasattr(result["maturity"], "isoformat"):
        result["maturity"] = result["maturity"].isoformat()

    return result


# ── IBR Swap Endpoints ──


@router.post("/ibr-swap")
def price_ibr_swap(req: IbrSwapRequest):
    """Price an IBR OIS swap."""
    _ensure_curves_built()
    cm = _get_cm()
    ibr = IbrSwapPricer(cm)

    if req.tenor_years is not None:
        tenor = ql.Period(req.tenor_years, ql.Years)
        result = ibr.price(req.notional, tenor, req.fixed_rate, req.pay_fixed, req.spread)
    elif req.maturity_date is not None:
        mat = _parse_date(req.maturity_date)
        result = ibr.price(req.notional, mat, req.fixed_rate, req.pay_fixed, req.spread)
    else:
        raise HTTPException(400, "Provide either tenor_years or maturity_date")

    return result


@router.get("/ibr/par-curve")
def ibr_par_curve():
    """Get IBR par swap rate curve for standard tenors."""
    _ensure_curves_built()
    cm = _get_cm()
    ibr = IbrSwapPricer(cm)
    df = ibr.par_curve()
    return df.to_dict(orient="records")


# ── TES Bond Endpoints ──


@router.post("/tes-bond")
def price_tes_bond(req: TesBondRequest):
    """
    Price a TES bond with full analytics.

    Supports catalog lookup via bond_name or explicit parameters.
    When include_cashflows=true, returns the full coupon schedule with
    dates, amounts, discount factors, and present values.
    Also includes carry/roll-down and Z-spread analytics.
    """
    _ensure_curves_built()
    cm = _get_cm()
    if cm.tes_curve is None:
        raise HTTPException(400, "TES curve not built. Provide bond data via /curves/build.")

    issue_date, maturity_date, coupon_rate = _resolve_bond_params(
        req.bond_name, req.issue_date, req.maturity_date, req.coupon_rate,
    )

    tes = TesBondPricer(cm)
    result = tes.analytics(
        issue_date=_parse_date(issue_date),
        maturity_date=_parse_date(maturity_date),
        coupon_rate=coupon_rate,
        market_clean_price=req.market_clean_price,
        face_value=req.face_value,
        include_cashflows=req.include_cashflows,
    )

    # Serialize datetime fields
    if "maturity" in result and hasattr(result["maturity"], "isoformat"):
        result["maturity"] = result["maturity"].isoformat()
    if "carry" in result and isinstance(result["carry"], dict):
        if "horizon_date" in result["carry"] and hasattr(result["carry"]["horizon_date"], "isoformat"):
            result["carry"]["horizon_date"] = result["carry"]["horizon_date"].isoformat()
    if "cashflows" in result:
        for cf in result["cashflows"]:
            if "date" in cf and hasattr(cf["date"], "isoformat"):
                cf["date"] = cf["date"].isoformat()

    return result


# ── TES Bond Catalog ──


@router.get("/tes/catalog")
def tes_catalog():
    """
    Return the active COLTES bond catalog from the database.

    Returns all active bonds with name, coupon, issue/maturity dates, currency.
    """
    catalog = _get_tes_catalog()
    bonds = list(catalog.values())
    return {"count": len(bonds), "bonds": bonds}


@router.post("/tes/catalog/refresh")
def tes_catalog_refresh():
    """Force refresh of the TES bond catalog from the database."""
    catalog = _refresh_tes_catalog()
    bonds = list(catalog.values())
    return {"count": len(bonds), "bonds": bonds, "status": "refreshed"}


# ── TES Bond Spread Analytics ──


@router.post("/tes-bond/spread")
def tes_bond_spread(req: TesBondSpreadRequest):
    """
    Compute spread-to-curve analytics for a TES bond.

    Returns yield spread and Z-spread relative to the TES curve.
    """
    _ensure_curves_built()
    cm = _get_cm()
    if cm.tes_curve is None:
        raise HTTPException(400, "TES curve not built.")

    issue_date, maturity_date, coupon_rate = _resolve_bond_params(
        req.bond_name, req.issue_date, req.maturity_date, req.coupon_rate,
    )

    tes = TesBondPricer(cm)
    result = tes.spread_to_curve(
        issue_date=_parse_date(issue_date),
        maturity_date=_parse_date(maturity_date),
        coupon_rate=coupon_rate,
        market_clean_price=req.market_clean_price,
        face_value=req.face_value,
    )

    return result


# ── TES Bond Carry/Roll-Down ──


@router.post("/tes-bond/carry")
def tes_bond_carry(req: TesBondCarryRequest):
    """
    Compute carry and roll-down analysis for a TES bond.

    Returns coupon carry, roll-down, and total carry over the specified horizon.
    """
    _ensure_curves_built()
    cm = _get_cm()
    if cm.tes_curve is None:
        raise HTTPException(400, "TES curve not built.")

    issue_date, maturity_date, coupon_rate = _resolve_bond_params(
        req.bond_name, req.issue_date, req.maturity_date, req.coupon_rate,
    )

    tes = TesBondPricer(cm)
    result = tes.carry_rolldown(
        issue_date=_parse_date(issue_date),
        maturity_date=_parse_date(maturity_date),
        coupon_rate=coupon_rate,
        horizon_days=req.horizon_days,
        market_clean_price=req.market_clean_price,
        face_value=req.face_value,
    )

    if "horizon_date" in result and hasattr(result["horizon_date"], "isoformat"):
        result["horizon_date"] = result["horizon_date"].isoformat()

    return result


# ── TES Portfolio Batch Reprice ──


@router.post("/tes-bond/portfolio")
def tes_portfolio_reprice(req: TesPortfolioBatchRequest):
    """
    Batch reprice a portfolio of TES bond positions.

    Returns analytics for each position and portfolio-level summary.
    """
    _ensure_curves_built()
    cm = _get_cm()
    if cm.tes_curve is None:
        raise HTTPException(400, "TES curve not built.")

    resolved_positions = []
    for i, pos in enumerate(req.positions):
        issue_date, maturity_date, coupon_rate = _resolve_bond_params(
            pos.bond_name, pos.issue_date, pos.maturity_date, pos.coupon_rate,
        )
        resolved_positions.append({
            "bond_name": pos.bond_name,
            "issue_date": issue_date,
            "maturity_date": maturity_date,
            "coupon_rate": coupon_rate,
            "notional": pos.notional,
            "market_clean_price": pos.market_clean_price,
            "direction": pos.direction,
        })

    tes = TesBondPricer(cm)
    results = tes.batch_reprice(resolved_positions)

    total_npv = sum(r["position_npv"] for r in results)
    total_dv01 = sum(r["position_dv01"] for r in results)

    # Serialize carry dates
    for r in results:
        if r.get("carry") and isinstance(r["carry"], dict):
            if "horizon_date" in r["carry"] and hasattr(r["carry"]["horizon_date"], "isoformat"):
                r["carry"]["horizon_date"] = r["carry"]["horizon_date"].isoformat()

    return {
        "positions": results,
        "portfolio_summary": {
            "total_positions": len(results),
            "total_npv": round(total_npv, 2),
            "total_dv01": round(total_dv01, 6),
        },
    }


# ── Cross-Currency Swap Endpoints ──


@router.post("/xccy-swap")
def price_xccy_swap(req: XccySwapRequest):
    """Price a USD/COP cross-currency swap with optional amortization."""
    _ensure_curves_built()
    cm = _get_cm()
    xccy = XccySwapPricer(cm)

    result = xccy.price(
        notional_usd=req.notional_usd,
        start_date=_parse_date(req.start_date),
        maturity_date=_parse_date(req.maturity_date),
        xccy_basis_bps=req.xccy_basis_bps,
        pay_usd=req.pay_usd,
        fx_initial=req.fx_initial,
        cop_spread_bps=req.cop_spread_bps,
        usd_spread_bps=req.usd_spread_bps,
        amortization_type=req.amortization_type,
        amortization_schedule=req.amortization_schedule,
    )

    for key in ("start_date", "maturity_date"):
        if key in result and hasattr(result[key], "isoformat"):
            result[key] = result[key].isoformat()

    return result


@router.post("/xccy-swap/pnl")
def xccy_pnl(req: XccyPnlRequest):
    """
    P&L from inception for an XCCY swap, decomposed into FX and rate components.
    """
    _ensure_curves_built()
    cm = _get_cm()
    xccy = XccySwapPricer(cm)

    result = xccy.pnl_inception(
        notional_usd=req.notional_usd,
        start_date=_parse_date(req.start_date),
        maturity_date=_parse_date(req.maturity_date),
        xccy_basis_bps=req.xccy_basis_bps,
        pay_usd=req.pay_usd,
        fx_initial=req.fx_initial,
        cop_spread_bps=req.cop_spread_bps,
        usd_spread_bps=req.usd_spread_bps,
        amortization_type=req.amortization_type,
        amortization_schedule=req.amortization_schedule,
    )

    for key in ("start_date", "maturity_date"):
        if key in result and hasattr(result[key], "isoformat"):
            result[key] = result[key].isoformat()

    return result


# ── Amortization Validation ──


@router.post("/amortization/validate")
def amortization_validate(req: AmortizationValidateRequest):
    """
    Validate an amortization schedule for consistency.

    Checks that factors are between 0 and 1, non-increasing, and start at 1.0.
    Returns validation result with any warnings or errors.
    """
    return validate_amortization_schedule(req.schedule_factors)


# ── Derivative Portfolio Batch Reprice ──


@router.post("/portfolio/reprice")
def portfolio_reprice(req: PortfolioRepriceRequest):
    """
    Batch reprice a portfolio of derivative positions (NDF, XCCY, IBR swap).

    Returns per-position NPV, P&L decomposition, and DV01, plus
    portfolio-level aggregates.

    DV01 is optimized: curves are bumped once and all positions repriced,
    instead of bumping per position. This reduces curve rebuilds from
    4*N to 3 total passes.
    """
    _ensure_curves_built()
    cm = _get_cm()
    engine = PortfolioEngine(cm)

    # Convert Pydantic models to dicts
    positions = [p.model_dump(exclude_none=True) for p in req.positions]

    result = engine.reprice_portfolio(
        positions=positions,
        include_pnl=req.include_pnl,
        include_dv01=req.include_dv01,
        dv01_bump_bps=req.dv01_bump_bps,
    )

    return result
