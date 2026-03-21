"""
Módulo de cashflows realizados para derivados OIS.

Calcula cupones compuestos overnight usando fixings históricos de IBR (BanRep)
y SOFR (Fed) almacenados en Supabase, sin necesitar tablas adicionales.
"""
from pricing.cashflows.fixing_repository import FixingRepository
from pricing.cashflows.ois_compounding import compound_overnight_rate, realized_coupon
from pricing.cashflows.realized_cashflows import RealizedCashflowCalculator
from pricing.cashflows.settled_flows_service import SettledFlowsService

__all__ = [
    "FixingRepository",
    "compound_overnight_rate",
    "realized_coupon",
    "RealizedCashflowCalculator",
    "SettledFlowsService",
]
