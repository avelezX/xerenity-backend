"""
Calculadora de flujos realizados para XCCY swaps e IBR OIS.

Usa FixingRepository para obtener fixings históricos y OIS compounding
para calcular cupones realizados de períodos ya liquidados (status='settled').
"""
from __future__ import annotations

from datetime import date

from pricing.cashflows.fixing_repository import FixingRepository
from pricing.cashflows.ois_compounding import (
    compound_overnight_rate,
    realized_coupon,
    annualized_rate_pct,
)


class RealizedCashflowCalculator:
    """Calcula cupones realizados de períodos settled usando fixings históricos."""

    def __init__(self, fixing_repo: FixingRepository):
        self.fixing_repo = fixing_repo

    def xccy_settled_period(
        self,
        period: dict,
        notional_usd: float,
        notional_cop: float,
        usd_spread_bps: float = 0.0,
        cop_spread_bps: float = 0.0,
        xccy_basis_bps: float = 0.0,
    ) -> dict:
        """
        Calcula flujos realizados para un período settled de XCCY swap.

        Pata USD: compound SOFR fixings + usd_spread_bps → cupón USD
        Pata COP: compound IBR fixings + cop_spread_bps + xccy_basis_bps → cupón COP

        Args:
            period:          dict con 'date_start' y 'date_end' (ISO strings).
            notional_usd:    Nocional USD vigente durante el período.
            notional_cop:    Nocional COP vigente durante el período.
            usd_spread_bps:  Spread sobre SOFR en la pata USD (e.g., -22).
            cop_spread_bps:  Spread adicional sobre IBR en la pata COP.
            xccy_basis_bps:  Basis cross-currency sobre IBR en la pata COP.

        Returns:
            dict con: usd_coupon, cop_coupon, realized_sofr_pct, realized_ibr_pct
        """
        start_str = period["date_start"]
        end_str = period["date_end"]

        sofr_fixings = self.fixing_repo.get_sofr_on_fixings(start_str, end_str)
        ibr_fixings = self.fixing_repo.get_ibr_on_fixings(start_str, end_str)

        cop_total_spread_bps = cop_spread_bps + xccy_basis_bps

        usd_coupon = realized_coupon(
            notional_usd, sofr_fixings, start_str, end_str, usd_spread_bps
        )
        cop_coupon = realized_coupon(
            notional_cop, ibr_fixings, start_str, end_str, cop_total_spread_bps
        )

        realized_sofr = compound_overnight_rate(sofr_fixings, start_str, end_str)
        realized_ibr = compound_overnight_rate(ibr_fixings, start_str, end_str)

        period_days = (
            date.fromisoformat(end_str) - date.fromisoformat(start_str)
        ).days

        return {
            "usd_coupon": round(usd_coupon, 2),
            "cop_coupon": round(cop_coupon, 0),
            "realized_sofr_pct": annualized_rate_pct(realized_sofr, period_days),
            "realized_ibr_pct": annualized_rate_pct(realized_ibr, period_days),
        }

    def ibr_ois_settled_period(
        self,
        period: dict,
        notional: float,
        fixed_rate_pct: float,
        spread_bps: float = 0.0,
    ) -> dict:
        """
        Calcula flujos realizados para un período settled de IBR OIS.

        Pata fija:    notional * fixed_rate * days/360  (convención simple Actual/360)
        Pata flotante: compound IBR fixings + spread (OIS compounding)
        Net = flotante − fija (perspectiva receptor flotante / pagador fijo)

        Args:
            period:          dict con 'date_start' y 'date_end' (ISO strings).
            notional:        Nocional COP.
            fixed_rate_pct:  Tasa fija en porcentaje (e.g., 9.5 = 9.5%).
            spread_bps:      Spread sobre IBR en la pata flotante.

        Returns:
            dict con: fixed_coupon, floating_coupon, net, realized_ibr_pct
        """
        start_str = period["date_start"]
        end_str = period["date_end"]

        ibr_fixings = self.fixing_repo.get_ibr_on_fixings(start_str, end_str)

        floating_coupon = realized_coupon(
            notional, ibr_fixings, start_str, end_str, spread_bps
        )

        # Pata fija: interés simple Actual/360 (convención IBR OIS)
        start_d = date.fromisoformat(start_str)
        end_d = date.fromisoformat(end_str)
        period_days = (end_d - start_d).days
        fixed_coupon = notional * (fixed_rate_pct / 100.0) * period_days / 360.0

        net = floating_coupon - fixed_coupon

        realized_ibr = compound_overnight_rate(ibr_fixings, start_str, end_str)

        return {
            "fixed_coupon": round(fixed_coupon, 0),
            "floating_coupon": round(floating_coupon, 0),
            "net": round(net, 0),
            "realized_ibr_pct": annualized_rate_pct(realized_ibr, period_days),
        }
