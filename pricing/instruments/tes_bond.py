"""
TES Bond pricer with full analytics.

Enhances the existing bond_structure.py with:
  - DiscountingBondEngine linked to the TES yield curve handle
  - Clean price, dirty price, accrued interest
  - Yield to maturity (YTM)
  - Duration (Macaulay and Modified)
  - Convexity, DV01, BPV
  - Cashflow schedule with dates, amounts, discount factors, PVs
  - Carry and roll-down analysis
  - Spread to curve (OAS), Z-spread
"""
import QuantLib as ql
import pandas as pd
from datetime import datetime
from typing import Optional
from scipy.optimize import brentq
from utilities.date_functions import datetime_to_ql, ql_to_datetime
from utilities.colombia_calendar import calendar_colombia
from bond_functions.tes_quant_lib_details import tes_quantlib_det


class TesBondPricer:
    """
    Prices individual TES bonds using the TES yield curve from CurveManager.

    Provides:
      - Bond creation and pricing via QuantLib DiscountingBondEngine
      - Full analytics (price, yield, duration, convexity, DV01)
      - Cashflow schedule with discount factors and present values
      - Carry and roll-down analysis
      - Z-spread computation
      - Portfolio batch pricing
    """

    def __init__(self, curve_manager) -> None:
        """
        Initialize the TES bond pricer.

        Args:
            curve_manager: CurveManager instance with TES curve built.
        """
        self.cm = curve_manager
        self.calendar = calendar_colombia()
        self.details = tes_quantlib_det

    def create_bond(
        self,
        issue_date,
        maturity_date,
        coupon_rate: float,
        face_value: float = 100.0,
    ) -> ql.FixedRateBond:
        """
        Create a QuantLib FixedRateBond for a TES bond.

        Args:
            issue_date: Bond issuance date (datetime or ql.Date)
            maturity_date: Bond maturity date (datetime or ql.Date)
            coupon_rate: Annual coupon rate as decimal (e.g., 0.07)
            face_value: Face/par value (default 100)

        Returns:
            ql.FixedRateBond with pricing engine set
        """
        if isinstance(issue_date, datetime):
            issue_date = datetime_to_ql(issue_date)
        if isinstance(maturity_date, datetime):
            maturity_date = datetime_to_ql(maturity_date)

        schedule = ql.Schedule(
            issue_date, maturity_date,
            ql.Period(ql.Annual),
            self.calendar,
            ql.Unadjusted, ql.Unadjusted,
            ql.DateGeneration.Backward,
            True,
        )

        bond = ql.FixedRateBond(
            0,
            face_value,
            schedule,
            [coupon_rate],
            ql.Actual36525(),
            ql.Unadjusted,
        )

        engine = ql.DiscountingBondEngine(self.cm.tes_handle)
        bond.setPricingEngine(engine)

        return bond

    def _get_schedule(
        self,
        issue_date: ql.Date,
        maturity_date: ql.Date,
    ) -> ql.Schedule:
        """
        Build the coupon schedule for a TES bond.

        Args:
            issue_date: Bond issuance date as ql.Date.
            maturity_date: Bond maturity date as ql.Date.

        Returns:
            ql.Schedule with annual coupon dates.
        """
        return ql.Schedule(
            issue_date, maturity_date,
            ql.Period(ql.Annual),
            self.calendar,
            ql.Unadjusted, ql.Unadjusted,
            ql.DateGeneration.Backward,
            True,
        )

    def cashflow_schedule(
        self,
        issue_date,
        maturity_date,
        coupon_rate: float,
        face_value: float = 100.0,
    ) -> list[dict]:
        """
        Generate the full cashflow schedule with discount factors and present values.

        Each cashflow entry includes the payment date, coupon amount (plus
        principal at maturity), the TES-curve discount factor to that date,
        and the present value of the cashflow.

        Args:
            issue_date: Bond issuance date (datetime or ql.Date).
            maturity_date: Bond maturity date (datetime or ql.Date).
            coupon_rate: Annual coupon rate as decimal (e.g., 0.07).
            face_value: Face/par value (default 100).

        Returns:
            List of dicts, one per cashflow, with keys:
              date, date_str, period, coupon, principal, cashflow,
              discount_factor, pv, accrual_start, accrual_end,
              accrual_days, year_fraction
        """
        if isinstance(issue_date, datetime):
            issue_date = datetime_to_ql(issue_date)
        if isinstance(maturity_date, datetime):
            maturity_date = datetime_to_ql(maturity_date)

        schedule = self._get_schedule(issue_date, maturity_date)
        day_counter = ql.Actual36525()
        valuation = self.cm.valuation_date
        dates = list(schedule)
        cashflows = []

        for i in range(1, len(dates)):
            accrual_start = dates[i - 1]
            accrual_end = dates[i]
            payment_date = accrual_end

            # Skip past cashflows
            if payment_date <= valuation:
                continue

            yf = day_counter.yearFraction(accrual_start, accrual_end)
            accrual_days = day_counter.dayCount(accrual_start, accrual_end)
            coupon_amount = face_value * coupon_rate * yf
            is_final = (i == len(dates) - 1)
            principal = face_value if is_final else 0.0
            total_cf = coupon_amount + principal

            df = self.cm.tes_handle.discount(payment_date)
            pv = total_cf * df

            cashflows.append({
                "date": ql_to_datetime(payment_date),
                "date_str": f"{payment_date.year()}-{payment_date.month():02d}-{payment_date.dayOfMonth():02d}",
                "period": i,
                "coupon": round(coupon_amount, 6),
                "principal": round(principal, 6),
                "cashflow": round(total_cf, 6),
                "discount_factor": round(df, 8),
                "pv": round(pv, 6),
                "accrual_start": f"{accrual_start.year()}-{accrual_start.month():02d}-{accrual_start.dayOfMonth():02d}",
                "accrual_end": f"{accrual_end.year()}-{accrual_end.month():02d}-{accrual_end.dayOfMonth():02d}",
                "accrual_days": accrual_days,
                "year_fraction": round(yf, 8),
            })

        return cashflows

    def analytics(
        self,
        issue_date,
        maturity_date,
        coupon_rate: float,
        market_clean_price: Optional[float] = None,
        face_value: float = 100.0,
        include_cashflows: bool = False,
    ) -> dict:
        """
        Compute full analytics for a TES bond.

        Includes price, yield, duration, convexity, DV01, BPV.
        Optionally includes the full cashflow schedule and carry/roll-down
        analytics.

        Args:
            issue_date: Bond issuance date.
            maturity_date: Bond maturity date.
            coupon_rate: Annual coupon rate as decimal.
            market_clean_price: If provided, used to compute YTM.
            face_value: Face value.
            include_cashflows: If True, include full cashflow schedule in response.

        Returns:
            dict with all analytics including optional cashflows and carry.
        """
        bond = self.create_bond(issue_date, maturity_date, coupon_rate, face_value)

        clean_price = bond.cleanPrice()
        dirty_price = bond.dirtyPrice()
        accrued = bond.accruedAmount()
        npv = bond.NPV()

        if market_clean_price is not None:
            ytm = bond.bondYield(
                market_clean_price, ql.Actual36525(), ql.Compounded, ql.Annual
            )
            price_for_risk = market_clean_price
        else:
            ytm = bond.bondYield(
                clean_price, ql.Actual36525(), ql.Compounded, ql.Annual
            )
            price_for_risk = clean_price

        flat_rate = ql.InterestRate(ytm, ql.Actual36525(), ql.Compounded, ql.Annual)

        macaulay_dur = ql.BondFunctions.duration(bond, flat_rate, ql.Duration.Macaulay)
        modified_dur = ql.BondFunctions.duration(bond, flat_rate, ql.Duration.Modified)
        convexity = ql.BondFunctions.convexity(bond, flat_rate)

        dirty_for_risk = price_for_risk + accrued
        dv01 = modified_dur * dirty_for_risk / 10000.0
        bpv = dv01 * face_value / 100.0

        mat_dt = ql_to_datetime(maturity_date) if isinstance(maturity_date, ql.Date) else maturity_date

        result = {
            "clean_price": clean_price,
            "dirty_price": dirty_price,
            "accrued_interest": accrued,
            "npv": npv,
            "ytm": ytm,
            "macaulay_duration": macaulay_dur,
            "modified_duration": modified_dur,
            "convexity": convexity,
            "dv01": dv01,
            "bpv": bpv,
            "coupon_rate": coupon_rate,
            "face_value": face_value,
            "maturity": mat_dt,
        }

        # Cashflow schedule
        if include_cashflows:
            result["cashflows"] = self.cashflow_schedule(
                issue_date, maturity_date, coupon_rate, face_value
            )

        # Carry and roll-down analytics
        try:
            carry = self.carry_rolldown(
                issue_date, maturity_date, coupon_rate,
                market_clean_price=market_clean_price,
                face_value=face_value,
            )
            result["carry"] = carry
        except Exception:
            # Carry may fail if horizon date is beyond maturity
            result["carry"] = None

        # Z-spread
        if market_clean_price is not None:
            try:
                z_spread = self.z_spread(
                    issue_date, maturity_date, coupon_rate,
                    market_clean_price, face_value,
                )
                result["z_spread_bps"] = z_spread
            except Exception:
                result["z_spread_bps"] = None
        else:
            result["z_spread_bps"] = None

        return result

    def carry_rolldown(
        self,
        issue_date,
        maturity_date,
        coupon_rate: float,
        horizon_days: int = 30,
        market_clean_price: Optional[float] = None,
        face_value: float = 100.0,
    ) -> dict:
        """
        Compute carry and roll-down for a TES bond over a given horizon.

        Carry measures the P&L from holding the bond assuming rates stay
        constant.  It consists of two components:
          - Coupon carry: accrued interest earned over the horizon.
          - Roll-down: price change from moving along the unchanged yield curve.

        Args:
            issue_date: Bond issuance date (datetime or ql.Date).
            maturity_date: Bond maturity date (datetime or ql.Date).
            coupon_rate: Annual coupon rate as decimal.
            horizon_days: Number of calendar days for the analysis (default 30).
            market_clean_price: Market price for YTM computation.
            face_value: Face value.

        Returns:
            dict with carry analytics: horizon_date, coupon_carry, rolldown,
            total_carry, total_carry_bps, current_dirty, horizon_dirty.
        """
        if isinstance(issue_date, datetime):
            issue_date = datetime_to_ql(issue_date)
        if isinstance(maturity_date, datetime):
            maturity_date = datetime_to_ql(maturity_date)

        valuation = self.cm.valuation_date
        horizon_date = valuation + horizon_days

        # Ensure horizon is before maturity
        if horizon_date >= maturity_date:
            return {
                "horizon_days": horizon_days,
                "horizon_date": ql_to_datetime(horizon_date),
                "error": "Horizon date is at or beyond maturity.",
            }

        # Current pricing
        bond = self.create_bond(issue_date, maturity_date, coupon_rate, face_value)
        if market_clean_price is not None:
            current_dirty = market_clean_price + bond.accruedAmount()
        else:
            current_dirty = bond.dirtyPrice()

        # Roll-down: re-price the bond on the horizon date using the SAME curve
        # by computing the bond's dirty price at the horizon date on the current curve
        day_counter = ql.Actual36525()

        # Accrued interest at horizon
        accrued_horizon = ql.BondFunctions.accruedAmount(bond, horizon_date)

        # Coupon carry = accrued at horizon - accrued now (net coupon income)
        accrued_now = bond.accruedAmount()
        coupon_carry = accrued_horizon - accrued_now

        # Roll-down: use the curve's discount factors from the horizon date
        # to reprice the remaining cashflows. The bond's clean price changes
        # because the bond is now shorter on the same curve.
        # We compute: dirty_horizon = sum(CF_i * DF(T_i) / DF(T_horizon))
        schedule = self._get_schedule(issue_date, maturity_date)
        dates = list(schedule)

        df_horizon = self.cm.tes_handle.discount(horizon_date)
        dirty_horizon = 0.0
        for i in range(1, len(dates)):
            payment_date = dates[i]
            if payment_date <= horizon_date:
                continue
            accrual_start = dates[i - 1]
            yf = day_counter.yearFraction(accrual_start, payment_date)
            cf = face_value * coupon_rate * yf
            if i == len(dates) - 1:
                cf += face_value
            df_payment = self.cm.tes_handle.discount(payment_date)
            dirty_horizon += cf * (df_payment / df_horizon)

        rolldown = dirty_horizon - current_dirty - coupon_carry
        total_carry = coupon_carry + rolldown

        # Express in bps: total carry / dirty price * 10000 * (365.25 / horizon_days)
        if current_dirty != 0:
            total_carry_bps = (total_carry / current_dirty) * 10000.0 * (365.25 / horizon_days)
        else:
            total_carry_bps = 0.0

        return {
            "horizon_days": horizon_days,
            "horizon_date": ql_to_datetime(horizon_date),
            "current_dirty": round(current_dirty, 6),
            "horizon_dirty": round(dirty_horizon, 6),
            "coupon_carry": round(coupon_carry, 6),
            "rolldown": round(rolldown, 6),
            "total_carry": round(total_carry, 6),
            "total_carry_bps_annualized": round(total_carry_bps, 2),
        }

    def z_spread(
        self,
        issue_date,
        maturity_date,
        coupon_rate: float,
        market_clean_price: float,
        face_value: float = 100.0,
    ) -> float:
        """
        Compute the Z-spread (zero-volatility spread) over the TES curve.

        The Z-spread is the constant spread added to each point on the
        TES zero curve such that the sum of discounted cashflows equals
        the market dirty price.

        Args:
            issue_date: Bond issuance date (datetime or ql.Date).
            maturity_date: Bond maturity date (datetime or ql.Date).
            coupon_rate: Annual coupon rate as decimal.
            market_clean_price: Market clean price of the bond.
            face_value: Face value.

        Returns:
            Z-spread in basis points.
        """
        if isinstance(issue_date, datetime):
            issue_date = datetime_to_ql(issue_date)
        if isinstance(maturity_date, datetime):
            maturity_date = datetime_to_ql(maturity_date)

        bond = self.create_bond(issue_date, maturity_date, coupon_rate, face_value)
        accrued = bond.accruedAmount()
        market_dirty = market_clean_price + accrued

        schedule = self._get_schedule(issue_date, maturity_date)
        day_counter = ql.Actual36525()
        valuation = self.cm.valuation_date
        dates = list(schedule)

        # Build cashflow list (future only)
        cf_list: list[tuple[ql.Date, float]] = []
        for i in range(1, len(dates)):
            payment_date = dates[i]
            if payment_date <= valuation:
                continue
            accrual_start = dates[i - 1]
            yf = day_counter.yearFraction(accrual_start, payment_date)
            cf = face_value * coupon_rate * yf
            if i == len(dates) - 1:
                cf += face_value
            cf_list.append((payment_date, cf))

        def _pv_with_spread(spread_decimal: float) -> float:
            """Compute dirty price using curve DFs shifted by a constant spread."""
            pv = 0.0
            for dt, cf in cf_list:
                t = day_counter.yearFraction(valuation, dt)
                base_df = self.cm.tes_handle.discount(dt)
                # Convert DF to continuous zero rate, add spread, back to DF
                if base_df > 0 and t > 0:
                    z = -1.0 * ql.InterestRate.impliedRate(
                        base_df, day_counter, ql.Continuous, ql.NoFrequency, t
                    ).rate()
                    # z is negative of the implied rate since DF = exp(-z*t)
                    # Actually: DF = exp(-r*t), so r = -ln(DF)/t
                    import math
                    r_cont = -math.log(base_df) / t
                    adjusted_df = math.exp(-(r_cont + spread_decimal) * t)
                else:
                    adjusted_df = base_df
                pv += cf * adjusted_df
            return pv

        def _objective(spread_decimal: float) -> float:
            return _pv_with_spread(spread_decimal) - market_dirty

        # Solve for spread: search between -10% and +10%
        z_spread_decimal = brentq(_objective, -0.10, 0.10, xtol=1e-8)
        return round(z_spread_decimal * 10000.0, 2)  # Convert to bps

    def spread_to_curve(
        self,
        issue_date,
        maturity_date,
        coupon_rate: float,
        market_clean_price: float,
        face_value: float = 100.0,
    ) -> dict:
        """
        Compute spread metrics of the bond relative to the TES curve.

        Returns the yield spread (bond YTM minus interpolated curve yield)
        and the Z-spread.

        Args:
            issue_date: Bond issuance date (datetime or ql.Date).
            maturity_date: Bond maturity date (datetime or ql.Date).
            coupon_rate: Annual coupon rate as decimal.
            market_clean_price: Market clean price.
            face_value: Face value.

        Returns:
            dict with yield_spread_bps and z_spread_bps.
        """
        if isinstance(issue_date, datetime):
            issue_date = datetime_to_ql(issue_date)
        if isinstance(maturity_date, datetime):
            maturity_date = datetime_to_ql(maturity_date)

        # Bond YTM from market price
        bond = self.create_bond(issue_date, maturity_date, coupon_rate, face_value)
        ytm = bond.bondYield(
            market_clean_price, ql.Actual36525(), ql.Compounded, ql.Annual
        )

        # Interpolated curve yield at the bond's maturity
        curve_yield = self.cm.tes_handle.zeroRate(
            maturity_date, ql.Actual36525(), ql.Compounded, ql.Annual
        ).rate()

        yield_spread_bps = round((ytm - curve_yield) * 10000.0, 2)

        # Z-spread
        z_spread_bps = self.z_spread(
            issue_date, maturity_date, coupon_rate,
            market_clean_price, face_value,
        )

        return {
            "ytm": ytm,
            "curve_yield": curve_yield,
            "yield_spread_bps": yield_spread_bps,
            "z_spread_bps": z_spread_bps,
        }

    def price_portfolio(self, bonds_df: pd.DataFrame) -> pd.DataFrame:
        """
        Price a portfolio of TES bonds.

        Args:
            bonds_df: DataFrame with columns: name, emision, maduracion, cupon,
                      notional (optional), market_price (optional)

        Returns:
            DataFrame with all analytics per bond
        """
        results = []
        for _, row in bonds_df.iterrows():
            notional = row.get("notional", 100.0)
            market_price = row.get("market_price", None)

            analytics = self.analytics(
                issue_date=row["emision"],
                maturity_date=row["maduracion"],
                coupon_rate=row["cupon"],
                market_clean_price=market_price,
                face_value=notional,
            )
            analytics["name"] = row["name"]
            results.append(analytics)

        return pd.DataFrame(results)

    def batch_reprice(
        self,
        positions: list[dict],
    ) -> list[dict]:
        """
        Reprice a batch of TES bond positions.

        Each position dict should contain bond identification (either explicit
        parameters or a bond_name for catalog lookup) and position details.

        Args:
            positions: List of dicts, each with keys:
              - issue_date (str YYYY-MM-DD)
              - maturity_date (str YYYY-MM-DD)
              - coupon_rate (float)
              - notional (float, optional, default 100)
              - market_clean_price (float, optional)
              - direction ('long' or 'short', optional, default 'long')

        Returns:
            List of dicts with analytics per position, including position P&L.
        """
        results = []
        for pos in positions:
            issue_date = pos["issue_date"]
            maturity_date = pos["maturity_date"]
            coupon_rate = pos["coupon_rate"]
            notional = pos.get("notional", 100.0)
            market_price = pos.get("market_clean_price")
            direction = pos.get("direction", "long")
            bond_name = pos.get("bond_name", None)

            if isinstance(issue_date, str):
                issue_date = datetime.strptime(issue_date, "%Y-%m-%d")
            if isinstance(maturity_date, str):
                maturity_date = datetime.strptime(maturity_date, "%Y-%m-%d")

            analytics = self.analytics(
                issue_date=issue_date,
                maturity_date=maturity_date,
                coupon_rate=coupon_rate,
                market_clean_price=market_price,
                face_value=100.0,
                include_cashflows=False,
            )

            sign = 1.0 if direction == "long" else -1.0
            position_npv = sign * analytics["npv"] * notional / 100.0
            position_dv01 = sign * analytics["dv01"] * notional / 100.0

            result = {
                "bond_name": bond_name,
                "direction": direction,
                "notional": notional,
                "clean_price": analytics["clean_price"],
                "dirty_price": analytics["dirty_price"],
                "accrued_interest": analytics["accrued_interest"],
                "ytm": analytics["ytm"],
                "modified_duration": analytics["modified_duration"],
                "position_npv": round(position_npv, 2),
                "position_dv01": round(position_dv01, 6),
                "carry": analytics.get("carry"),
                "z_spread_bps": analytics.get("z_spread_bps"),
            }
            results.append(result)

        return results
