"""
SOFR Variable-Rate USD Loan pricer.

Prices USD loans indexed to SOFR using the CurveManager infrastructure
for forward rate projection and discounting.

Structure:
  - Rate: SOFR (from curve forward rates) + client spread
  - Day count: Actual/360 (USD standard)
  - Amortization: French (annuity), linear, or bullet
  - Grace periods: capital, interest, or both
  - Currency: USD
  - Spread is additive over SOFR in percent (e.g., 1.50 = 1.50%)

Conventions:
  - All amounts in USD
  - SOFR forward rates extracted from CurveManager.sofr_handle
  - Discounting with SOFR curve (USD risk-free)
  - Day count: Actual/360 (market standard for USD floating)
  - For COP-equivalent NPV, multiply by cm.fx_spot

Integration:
  - Same CurveManager pattern as IbrLoanPricer and XccySwapPricer
  - Settled periods use historical SOFR rates from db_info
  - Future periods use forward rates from the SOFR curve
"""
import QuantLib as ql
import pandas as pd
from datetime import datetime
from utilities.date_functions import datetime_to_ql, ql_to_datetime

# Periodicity mappings (English names for USD loans)
PERIODICITY_MONTHS = {
    "Annual": 12,
    "Semiannual": 6,
    "Quarterly": 3,
    "Monthly": 1,
    # Spanish aliases for compatibility
    "Anual": 12,
    "Semestral": 6,
    "Trimestral": 3,
    "Mensual": 1,
}

PERIODICITY_FRACTION = {
    "Annual": 1.0,
    "Semiannual": 0.5,
    "Quarterly": 0.25,
    "Monthly": 1 / 12,
    "Anual": 1.0,
    "Semestral": 0.5,
    "Trimestral": 0.25,
    "Mensual": 1 / 12,
}

# SOFR tenor key per periodicity (for historical lookups)
PERIODICITY_SOFR_KEY = {
    "Annual": "sofr_12m",
    "Semiannual": "sofr_6m",
    "Quarterly": "sofr_3m",
    "Monthly": "sofr_1m",
    "Anual": "sofr_12m",
    "Semestral": "sofr_6m",
    "Trimestral": "sofr_3m",
    "Mensual": "sofr_1m",
}

# Amortization types
AMORTIZATION_TYPES = ("french", "linear", "bullet")

# Grace types
GRACE_TYPES = (None, "capital", "interest", "ambos")


