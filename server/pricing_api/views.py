"""
Django views for pricing API.
Wraps the pricing module for the existing Django WSGI server.

The CurveManager is created as a module-level singleton.
It gets initialized on the first /pricing/curves/build call.
"""
import json
import QuantLib as ql
from datetime import datetime
from typing import Optional
from django.views.decorators.csrf import csrf_exempt
from server.main_server import responseHttpOk, responseHttpError

from pricing.curves.curve_manager import CurveManager
from pricing.data.market_data import MarketDataLoader
from pricing.instruments.ndf import NdfPricer
from pricing.instruments.ibr_swap import IbrSwapPricer
from pricing.instruments.tes_bond import TesBondPricer
from pricing.instruments.xccy_swap import XccySwapPricer, validate_amortization_schedule
from pricing.portfolio import PortfolioEngine
from utilities.date_functions import datetime_to_ql

# Module-level singletons
_cm = None
_loader = None

# In-memory TES bond catalog (populated from DB on first call)
_tes_catalog: Optional[dict] = None


def _get_cm():
    global _cm
    if _cm is None:
        _cm = CurveManager()
    return _cm


def _get_loader():
    global _loader
    if _loader is None:
        _loader = MarketDataLoader()
    return _loader


def _parse_date(s: str) -> ql.Date:
    """Parse an ISO date string (YYYY-MM-DD) into a QuantLib Date."""
    dt = datetime.strptime(s, "%Y-%m-%d")
    return datetime_to_ql(dt)


def _ensure_curves():
    """Ensure at least one curve has been built."""
    cm = _get_cm()
    if cm.ibr_curve is None and cm.sofr_curve is None:
        return responseHttpError("Curves not built. Call POST /pricing_build first.", 400)
    return None


def _serialize(result: dict) -> dict:
    """Convert datetime objects to strings for JSON serialization."""
    out = {}
    for k, v in result.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, float):
            out[k] = round(v, 6) if abs(v) < 1e12 else round(v, 2)
        elif isinstance(v, list):
            out[k] = [_serialize(item) if isinstance(item, dict) else item for item in v]
        elif isinstance(v, dict):
            out[k] = _serialize(v)
        else:
            out[k] = v
    return out


