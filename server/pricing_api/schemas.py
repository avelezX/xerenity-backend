"""Pydantic request/response models for pricing API."""
from pydantic import BaseModel, Field
from typing import Optional


class BuildCurvesRequest(BaseModel):
    target_date: Optional[str] = Field(None, description="ISO date string. None = latest.")


class BumpRequest(BaseModel):
    curve: str = Field(..., description="'ibr' or 'sofr'")
    bps: Optional[float] = Field(None, description="Parallel shift in bps")
    node: Optional[str] = Field(None, description="Tenor key (e.g., 'ibr_5y' or '60')")
    rate_pct: Optional[float] = Field(None, description="New rate in percent for the node")


class NdfRequest(BaseModel):
    notional_usd: float
    strike: float
    maturity_date: str = Field(..., description="ISO date string YYYY-MM-DD")
    direction: str = Field("buy", description="'buy' or 'sell'")
    spot: Optional[float] = None
    use_market_forward: bool = Field(False, description="Use FXEmpire forward instead of implied")
    market_forward: Optional[float] = Field(None, description="Market forward rate if use_market_forward=True")


class IbrSwapRequest(BaseModel):
    notional: float
    tenor_years: Optional[int] = Field(None, description="Tenor in years (e.g., 5)")
    maturity_date: Optional[str] = Field(None, description="ISO date or use tenor_years")
    fixed_rate: float = Field(..., description="Fixed rate as decimal (e.g., 0.095)")
    pay_fixed: bool = True
    spread: float = 0.0


class TesBondRequest(BaseModel):
    """
    Request model for TES bond pricing.

    Supports two modes:
      1. Explicit parameters: provide issue_date, maturity_date, coupon_rate.
      2. Catalog lookup: provide bond_name to auto-lookup from the TES catalog.
         When bond_name is provided, issue_date/maturity_date/coupon_rate are
         optional and will be filled from the catalog.
    """
    bond_name: Optional[str] = Field(
        None,
        description="Bond name for catalog auto-lookup (e.g., 'TFIT10040522'). "
                    "When provided, issue_date/maturity_date/coupon_rate are fetched from DB.",
    )
    issue_date: Optional[str] = Field(
        None,
        description="ISO date YYYY-MM-DD. Required unless bond_name is provided.",
    )
    maturity_date: Optional[str] = Field(
        None,
        description="ISO date YYYY-MM-DD. Required unless bond_name is provided.",
    )
    coupon_rate: Optional[float] = Field(
        None,
        description="Coupon rate as decimal (e.g., 0.07). Required unless bond_name is provided.",
    )
    market_clean_price: Optional[float] = None
    face_value: float = 100.0
    include_cashflows: bool = Field(
        False,
        description="If true, include full cashflow schedule in response.",
    )


class TesBondSpreadRequest(BaseModel):
    """Request model for TES bond spread-to-curve analytics."""
    bond_name: Optional[str] = Field(None, description="Bond name for catalog lookup.")
    issue_date: Optional[str] = None
    maturity_date: Optional[str] = None
    coupon_rate: Optional[float] = None
    market_clean_price: float = Field(..., description="Market clean price for spread calculation.")
    face_value: float = 100.0


class TesBondCarryRequest(BaseModel):
    """Request model for TES bond carry/roll-down analysis."""
    bond_name: Optional[str] = Field(None, description="Bond name for catalog lookup.")
    issue_date: Optional[str] = None
    maturity_date: Optional[str] = None
    coupon_rate: Optional[float] = None
    market_clean_price: Optional[float] = None
    face_value: float = 100.0
    horizon_days: int = Field(30, description="Horizon in calendar days for carry analysis.")


class TesPortfolioPositionRequest(BaseModel):
    """A single TES bond position for portfolio batch repricing."""
    bond_name: Optional[str] = Field(None, description="Bond name for catalog lookup.")
    issue_date: Optional[str] = None
    maturity_date: Optional[str] = None
    coupon_rate: Optional[float] = None
    notional: float = Field(100.0, description="Position notional (face value units).")
    market_clean_price: Optional[float] = None
    direction: str = Field("long", description="'long' or 'short'.")


