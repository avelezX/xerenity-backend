"""
Compounding overnight para instrumentos OIS.

Implementa la convención estándar de capitalización diaria usada por BanRep (IBR)
y la Fed (SOFR): cada fixing aplica desde su fecha hasta el siguiente fixing,
cubriendo implícitamente fines de semana y festivos (el viernes aplica 3 días
si el próximo fixing es el lunes).

Convención: Actual/360 para IBR y SOFR.
"""
from __future__ import annotations

from datetime import date


def compound_overnight_rate(
    fixings: list[dict],
    start_date: "date | str",
    end_date: "date | str",
    day_count: int = 360,
) -> float:
    """
    Calcula la tasa compuesta realizada de un período OIS.

    Para cada fixing, el rate aplica desde su fecha hasta el siguiente fixing
    (o hasta end_date para el último). Fines de semana y festivos quedan
    implícitamente cubiertos: el viernes tiene days=3 si el lunes es el próximo fixing.

    Fórmula: ∏(1 + rate_i/100 * days_i/day_count) − 1

    Args:
        fixings:    Lista de {'date': 'YYYY-MM-DD', 'rate': float} en porcentaje.
                    Debe cubrir el período [start_date, end_date).
                    Los fixings fuera del rango son ignorados.
        start_date: Inicio del período (los fixings anteriores a esta fecha son ignorados).
        end_date:   Fin del período; el último fixing aplica hasta aquí.
        day_count:  Base de días (360 para IBR y SOFR).

    Returns:
        Tasa compuesta como decimal (e.g., 0.0235 para 2.35%).
        Retorna 0.0 si no hay fixings.
    """
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)

    if not fixings:
        return 0.0

    # Ordenar y filtrar: solo fixings >= start_date y < end_date
    sorted_fixings = sorted(
        [f for f in fixings if date.fromisoformat(f["date"]) < end_date],
        key=lambda x: x["date"],
    )
    if not sorted_fixings:
        return 0.0

    compound = 1.0
    n = len(sorted_fixings)

    for i, fixing in enumerate(sorted_fixings):
        fixing_date = date.fromisoformat(fixing["date"])

        # Días que aplica este fixing: hasta el próximo fixing o hasta end_date
        if i + 1 < n:
            next_date = date.fromisoformat(sorted_fixings[i + 1]["date"])
        else:
            next_date = end_date

        days = (next_date - fixing_date).days
        if days <= 0:
            continue

        rate_decimal = fixing["rate"] / 100.0
        compound *= 1.0 + rate_decimal * days / day_count

    return compound - 1.0


def realized_coupon(
    notional: float,
    fixings: list[dict],
    start_date: "date | str",
    end_date: "date | str",
    spread_bps: float = 0.0,
    day_count: int = 360,
) -> float:
    """
    Calcula el cupón realizado para un período OIS con spread opcional.

    El spread se suma a cada fixing diario antes de componer:
        ∏(1 + (rate_i/100 + spread/10000) * days_i/day_count) − 1

    Args:
        notional:   Nocional del instrumento (COP o USD según la pata).
        fixings:    Lista de {'date': 'YYYY-MM-DD', 'rate': float} en porcentaje.
        start_date: Inicio del período.
        end_date:   Fin del período.
        spread_bps: Spread en basis points (e.g., -22 para SOFR-22bps).
        day_count:  Base de días (360).

    Returns:
        Monto del cupón realizado en la misma moneda que notional.
        Retorna 0.0 si no hay fixings.
    """
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)

    if not fixings:
        return 0.0

    spread_decimal = spread_bps / 10_000.0

    sorted_fixings = sorted(
        [f for f in fixings if date.fromisoformat(f["date"]) < end_date],
        key=lambda x: x["date"],
    )
    if not sorted_fixings:
        return 0.0

    compound = 1.0
    n = len(sorted_fixings)

    for i, fixing in enumerate(sorted_fixings):
        fixing_date = date.fromisoformat(fixing["date"])

        if i + 1 < n:
            next_date = date.fromisoformat(sorted_fixings[i + 1]["date"])
        else:
            next_date = end_date

        days = (next_date - fixing_date).days
        if days <= 0:
            continue

        rate_decimal = fixing["rate"] / 100.0
        compound *= 1.0 + (rate_decimal + spread_decimal) * days / day_count

    return notional * (compound - 1.0)


def annualized_rate_pct(
    compound_factor: float,
    period_days: int,
    day_count: int = 360,
) -> float | None:
    """
    Anualiza una tasa compuesta de período a tasa simple anual en porcentaje.

    Fórmula: compound_factor / period_days * day_count * 100

    Args:
        compound_factor: Tasa compuesta decimal del período (ej. compound_overnight_rate()).
        period_days:     Días calendario del período.
        day_count:       Base de días (360).

    Returns:
        Tasa anualizada en porcentaje, o None si period_days <= 0.
    """
    if period_days <= 0:
        return None
    return round(compound_factor / period_days * day_count * 100, 4)