class SofrLoanPricer:
    """
    Prices USD SOFR-indexed loans using the CurveManager infrastructure.

    Requires CurveManager with SOFR curve built.
    """

    def __init__(self, curve_manager):
        self.cm = curve_manager
        # USD calendar
        self.calendar = ql.UnitedStates(ql.UnitedStates.FederalReserve)
        # Standard USD day count
        self.day_counter = ql.Actual360()

    def _build_schedule(self, start_date, maturity_date, periodicity):
        """Build payment schedule from start to maturity."""
        period = ql.Period(PERIODICITY_MONTHS[periodicity], ql.Months)
        return ql.Schedule(
            start_date, maturity_date,
            period,
            self.calendar,
            ql.ModifiedFollowing, ql.ModifiedFollowing,
            ql.DateGeneration.Forward, False,
        )

    def _get_sofr_rate(self, period_start, period_end, periodicity, historical_rates=None):
        """
        Get the SOFR rate for a period.

        For settled periods: looks up historical rate from db_info.
        For future periods: extracts forward rate from the SOFR curve.

        Returns:
            SOFR rate as decimal (e.g., 0.045 for 4.5%)
        """
        eval_date = ql.Settings.instance().evaluationDate
        sofr_ref = self.cm.sofr_handle.currentLink().referenceDate()
        curve_floor = max(eval_date, sofr_ref)

        if period_start < curve_floor and historical_rates is not None:
            sofr_key = PERIODICITY_SOFR_KEY.get(periodicity)
            if sofr_key is not None:
                p_start_dt = ql_to_datetime(period_start)
                hist_df = historical_rates
                if not hist_df.empty and sofr_key in hist_df.columns:
                    idx = hist_df["date"].sub(pd.Timestamp(p_start_dt)).abs().idxmin()
                    rate_pct = hist_df.at[idx, sofr_key]
                    if rate_pct is not None and not pd.isna(rate_pct):
                        return rate_pct / 100.0
            # Fallback: try generic 'rate' column (from us_reference_rates)
            if historical_rates is not None and not historical_rates.empty and 'rate' in historical_rates.columns:
                p_start_dt = ql_to_datetime(period_start)
                idx = historical_rates["date"].sub(pd.Timestamp(p_start_dt)).abs().idxmin()
                rate_val = historical_rates.at[idx, 'rate']
                if rate_val is not None and not pd.isna(rate_val):
                    return rate_val / 100.0
            return None

        # Future period — use forward rate from SOFR curve
        fwd_start = period_start if period_start >= sofr_ref else sofr_ref
        if period_end <= sofr_ref:
            # Fully settled period with no historical data — can't compute
            return None
        fwd_rate = self.cm.sofr_handle.forwardRate(
            fwd_start, period_end, self.day_counter, ql.Simple
        ).rate()
        return fwd_rate

    def _compute_interest_factor(self, rate_total_pct, period_start, period_end):
        """
        Compute interest factor using Actual/360 day count (USD standard).

        Returns:
            Interest factor as decimal (multiply by balance to get interest)
        """
        rate_decimal = rate_total_pct / 100.0
        tau = self.day_counter.yearFraction(period_start, period_end)
        return rate_decimal * tau

    def _prepare_historical_rates(self, db_info):
        """Prepare historical rates DataFrame from db_info."""
        if db_info is None:
            return None
        df = pd.DataFrame(db_info) if not isinstance(db_info, pd.DataFrame) else db_info.copy()
        if "fecha" in df.columns:
            df["date"] = pd.to_datetime(df["fecha"])
        elif "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        else:
            return None
        return df

    def cashflows(
        self,
        notional_usd: float,
        start_date,
        maturity_date,
        spread_pct: float,
        periodicity: str = "Quarterly",
        amortization_type: str = "linear",
        grace_type: str = None,
        grace_period: int = 0,
        min_period_rate: float = None,
        db_info: dict = None,
    ) -> list:
        """
        Full cashflow schedule for a SOFR-indexed USD loan.

        Args:
            notional_usd: Original loan amount (USD)
            start_date: Loan origination date
            maturity_date: Final payment date
            spread_pct: Client spread over SOFR in percent (e.g., 1.50)
            periodicity: Payment frequency (Quarterly, Monthly, etc.)
            amortization_type: 'french', 'linear', or 'bullet'
            grace_type: None, 'capital', 'interest', or 'ambos'
            grace_period: Number of grace periods
            min_period_rate: Floor on total rate (SOFR + spread) in percent
            db_info: Historical SOFR rates (from us_reference_rates)

        Returns:
            List of dicts, one per period, with USD amounts and optionally COP equivalents
        """
        if isinstance(start_date, datetime):
            start_date = datetime_to_ql(start_date)
        if isinstance(maturity_date, datetime):
            maturity_date = datetime_to_ql(maturity_date)

        if periodicity not in PERIODICITY_MONTHS:
            raise ValueError(f"Invalid periodicity '{periodicity}'. Valid: {list(PERIODICITY_MONTHS.keys())}")
        if amortization_type not in AMORTIZATION_TYPES:
            raise ValueError(f"Invalid amortization_type. Valid: {list(AMORTIZATION_TYPES)}")
        if grace_type not in GRACE_TYPES:
            raise ValueError(f"Invalid grace_type. Valid: {list(GRACE_TYPES)}")

        grace_period = int(grace_period) if grace_period else 0
        grace_period_principal = grace_period if grace_type in ("capital", "ambos") else 0
        grace_period_interest = grace_period if grace_type in ("interest", "ambos") else 0

        schedule = self._build_schedule(start_date, maturity_date, periodicity)
        dates = list(schedule)
        n_periods = len(dates) - 1

        if n_periods <= 0:
            raise ValueError("Schedule has no periods.")

        capital_periods = n_periods - grace_period_principal
        if capital_periods <= 0:
            raise ValueError(f"Grace period ({grace_period_principal}) >= total periods ({n_periods})")

        historical_rates = self._prepare_historical_rates(db_info)
        eval_date = ql.Settings.instance().evaluationDate
        sofr_ref = self.cm.sofr_handle.currentLink().referenceDate()

        # French annuity — need an estimated rate for initial payment calc
        if amortization_type == "french":
            # Use first period forward rate as estimate
            est_start = dates[0] if dates[0] >= sofr_ref else sofr_ref
            est_rate = self.cm.sofr_handle.forwardRate(
                est_start, dates[1], self.day_counter, ql.Simple
            ).rate() * 100.0 + spread_pct
            est_factor = self._compute_interest_factor(est_rate, dates[0], dates[1])
            if abs(est_factor) < 1e-10:
                annuity = notional_usd / capital_periods
            else:
                annuity = notional_usd * est_factor / (1 - (1 + est_factor) ** (-capital_periods))

        fx_spot = self.cm.fx_spot

        rows = []
        balance = notional_usd
        accumulated_interest = 0.0

        for i in range(n_periods):
            p_start = dates[i]
            p_end = dates[i + 1]

            # Status
            if p_end <= eval_date:
                status = "settled"
            elif p_start < eval_date:
                status = "current"
            else:
                status = "future"

            # SOFR rate
            sofr_rate = self._get_sofr_rate(p_start, p_end, periodicity, historical_rates)
            if sofr_rate is None:
                sofr_rate_pct = 0.0
            else:
                sofr_rate_pct = sofr_rate * 100.0

            # Total rate = SOFR + spread, floored by min_period_rate
            rate_total_pct = sofr_rate_pct + spread_pct
            if min_period_rate is not None:
                rate_total_pct = max(rate_total_pct, min_period_rate)

            # Interest
            interest_factor = self._compute_interest_factor(rate_total_pct, p_start, p_end)

            if i < grace_period_interest:
                interest_amount = 0.0
                accumulated_interest += balance * interest_factor
            else:
                if accumulated_interest > 0 and i == grace_period_interest:
                    balance += accumulated_interest
                    accumulated_interest = 0.0
                interest_amount = balance * interest_factor

            # Principal
            if i < grace_period_principal:
                principal_amount = 0.0
            else:
                if amortization_type == "linear":
                    principal_amount = notional_usd / capital_periods
                    if i == n_periods - 1:
                        principal_amount = balance
                elif amortization_type == "bullet":
                    principal_amount = balance if i == n_periods - 1 else 0.0
                elif amortization_type == "french":
                    principal_amount = annuity - interest_amount
                    if i == n_periods - 1:
                        principal_amount = balance

            payment = interest_amount + principal_amount
            ending_balance = balance - principal_amount

            # Discount factor (SOFR curve)
            if p_end > sofr_ref:
                df = self.cm.sofr_handle.discount(p_end)
            else:
                df = 1.0

            pv_usd = payment * df
            pv_cop = pv_usd * fx_spot if fx_spot else None

            rows.append({
                "period": i + 1,
                "date_start": ql_to_datetime(p_start).strftime("%Y-%m-%d"),
                "date_end": ql_to_datetime(p_end).strftime("%Y-%m-%d"),
                "beginning_balance_usd": round(balance, 2),
                "sofr_rate_pct": round(sofr_rate_pct, 6),
                "spread_pct": spread_pct,
                "rate_total_pct": round(rate_total_pct, 6),
                "interest_usd": round(interest_amount, 2),
                "principal_usd": round(principal_amount, 2),
                "payment_usd": round(payment, 2),
                "ending_balance_usd": round(ending_balance, 2),
                "discount_factor": round(df, 8),
                "pv_usd": round(pv_usd, 2),
                "pv_cop": round(pv_cop, 2) if pv_cop is not None else None,
                "status": status,
            })

            balance = ending_balance

        return rows

    def price(
        self,
        notional_usd: float,
        start_date,
        maturity_date,
        spread_pct: float,
        periodicity: str = "Quarterly",
        amortization_type: str = "linear",
        grace_type: str = None,
        grace_period: int = 0,
        min_period_rate: float = None,
        db_info: dict = None,
    ) -> dict:
        """
        Price a SOFR-indexed USD loan and return analytics.

        Returns:
            dict with: npv_usd, npv_cop, notional_usd, spread_pct,
                       principal_outstanding_usd, accrued_interest_usd,
                       duration, tenor_years, avg_rate_pct, fx_spot
        """
        cfs = self.cashflows(
            notional_usd=notional_usd,
            start_date=start_date,
            maturity_date=maturity_date,
            spread_pct=spread_pct,
            periodicity=periodicity,
            amortization_type=amortization_type,
            grace_type=grace_type,
            grace_period=grace_period,
            min_period_rate=min_period_rate,
            db_info=db_info,
        )

        future_cfs = [cf for cf in cfs if cf["status"] != "settled"]
        npv_usd = sum(cf["pv_usd"] for cf in future_cfs)
        fx_spot = self.cm.fx_spot
        npv_cop = npv_usd * fx_spot if fx_spot else None

        principal_outstanding = future_cfs[0]["beginning_balance_usd"] if future_cfs else 0.0

        # Accrued interest
        accrued_interest = 0.0
        eval_date = ql.Settings.instance().evaluationDate
        for cf in cfs:
            if cf["status"] == "current":
                p_start = datetime_to_ql(datetime.strptime(cf["date_start"], "%Y-%m-%d"))
                p_end = datetime_to_ql(datetime.strptime(cf["date_end"], "%Y-%m-%d"))
                total_days = self.day_counter.dayCount(p_start, p_end)
                elapsed_days = self.day_counter.dayCount(p_start, eval_date)
                if total_days > 0:
                    accrued_interest = cf["interest_usd"] * elapsed_days / total_days
                break

        # Duration (Macaulay)
        total_pv = sum(cf["pv_usd"] for cf in future_cfs) if future_cfs else 0.0
        eval_dt = ql_to_datetime(eval_date)
        duration = 0.0
        if total_pv > 0:
            for cf in future_cfs:
                cf_date = datetime.strptime(cf["date_end"], "%Y-%m-%d")
                t_years = (cf_date - eval_dt).days / 365.25
                duration += t_years * cf["pv_usd"] / total_pv

        # Tenor
        if cfs:
            last_date = datetime.strptime(cfs[-1]["date_end"], "%Y-%m-%d")
            tenor_years = (last_date - eval_dt).days / 365.25
        else:
            tenor_years = 0.0

        # Weighted average rate
        if future_cfs:
            total_balance = sum(cf["beginning_balance_usd"] for cf in future_cfs)
            avg_rate = (sum(cf["rate_total_pct"] * cf["beginning_balance_usd"] for cf in future_cfs)
                        / total_balance) if total_balance > 0 else 0.0
        else:
            avg_rate = 0.0

        return {
            "npv_usd": round(npv_usd, 2),
            "npv_cop": round(npv_cop, 2) if npv_cop is not None else None,
            "notional_usd": notional_usd,
            "spread_pct": spread_pct,
            "principal_outstanding_usd": round(principal_outstanding, 2),
            "accrued_interest_usd": round(accrued_interest, 2),
            "total_value_usd": round(principal_outstanding + accrued_interest, 2),
            "duration": round(duration, 4),
            "tenor_years": round(tenor_years, 4),
            "avg_rate_pct": round(avg_rate, 4),
            "periods_total": len(cfs),
            "periods_remaining": len(future_cfs),
            "fx_spot": fx_spot,
            "amortization_type": amortization_type,
            "periodicity": periodicity,
            "currency": "USD",
        }

    def par_spread(
        self,
        notional_usd: float,
        start_date,
        maturity_date,
        periodicity: str = "Quarterly",
        amortization_type: str = "linear",
        grace_type: str = None,
        grace_period: int = 0,
        min_period_rate: float = None,
        db_info: dict = None,
    ) -> float:
        """
        Find the spread over SOFR that makes NPV = notional (fair spread).

        Returns:
            Par spread in percent
        """
        from scipy.optimize import brentq

        def objective(spread):
            result = self.price(
                notional_usd=notional_usd,
                start_date=start_date,
                maturity_date=maturity_date,
                spread_pct=spread,
                periodicity=periodicity,
                amortization_type=amortization_type,
                grace_type=grace_type,
                grace_period=grace_period,
                min_period_rate=min_period_rate,
                db_info=db_info,
            )
            return result["npv_usd"] - notional_usd

        par = brentq(objective, -20.0, 20.0, xtol=0.0001)
        return round(par, 4)

    def dv01(
        self,
        notional_usd: float,
        start_date,
        maturity_date,
        spread_pct: float,
        periodicity: str = "Quarterly",
        amortization_type: str = "linear",
        grace_type: str = None,
        grace_period: int = 0,
        min_period_rate: float = None,
        db_info: dict = None,
        bump_bps: float = 1.0,
    ) -> dict:
        """
        DV01: sensitivity of USD NPV to a 1bp parallel shift in the SOFR curve.

        Returns:
            dict with dv01_usd, dv01_cop, bump_bps, base_npv_usd
        """
        common_args = dict(
            notional_usd=notional_usd,
            start_date=start_date,
            maturity_date=maturity_date,
            spread_pct=spread_pct,
            periodicity=periodicity,
            amortization_type=amortization_type,
            grace_type=grace_type,
            grace_period=grace_period,
            min_period_rate=min_period_rate,
            db_info=db_info,
        )

        base = self.price(**common_args)
        base_npv = base["npv_usd"]

        self.cm.bump_sofr(bump_bps)
        bumped = self.price(**common_args)
        bumped_npv = bumped["npv_usd"]
        self.cm.bump_sofr(-bump_bps)

        fx = self.cm.fx_spot
        dv01_usd = bumped_npv - base_npv

        return {
            "dv01_usd": round(dv01_usd, 2),
            "dv01_cop": round(dv01_usd * fx, 2) if fx else None,
            "bump_bps": bump_bps,
            "base_npv_usd": base_npv,
            "bumped_npv_usd": bumped_npv,
        }
