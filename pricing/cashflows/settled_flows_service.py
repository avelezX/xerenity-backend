"""
Servicio de alto nivel para flujos liquidados entre dos fechas.

Dado un instrumento (XCCY o IBR OIS) y un rango de fechas T0–T1,
calcula la suma de flujos netos de todos los períodos que se liquidaron
dentro de ese rango.
"""
from __future__ import annotations

from datetime import date

from pricing.cashflows.fixing_repository import FixingRepository
from pricing.cashflows.realized_cashflows import RealizedCashflowCalculator


class SettledFlowsService:
    """
    Calcula flujos netos realizados de períodos liquidados entre T0 y T1.

    El caller provee el schedule completo del instrumento (generado por
    xccy.cashflows() o ibr.cashflows()) y este servicio filtra los
    períodos con status='settled' cuyo date_end cae entre T0 y T1.
    """

    def __init__(self, fixing_repo: FixingRepository):
        self.fixing_repo = fixing_repo
        self.calculator = RealizedCashflowCalculator(fixing_repo)

    def settled_flows_between(
        self,
        instrument_type: str,
        instrument_params: dict,
        schedule: list[dict],
        T0: str,
        T1: str,
    ) -> dict:
        """
        Retorna la suma de flujos netos de períodos liquidados entre T0 y T1.

        Args:
            instrument_type:   'xccy' o 'ibr_ois'
            instrument_params: Parámetros del trade. Para XCCY:
                                 {notional_usd, notional_cop, fx_initial,
                                  usd_spread_bps, cop_spread_bps, xccy_basis_bps, pay_usd}
                               Para IBR OIS:
                                 {notional, fixed_rate_pct, spread_bps, pay_fixed}
            schedule:          Lista de períodos (dicts) con al menos:
                                 {period_num, date_start, date_end, status}
                               Para XCCY también: {notional_usd, notional_cop,
                                 usd_principal, cop_principal}
                               Para IBR OIS también: {notional}
            T0:                Inicio del rango (inclusive), ISO string 'YYYY-MM-DD'
            T1:                Fin del rango (inclusive), ISO string 'YYYY-MM-DD'

        Returns:
            dict con:
              total_net_cop:  Suma de flujos netos COP en el rango.
              total_net_usd:  Suma de flujos netos USD (solo XCCY, None para IBR OIS).
              periods:        Lista de períodos procesados con flujos realizados.
        """
        t0 = date.fromisoformat(T0)
        t1 = date.fromisoformat(T1)

        # Períodos liquidados cuyo date_end cae en [T0, T1], excluyendo intercambio inicial
        settled = [
            p for p in schedule
            if p.get("status") == "settled"
            and p.get("period_num", 0) > 0
            and t0 <= date.fromisoformat(p["date_end"]) <= t1
        ]

        periods_out = []
        total_net_cop = 0.0
        total_net_usd = 0.0

        if instrument_type == "xccy":
            usd_spread_bps = instrument_params.get("usd_spread_bps", 0.0)
            cop_spread_bps = instrument_params.get("cop_spread_bps", 0.0)
            xccy_basis_bps = instrument_params.get("xccy_basis_bps", 0.0)
            pay_usd = instrument_params.get("pay_usd", True)
            sign = 1.0 if pay_usd else -1.0

            for period in settled:
                n_usd = period.get("notional_usd", instrument_params.get("notional_usd", 0.0))
                n_cop = period.get("notional_cop", instrument_params.get("notional_cop", 0.0))

                realized = self.calculator.xccy_settled_period(
                    period=period,
                    notional_usd=n_usd,
                    notional_cop=n_cop,
                    usd_spread_bps=usd_spread_bps,
                    cop_spread_bps=cop_spread_bps,
                    xccy_basis_bps=xccy_basis_bps,
                )

                usd_principal = period.get("usd_principal", 0.0)
                cop_principal = period.get("cop_principal", 0.0)

                # Convención: pay_usd=True → paga cupón USD (-), recibe cupón COP (+)
                usd_net = (-sign * realized["usd_coupon"]) + usd_principal
                cop_net = (+sign * realized["cop_coupon"]) + cop_principal

                total_net_usd += usd_net
                total_net_cop += cop_net

                periods_out.append({
                    "period_num": period["period_num"],
                    "date_start": period["date_start"],
                    "date_end": period["date_end"],
                    "usd_coupon": realized["usd_coupon"],
                    "cop_coupon": realized["cop_coupon"],
                    "usd_principal": usd_principal,
                    "cop_principal": cop_principal,
                    "usd_net": round(usd_net, 2),
                    "cop_net": round(cop_net, 0),
                    "realized_sofr_pct": realized["realized_sofr_pct"],
                    "realized_ibr_pct": realized["realized_ibr_pct"],
                })

            return {
                "total_net_cop": round(total_net_cop, 0),
                "total_net_usd": round(total_net_usd, 2),
                "periods": periods_out,
            }

        elif instrument_type == "ibr_ois":
            fixed_rate_pct = instrument_params.get("fixed_rate_pct", 0.0)
            spread_bps = instrument_params.get("spread_bps", 0.0)
            pay_fixed = instrument_params.get("pay_fixed", True)
            # pay_fixed=True: net = flotante - fija (positivo si IBR > fixed)
            sign = 1.0 if pay_fixed else -1.0

            for period in settled:
                notional = period.get("notional", instrument_params.get("notional", 0.0))

                realized = self.calculator.ibr_ois_settled_period(
                    period=period,
                    notional=notional,
                    fixed_rate_pct=fixed_rate_pct,
                    spread_bps=spread_bps,
                )

                net_from_perspective = sign * realized["net"]
                total_net_cop += net_from_perspective

                periods_out.append({
                    "period_num": period["period_num"],
                    "date_start": period["date_start"],
                    "date_end": period["date_end"],
                    "notional": notional,
                    "fixed_coupon": realized["fixed_coupon"],
                    "floating_coupon": realized["floating_coupon"],
                    "net": round(net_from_perspective, 0),
                    "realized_ibr_pct": realized["realized_ibr_pct"],
                })

            return {
                "total_net_cop": round(total_net_cop, 0),
                "total_net_usd": None,
                "periods": periods_out,
            }

        else:
            raise ValueError(
                f"instrument_type desconocido: '{instrument_type}'. "
                "Valores válidos: 'xccy', 'ibr_ois'"
            )