def _get_tes_catalog() -> dict:
    """
    Fetch and cache the TES bond catalog from the database.

    Returns:
        dict mapping bond name to bond info dict with keys:
        name, emision, maduracion, cupon, moneda.
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
    """Force refresh of the TES bond catalog from DB."""
    global _tes_catalog
    _tes_catalog = None
    return _get_tes_catalog()


def _resolve_bond_params(body: dict) -> tuple[str, str, float]:
    """
    Resolve bond parameters from either explicit values or catalog lookup.

    If bond_name is provided in body, looks up the bond in the catalog.
    Otherwise requires issue_date, maturity_date, coupon_rate in body.

    Args:
        body: Request body dict.

    Returns:
        Tuple of (issue_date_str, maturity_date_str, coupon_rate).

    Raises:
        ValueError: If bond not found or required fields missing.
    """
    bond_name = body.get("bond_name")

    if bond_name:
        catalog = _get_tes_catalog()
        if bond_name not in catalog:
            raise ValueError(
                f"Bond '{bond_name}' not found in catalog. "
                f"Available: {list(catalog.keys())[:10]}..."
            )
        bond_info = catalog[bond_name]
        issue_date = body.get("issue_date") or bond_info["issue_date"]
        maturity_date = body.get("maturity_date") or bond_info["maturity_date"]
        coupon_rate = body.get("coupon_rate") if body.get("coupon_rate") is not None else bond_info["coupon_rate"]
    else:
        issue_date = body.get("issue_date")
        maturity_date = body.get("maturity_date")
        coupon_rate = body.get("coupon_rate")
        if not issue_date or not maturity_date or coupon_rate is None:
            raise ValueError(
                "Provide either bond_name for catalog lookup, "
                "or issue_date + maturity_date + coupon_rate."
            )

    return issue_date, maturity_date, coupon_rate


# ── Curve Endpoints ──

@csrf_exempt
def pricing_build(request):
    """Build or rebuild all curves from latest market data."""
    cm = _get_cm()
    loader = _get_loader()
    results = cm.build_all(loader)
    return responseHttpOk({"status": "ok", "curves": results, "full_status": cm.status()})


@csrf_exempt
def pricing_status(request):
    """Get current curve build status and node values."""
    return responseHttpOk(_get_cm().status())


@csrf_exempt
def pricing_bump(request):
    """Bump a curve (parallel shift or single node)."""
    err = _ensure_curves()
    if err:
        return err

    body = json.loads(request.body) if request.body else {}
    cm = _get_cm()
    curve = body.get("curve")
    node = body.get("node")
    rate_pct = body.get("rate_pct")
    bps = body.get("bps")

    if node and rate_pct is not None:
        if curve == "ibr":
            cm.set_ibr_node(node, rate_pct)
        elif curve == "sofr":
            cm.set_sofr_node(int(node), rate_pct)
        else:
            return responseHttpError(f"Unknown curve: {curve}", 400)
        return responseHttpOk({"status": "node_set", "curve": curve, "node": node, "rate_pct": rate_pct})

    elif bps is not None:
        if curve == "ibr":
            cm.bump_ibr(bps)
        elif curve == "sofr":
            cm.bump_sofr(bps)
        else:
            return responseHttpError(f"Unknown curve: {curve}", 400)
        return responseHttpOk({"status": "bumped", "curve": curve, "bps": bps})

    return responseHttpError("Provide either (node + rate_pct) or bps", 400)


@csrf_exempt
def pricing_reset(request):
    """Reset all curves to original market values."""
    _get_cm().reset_to_market()
    return responseHttpOk({"status": "reset"})


# ── NDF ──

@csrf_exempt
def pricing_ndf(request):
    """Price a USD/COP NDF."""
    err = _ensure_curves()
    if err:
        return err

    body = json.loads(request.body)
    cm = _get_cm()
    ndf = NdfPricer(cm)
    mat = _parse_date(body["maturity_date"])

    if body.get("use_market_forward") and body.get("market_forward"):
        result = ndf.price_from_market_points(
            notional_usd=body["notional_usd"],
            strike=body["strike"],
            maturity_date=mat,
            market_forward=body["market_forward"],
            direction=body.get("direction", "buy"),
            spot=body.get("spot"),
        )
    else:
        result = ndf.price(
            notional_usd=body["notional_usd"],
            strike=body["strike"],
            maturity_date=mat,
            direction=body.get("direction", "buy"),
            spot=body.get("spot"),
        )

    return responseHttpOk(_serialize(result))


@csrf_exempt
def pricing_ndf_implied_curve(request):
    """Get implied forward curve vs market forwards."""
    err = _ensure_curves()
    if err:
        return err

    cm = _get_cm()
    loader = _get_loader()
    ndf = NdfPricer(cm)
    cop_fwd = loader.fetch_cop_forwards()

    if cop_fwd.empty:
        return responseHttpError("No COP forward data available", 404)

    df = ndf.implied_curve(cop_fwd)
    return responseHttpOk(df.to_dict(orient="records"))


# ── IBR Swap ──

@csrf_exempt
def pricing_ibr_swap(request):
    """Price an IBR OIS swap."""
    err = _ensure_curves()
    if err:
        return err

    body = json.loads(request.body)
    cm = _get_cm()
    ibr = IbrSwapPricer(cm)

    if "tenor_years" in body and body["tenor_years"]:
        tenor = ql.Period(int(body["tenor_years"]), ql.Years)
        result = ibr.price(
            body["notional"], tenor, body["fixed_rate"],
            body.get("pay_fixed", True), body.get("spread", 0.0),
        )
    elif "maturity_date" in body and body["maturity_date"]:
        mat = _parse_date(body["maturity_date"])
        result = ibr.price(
            body["notional"], mat, body["fixed_rate"],
            body.get("pay_fixed", True), body.get("spread", 0.0),
        )
    else:
        return responseHttpError("Provide tenor_years or maturity_date", 400)

    return responseHttpOk(_serialize(result))


@csrf_exempt
def pricing_ibr_par_curve(request):
    """Get IBR par swap rate curve for standard tenors."""
    err = _ensure_curves()
    if err:
        return err

    cm = _get_cm()
    ibr = IbrSwapPricer(cm)
    df = ibr.par_curve()
    records = df.to_dict(orient="records")
    return responseHttpOk(records)


# ── TES Bond ──

@csrf_exempt
def pricing_tes_bond(request):
    """
    Price a TES bond with full analytics.

    Supports catalog lookup via bond_name or explicit parameters.
    When include_cashflows=true, the response includes the full
    coupon schedule with dates, amounts, discount factors, and PVs.
    Also includes carry/roll-down analytics and Z-spread.
    """
    err = _ensure_curves()
    if err:
        return err

    cm = _get_cm()
    if cm.tes_curve is None:
        return responseHttpError("TES curve not built", 400)

    body = json.loads(request.body)

    try:
        issue_date, maturity_date, coupon_rate = _resolve_bond_params(body)
    except ValueError as e:
        return responseHttpError(str(e), 400)

    tes = TesBondPricer(cm)
    result = tes.analytics(
        issue_date=_parse_date(issue_date),
        maturity_date=_parse_date(maturity_date),
        coupon_rate=coupon_rate,
        market_clean_price=body.get("market_clean_price"),
        face_value=body.get("face_value", 100.0),
        include_cashflows=body.get("include_cashflows", False),
    )

    return responseHttpOk(_serialize(result))


# ── TES Bond Catalog ──

@csrf_exempt
def pricing_tes_catalog(request):
    """
    Return the active COLTES bond catalog from the database.

    GET: Returns all active bonds with name, coupon, issue/maturity dates, currency.
    POST with {"refresh": true}: Forces a refresh of the cached catalog.
    """
    if request.method == "POST":
        body = json.loads(request.body) if request.body else {}
        if body.get("refresh"):
            catalog = _refresh_tes_catalog()
        else:
            catalog = _get_tes_catalog()
    else:
        catalog = _get_tes_catalog()

    bonds = list(catalog.values())
    return responseHttpOk({"count": len(bonds), "bonds": bonds})


# ── TES Bond Spread Analytics ──

@csrf_exempt
def pricing_tes_spread(request):
    """
    Compute spread-to-curve analytics for a TES bond.

    Returns yield spread and Z-spread relative to the TES curve.
    Requires market_clean_price.
    """
    err = _ensure_curves()
    if err:
        return err

    cm = _get_cm()
    if cm.tes_curve is None:
        return responseHttpError("TES curve not built", 400)

    body = json.loads(request.body)

    try:
        issue_date, maturity_date, coupon_rate = _resolve_bond_params(body)
    except ValueError as e:
        return responseHttpError(str(e), 400)

    market_clean_price = body.get("market_clean_price")
    if market_clean_price is None:
        return responseHttpError("market_clean_price is required for spread analytics.", 400)

    tes = TesBondPricer(cm)
    try:
        result = tes.spread_to_curve(
            issue_date=_parse_date(issue_date),
            maturity_date=_parse_date(maturity_date),
            coupon_rate=coupon_rate,
            market_clean_price=market_clean_price,
            face_value=body.get("face_value", 100.0),
        )
    except Exception as e:
        return responseHttpError(f"Spread calculation failed: {str(e)}", 400)

    return responseHttpOk(_serialize(result))


# ── TES Bond Carry/Roll-Down ──

@csrf_exempt
def pricing_tes_carry(request):
    """
    Compute carry and roll-down analysis for a TES bond.

    Returns coupon carry, roll-down, and total carry over the specified
    horizon (default 30 days).
    """
    err = _ensure_curves()
    if err:
        return err

    cm = _get_cm()
    if cm.tes_curve is None:
        return responseHttpError("TES curve not built", 400)

    body = json.loads(request.body)

    try:
        issue_date, maturity_date, coupon_rate = _resolve_bond_params(body)
    except ValueError as e:
        return responseHttpError(str(e), 400)

    tes = TesBondPricer(cm)
    try:
        result = tes.carry_rolldown(
            issue_date=_parse_date(issue_date),
            maturity_date=_parse_date(maturity_date),
            coupon_rate=coupon_rate,
            horizon_days=body.get("horizon_days", 30),
            market_clean_price=body.get("market_clean_price"),
            face_value=body.get("face_value", 100.0),
        )
    except Exception as e:
        return responseHttpError(f"Carry calculation failed: {str(e)}", 400)

    return responseHttpOk(_serialize(result))


# ── TES Portfolio Batch Reprice ──

@csrf_exempt
def pricing_tes_portfolio(request):
    """
    Batch reprice a portfolio of TES bond positions.

    Each position can use bond_name for catalog lookup or explicit parameters.
    Returns analytics for each position including position-level NPV and DV01.
    """
    err = _ensure_curves()
    if err:
        return err

    cm = _get_cm()
    if cm.tes_curve is None:
        return responseHttpError("TES curve not built", 400)

    body = json.loads(request.body)
    positions_raw = body.get("positions", [])

    if not positions_raw:
        return responseHttpError("No positions provided.", 400)

    # Resolve bond_name lookups for each position
    resolved_positions = []
    for i, pos in enumerate(positions_raw):
        try:
            issue_date, maturity_date, coupon_rate = _resolve_bond_params(pos)
        except ValueError as e:
            return responseHttpError(f"Position {i}: {str(e)}", 400)

        resolved_positions.append({
            "bond_name": pos.get("bond_name"),
            "issue_date": issue_date,
            "maturity_date": maturity_date,
            "coupon_rate": coupon_rate,
            "notional": pos.get("notional", 100.0),
            "market_clean_price": pos.get("market_clean_price"),
            "direction": pos.get("direction", "long"),
        })

    tes = TesBondPricer(cm)
    try:
        results = tes.batch_reprice(resolved_positions)
    except Exception as e:
        return responseHttpError(f"Portfolio reprice failed: {str(e)}", 400)

    # Portfolio-level aggregation
    total_npv = sum(r["position_npv"] for r in results)
    total_dv01 = sum(r["position_dv01"] for r in results)

    serialized_results = [_serialize(r) for r in results]

    return responseHttpOk({
        "positions": serialized_results,
        "portfolio_summary": {
            "total_positions": len(results),
            "total_npv": round(total_npv, 2),
            "total_dv01": round(total_dv01, 6),
        },
    })


# ── Xccy Swap ──

@csrf_exempt
def pricing_xccy_swap(request):
    """Price a USD/COP cross-currency swap with optional amortization."""
    err = _ensure_curves()
    if err:
        return err

    body = json.loads(request.body)
    cm = _get_cm()
    xccy = XccySwapPricer(cm)

    result = xccy.price(
        notional_usd=body["notional_usd"],
        start_date=_parse_date(body["start_date"]),
        maturity_date=_parse_date(body["maturity_date"]),
        xccy_basis_bps=body.get("xccy_basis_bps", 0.0),
        pay_usd=body.get("pay_usd", True),
        fx_initial=body.get("fx_initial"),
        cop_spread_bps=body.get("cop_spread_bps", 0.0),
        usd_spread_bps=body.get("usd_spread_bps", 0.0),
        amortization_type=body.get("amortization_type", "bullet"),
        amortization_schedule=body.get("amortization_schedule"),
    )

    return responseHttpOk(_serialize(result))


# ── NDF P&L Decomposition ──

@csrf_exempt
def pricing_ndf_pnl(request):
    """P&L from inception for an NDF, decomposed into FX and rate components."""
    err = _ensure_curves()
    if err:
        return err

    body = json.loads(request.body)
    cm = _get_cm()
    ndf = NdfPricer(cm)

    result = ndf.pnl_inception(
        notional_usd=body["notional_usd"],
        strike=body["strike"],
        maturity_date=_parse_date(body["maturity_date"]),
        direction=body.get("direction", "buy"),
        spot=body.get("spot"),
        fx_inception=body.get("fx_inception"),
    )

    return responseHttpOk(_serialize(result))


# ── XCCY P&L Decomposition ──

@csrf_exempt
def pricing_xccy_pnl(request):
    """P&L from inception for an XCCY swap, decomposed into FX and rate components."""
    err = _ensure_curves()
    if err:
        return err

    body = json.loads(request.body)
    cm = _get_cm()
    xccy = XccySwapPricer(cm)

    result = xccy.pnl_inception(
        notional_usd=body["notional_usd"],
        start_date=_parse_date(body["start_date"]),
        maturity_date=_parse_date(body["maturity_date"]),
        xccy_basis_bps=body.get("xccy_basis_bps", 0.0),
        pay_usd=body.get("pay_usd", True),
        fx_initial=body.get("fx_initial"),
        cop_spread_bps=body.get("cop_spread_bps", 0.0),
        usd_spread_bps=body.get("usd_spread_bps", 0.0),
        amortization_type=body.get("amortization_type", "bullet"),
        amortization_schedule=body.get("amortization_schedule"),
    )

    return responseHttpOk(_serialize(result))


# ── Amortization Validation ──

@csrf_exempt
def pricing_amortization_validate(request):
    """Validate an amortization schedule for consistency."""
    body = json.loads(request.body)
    schedule_factors = body.get("schedule_factors", [])

    if not schedule_factors:
        return responseHttpError("schedule_factors is required", 400)

    result = validate_amortization_schedule(schedule_factors)
    return responseHttpOk(result)


# ── Derivative Portfolio Batch Reprice ──

@csrf_exempt
def pricing_portfolio_reprice(request):
    """
    Batch reprice a portfolio of derivative positions (NDF, XCCY, IBR swap).

    DV01 is optimized: curves are bumped once and all positions repriced,
    instead of bumping per position.
    """
    err = _ensure_curves()
    if err:
        return err

    body = json.loads(request.body)
    positions = body.get("positions", [])

    if not positions:
        return responseHttpError("No positions provided.", 400)

    cm = _get_cm()
    engine = PortfolioEngine(cm)

    try:
        result = engine.reprice_portfolio(
            positions=positions,
            include_pnl=body.get("include_pnl", True),
            include_dv01=body.get("include_dv01", True),
            dv01_bump_bps=body.get("dv01_bump_bps", 1.0),
        )
    except Exception as e:
        return responseHttpError(f"Portfolio reprice failed: {str(e)}", 400)

    return responseHttpOk(result)