class TesPortfolioBatchRequest(BaseModel):
    """Request model for TES portfolio batch repricing."""
    positions: list[TesPortfolioPositionRequest] = Field(
        ..., description="List of TES bond positions to reprice."
    )


class XccySwapRequest(BaseModel):
    notional_usd: float
    start_date: str
    maturity_date: str
    xccy_basis_bps: float = 0.0
    pay_usd: bool = True
    fx_initial: Optional[float] = None
    cop_spread_bps: float = 0.0
    usd_spread_bps: float = 0.0
    amortization_type: str = Field(
        "bullet",
        description="'bullet' (no amortization), 'linear', or 'custom'",
    )
    amortization_schedule: Optional[list[float]] = Field(
        None,
        description="For 'custom' amortization: list of notional factors per period "
                    "(e.g., [1.0, 1.0, 0.8, 0.6, 0.4, 0.2]). "
                    "Factor 1.0 = full notional, 0.0 = fully amortized.",
    )


class NdfPnlRequest(BaseModel):
    """Request for NDF P&L decomposition from inception."""
    notional_usd: float
    strike: float
    maturity_date: str = Field(..., description="ISO date YYYY-MM-DD")
    direction: str = Field("buy", description="'buy' or 'sell'")
    spot: Optional[float] = None
    fx_inception: Optional[float] = Field(
        None,
        description="FX spot at trade inception. If None, approximated from strike.",
    )


class XccyPnlRequest(BaseModel):
    """Request for XCCY swap P&L decomposition from inception."""
    notional_usd: float
    start_date: str
    maturity_date: str
    xccy_basis_bps: float = 0.0
    pay_usd: bool = True
    fx_initial: Optional[float] = None
    cop_spread_bps: float = 0.0
    usd_spread_bps: float = 0.0
    amortization_type: str = "bullet"
    amortization_schedule: Optional[list[float]] = None


class AmortizationValidateRequest(BaseModel):
    """Request to validate an amortization schedule."""
    schedule_factors: list[float] = Field(
        ...,
        description="List of notional factors per period "
                    "(e.g., [1.0, 1.0, 0.8, 0.6, 0.4, 0.2])",
    )


class PortfolioPositionRequest(BaseModel):
    """A single derivative position for portfolio batch repricing."""
    instrument_type: str = Field(
        ...,
        description="'ndf', 'xccy', or 'ibr_swap'",
    )
    # NDF fields
    notional_usd: Optional[float] = None
    strike: Optional[float] = None
    maturity_date: Optional[str] = None
    direction: Optional[str] = None
    spot: Optional[float] = None
    fx_inception: Optional[float] = None
    # XCCY fields
    start_date: Optional[str] = None
    xccy_basis_bps: Optional[float] = 0.0
    pay_usd: Optional[bool] = True
    fx_initial: Optional[float] = None
    cop_spread_bps: Optional[float] = 0.0
    usd_spread_bps: Optional[float] = 0.0
    amortization_type: Optional[str] = "bullet"
    amortization_schedule: Optional[list[float]] = None
    # IBR swap fields
    notional: Optional[float] = None
    tenor_years: Optional[int] = None
    fixed_rate: Optional[float] = None
    pay_fixed: Optional[bool] = True
    spread: Optional[float] = 0.0


class PortfolioRepriceRequest(BaseModel):
    """Request for batch portfolio repricing with P&L and DV01."""
    positions: list[PortfolioPositionRequest] = Field(
        ..., description="List of derivative positions to reprice."
    )
    include_pnl: bool = Field(True, description="Include P&L decomposition per position")
    include_dv01: bool = Field(True, description="Include DV01 per position and aggregate")
    dv01_bump_bps: float = Field(1.0, description="Bump size for DV01 computation")
