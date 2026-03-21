"""
IBR Overnight Indexed Swap pricer.

Structure:
  - Fixed leg: Quarterly payments, Actual360, Following, Colombia calendar
  - Floating leg: IBR overnight compounded, Actual360

Conventions match swap_functions/ibr_quantlib_details.py:
  fixedLegFrequency = Quarterly
  fixedLegConvention = Following
  fixedLegDayCounter = Actual360()
"""
import QuantLib as ql
import pandas as pd
from datetime import datetime
from typing import TYPE_CHECKING
from utilities.date_functions import datetime_to_ql, ql_to_datetime
from utilities.colombia_calendar import calendar_colombia

if TYPE_CHECKING:
    from pricing.cashflows.fixing_repository import FixingRepository


class IbrSwapPricer:
    """
    Prices IBR OIS swaps (fixed vs floating IBR overnight).
    Uses ql.OvernightIndexedSwap for native QuantLib pricing.
    """

    def __init__(self, curve_manager):
        self.cm = curve_manager
        self.calendar = calendar_colombia()

    def create_swap(
        self,
        notional: float,
        tenor_or_maturity,
        fixed_rate: float,
        pay_fixed: bool = True,
        spread: float = 0.0,
    ) -> ql.OvernightIndexedSwap:
        """
        Create an IBR OIS swap.

        Args:
            notional: COP notional amount
            tenor_or_maturity: ql.Period (e.g., ql.Period(5, ql.Years))
                              or ql.Date/datetime for maturity
            fixed_rate: Fixed leg rate as decimal (e.g., 0.0950)
            pay_fixed: True = pay fixed / receive floating
            spread: Spread over IBR floating leg (decimal)

        Returns:
            ql.OvernightIndexedSwap with pricing engine set
        """
        swap_type = (
            ql.OvernightIndexedSwap.Payer
            if pay_fixed
            else ql.OvernightIndexedSwap.Receiver
        )

        if isinstance(tenor_or_maturity, datetime):
            tenor_or_maturity = datetime_to_ql(tenor_or_maturity)

        if isinstance(tenor_or_maturity, ql.Period):
            start_date = self.calendar.advance(self.cm.valuation_date, 2, ql.Days)
            maturity_date = self.calendar.advance(start_date, tenor_or_maturity)
        else:
            start_date = self.calendar.advance(self.cm.valuation_date, 2, ql.Days)
            maturity_date = tenor_or_maturity

        schedule = ql.Schedule(
            start_date, maturity_date,
            ql.Period(ql.Quarterly),
            self.calendar,
            ql.Following, ql.Following,
            ql.DateGeneration.Forward, False,
        )

        swap = ql.OvernightIndexedSwap(
            swap_type,
            notional,
            schedule,
            fixed_rate,
            ql.Actual360(),
            self.cm.ibr_index,
            spread,
        )

        engine = ql.DiscountingSwapEngine(self.cm.ibr_handle)
        swap.setPricingEngine(engine)

        return swap

    def price(
        self,
        notional: float,
        tenor_or_maturity,
        fixed_rate: float,
        pay_fixed: bool = True,
        spread: float = 0.0,
    ) -> dict:
        """
        Price an IBR OIS swap and return analytics.

        Returns:
            dict with: npv, fair_rate, fixed_leg_npv, floating_leg_npv,
                      fixed_leg_bps, dv01, notional
        """
        swap = self.create_swap(notional, tenor_or_maturity, fixed_rate, pay_fixed, spread)

        npv = swap.NPV()
        fair_rate = swap.fairRate()
        fixed_leg_npv = swap.fixedLegNPV()
        floating_leg_npv = swap.overnightLegNPV()
        fixed_leg_bps = swap.fixedLegBPS()

        return {
            "npv": npv,
            "fair_rate": fair_rate,
            "fixed_rate": fixed_rate,
            "fixed_leg_npv": fixed_leg_npv,
            "floating_leg_npv": floating_leg_npv,
            "fixed_leg_bps": fixed_leg_bps,
            "dv01": abs(fixed_leg_bps),
            "notional": notional,
            "pay_fixed": pay_fixed,
            "spread": spread,
        }

    def cashflows(
        self,
        notional: float,
        tenor_or_maturity,
        fixed_rate: float,
        pay_fixed: bool = True,
        spread: float = 0.0,
        fixing_repo: "FixingRepository | None" = None,
    ) -> list:
        """
        Schedule completo de cashflows para un IBR OIS swap.

        Retorna un dict por período con fechas, cupones estimados (current/future)
        o realizados (settled con fixing_repo), y el flujo neto.

        Convención:
            pay_fixed=True: paga fija, recibe flotante.
            net positivo = flujo neto positivo para la perspectiva del cliente.
            status: 'settled' (pasado), 'current' (en accrual), 'future'.

        Args:
            notional:        Nocional COP.
            tenor_or_maturity: ql.Period o ql.Date/datetime de vencimiento.
            fixed_rate:      Tasa fija como decimal (e.g., 0.095).
            pay_fixed:       True = paga fija / recibe flotante.
            spread:          Spread sobre IBR en la pata flotante (decimal).
            fixing_repo:     Opcional. Con fixing_repo, períodos settled se calculan
                             con fixings históricos. Sin él, sus cupones son None.

        Returns:
            Lista de dicts con: period_num, date_start, date_end, notional,
            fixed_coupon, floating_coupon, net, ibr_fwd_pct,
            realized_ibr_pct, status.
        """
        if isinstance(tenor_or_maturity, datetime):
            tenor_or_maturity = datetime_to_ql(tenor_or_maturity)

        if isinstance(tenor_or_maturity, ql.Period):
            start_date = self.calendar.advance(self.cm.valuation_date, 2, ql.Days)
            maturity_date = self.calendar.advance(start_date, tenor_or_maturity)
        else:
            start_date = self.calendar.advance(self.cm.valuation_date, 2, ql.Days)
            maturity_date = tenor_or_maturity

        schedule = ql.Schedule(
            start_date, maturity_date,
            ql.Period(ql.Quarterly),
            self.calendar,
            ql.Following, ql.Following,
            ql.DateGeneration.Forward, False,
        )

        dates = list(schedule)
        n_periods = len(dates) - 1

        eval_date = ql.Settings.instance().evaluationDate
        ibr_ref   = self.cm.ibr_handle.currentLink().referenceDate()
        dc        = ql.Actual360()
        sign      = 1.0 if pay_fixed else -1.0
        spread_decimal = spread

        # Calculadora de realizados (lazy init solo si se usa)
        realized_calc = None
        if fixing_repo is not None:
            from pricing.cashflows.realized_cashflows import RealizedCashflowCalculator
            realized_calc = RealizedCashflowCalculator(fixing_repo)

        rows = []

        for i in range(1, n_periods + 1):
            p_start = dates[i - 1]
            p_end   = dates[i]

            p_start_str = ql_to_datetime(p_start).strftime("%Y-%m-%d")
            p_end_str   = ql_to_datetime(p_end).strftime("%Y-%m-%d")

            if p_end <= eval_date:
                status = "settled"
            elif p_start < eval_date:
                status = "current"
            else:
                status = "future"

            realized_ibr_pct = None

            if status == "settled":
                if realized_calc is not None:
                    period_dict = {"date_start": p_start_str, "date_end": p_end_str}
                    realized = realized_calc.ibr_ois_settled_period(
                        period=period_dict,
                        notional=notional,
                        fixed_rate_pct=fixed_rate * 100.0,
                        spread_bps=spread_decimal * 10_000.0,
                    )
                    fixed_coupon    = realized["fixed_coupon"]
                    floating_coupon = realized["floating_coupon"]
                    # Net desde perspectiva del cliente según pay_fixed
                    net = sign * realized["net"]
                    realized_ibr_pct = realized["realized_ibr_pct"]
                else:
                    fixed_coupon = floating_coupon = net = None
                ibr_fwd_pct = None

            else:
                # Estimar pata fija y pata flotante con curva forward
                tau = dc.yearFraction(p_start, p_end)
                fixed_coupon = round(notional * fixed_rate * tau, 0)

                if p_end > ibr_ref:
                    ibr_start = p_start if p_start >= ibr_ref else ibr_ref
                    ibr_fwd = self.cm.ibr_handle.forwardRate(
                        ibr_start, p_end, dc, ql.Simple
                    ).rate()
                    floating_coupon = round(
                        notional * (ibr_fwd + spread_decimal) * tau, 0
                    )
                    ibr_fwd_pct = round(ibr_fwd * 100, 4)
                else:
                    floating_coupon = ibr_fwd_pct = None

                if fixed_coupon is not None and floating_coupon is not None:
                    # pay_fixed=True → net = flotante - fija desde perspectiva pagador fijo
                    net = round(sign * (floating_coupon - fixed_coupon), 0)
                else:
                    net = None

            rows.append({
                "period_num":        i,
                "date_start":        p_start_str,
                "date_end":          p_end_str,
                "notional":          notional,
                "fixed_coupon":      fixed_coupon,
                "floating_coupon":   floating_coupon,
                "net":               net,
                "ibr_fwd_pct":       ibr_fwd_pct,
                "realized_ibr_pct":  realized_ibr_pct,
                "status":            status,
            })

        return rows

    def par_rate(self, tenor: ql.Period) -> float:
        """
        Compute the par swap rate for a given tenor.

        Args:
            tenor: e.g., ql.Period(5, ql.Years)

        Returns:
            Par fixed rate as decimal
        """
        swap = self.create_swap(
            notional=1_000_000_000,
            tenor_or_maturity=tenor,
            fixed_rate=0.05,
            pay_fixed=True,
        )
        return swap.fairRate()

    def par_curve(self, tenors: list = None) -> pd.DataFrame:
        """
        Build a par swap rate curve for standard tenors.

        Args:
            tenors: List of (label, ql.Period) tuples.

        Returns:
            DataFrame with: tenor, tenor_years, par_rate
        """
        if tenors is None:
            tenors = [
                ("1Y", ql.Period(1, ql.Years)),
                ("2Y", ql.Period(2, ql.Years)),
                ("3Y", ql.Period(3, ql.Years)),
                ("5Y", ql.Period(5, ql.Years)),
                ("7Y", ql.Period(7, ql.Years)),
                ("10Y", ql.Period(10, ql.Years)),
                ("15Y", ql.Period(15, ql.Years)),
                ("20Y", ql.Period(20, ql.Years)),
            ]

        results = []
        for label, period in tenors:
            try:
                rate = self.par_rate(period)
                results.append({
                    "tenor": label,
                    "tenor_years": period.length() if period.units() == ql.Years else period.length() / 12,
                    "par_rate": rate,
                })
            except Exception as e:
                results.append({
                    "tenor": label,
                    "par_rate": None,
                    "error": str(e),
                })

        return pd.DataFrame(results)
