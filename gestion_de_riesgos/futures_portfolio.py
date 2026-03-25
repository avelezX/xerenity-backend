"""
Portafolio de futuros para gestion de riesgos.

Calcula P&L (diario, mensual, desde inicio) para posiciones individuales
de futuros de commodities (MAIZ, AZUCAR, CACAO) operadas en cuentas de margen.

Soporta posiciones LONG y SHORT, y roll de contratos.
"""

from datetime import datetime, date, timedelta
import pandas as pd
import math


# Multiplicador por contrato (unidades fisicas por 1 contrato)
CONTRACT_MULTIPLIERS = {
    'MAIZ':   5_000,     # bushels por contrato (ZC, CBOT)
    'AZUCAR': 112_000,   # libras por contrato (SB, ICE)
    'CACAO':  10,         # toneladas metricas por contrato (CC, ICE)
}

DIRECTION_SIGN = {'LONG': 1, 'SHORT': -1}

PRICE_UNITS = {
    'MAIZ': 'cents/bu',
    'AZUCAR': 'cents/lb',
    'CACAO': 'USD/ton',
}


def _safe_round(value, decimals=2):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(value, decimals)


def _last_business_day_of_prev_month(ref_date: date) -> date:
    """
    Ultimo dia habil del mes anterior a ref_date.
    Misma logica que benchmark_factors() en risk_management_server.
    """
    first_of_current = ref_date.replace(day=1)
    last_cal_day = first_of_current - timedelta(days=1)
    wd = last_cal_day.weekday()  # 0=Mon ... 5=Sat, 6=Sun
    if wd == 5:
        return last_cal_day - timedelta(days=1)
    elif wd == 6:
        return last_cal_day - timedelta(days=2)
    return last_cal_day


def _prev_business_day(ref_date: date) -> date:
    """Dia habil anterior (retrocede sabados y domingos)."""
    prev = ref_date - timedelta(days=1)
    wd = prev.weekday()
    if wd == 5:
        return prev - timedelta(days=1)
    elif wd == 6:
        return prev - timedelta(days=2)
    return prev


def _find_price(prices_df: pd.DataFrame, asset: str, target_date: date):
    """
    Busca el precio mas reciente en o antes de target_date.
    Returns (price, actual_date_str) o (None, None).
    """
    if asset not in prices_df.columns:
        return None, None

    target_str = target_date.strftime('%Y-%m-%d')
    mask = prices_df['date'] <= target_str
    subset = prices_df.loc[mask, ['date', asset]].dropna(subset=[asset])
    if subset.empty:
        return None, None

    row = subset.iloc[-1]
    return float(row[asset]), str(row['date'])[:10]


class FuturesPortfolioCalculator:
    """
    Calcula P&L para un portafolio de posiciones individuales de futuros.

    Cada posicion tiene:
    - asset, contract, direction (LONG/SHORT), nominal (# contratos)
    - entry_price, entry_date

    Calcula:
    - valor_t:       nominal * multiplier * precio actual
    - valor_t1:      nominal * multiplier * precio dia anterior
    - daily_pnl:     diferencia diaria considerando direccion
    - pnl_inception: P&L desde precio de compra
    - pnl_month:     P&L del mes corriente (desde ultimo dia habil del mes anterior)
    """

    def __init__(
        self,
        positions: list[dict],
        prices_history: pd.DataFrame,
        filter_date: str,
    ):
        self.positions = positions
        self.prices = prices_history
        self.filter_date = datetime.strptime(filter_date, '%Y-%m-%d').date()

    def calculate(self) -> list[dict]:
        ref = self.filter_date
        prev_bday = _prev_business_day(ref)
        month_start = _last_business_day_of_prev_month(ref)

        rows = []
        totals = {
            'valor_t': 0, 'valor_t1': 0,
            'daily_pnl': 0, 'pnl_inception': 0, 'pnl_month': 0,
        }

        for pos in self.positions:
            asset = pos['asset']
            direction = pos['direction']
            nominal = pos['nominal']
            entry_price = float(pos['entry_price'])
            multiplier = CONTRACT_MULTIPLIERS.get(asset, 1)
            dir_sign = DIRECTION_SIGN.get(direction, 1)

            current_price, current_date = _find_price(self.prices, asset, ref)
            prev_price, _ = _find_price(self.prices, asset, prev_bday)
            month_start_price, month_start_actual = _find_price(
                self.prices, asset, month_start
            )

            # Si la posicion se abrio dentro del mes corriente,
            # el P&L mensual arranca desde el entry_price
            entry_dt = datetime.strptime(pos['entry_date'], '%Y-%m-%d').date()
            if entry_dt > month_start:
                month_ref_price = entry_price
            else:
                month_ref_price = month_start_price

            # Calculos
            valor_t = None
            valor_t1 = None
            daily_pnl = None
            pnl_inception = None
            pnl_month = None

            if current_price is not None:
                valor_t = nominal * multiplier * current_price
                pnl_inception = (current_price - entry_price) * nominal * multiplier * dir_sign

            if prev_price is not None:
                valor_t1 = nominal * multiplier * prev_price

            if current_price is not None and prev_price is not None:
                daily_pnl = (current_price - prev_price) * nominal * multiplier * dir_sign

            if current_price is not None and month_ref_price is not None:
                pnl_month = (current_price - month_ref_price) * nominal * multiplier * dir_sign

            row = {
                'id': pos.get('id'),
                'asset': asset,
                'contract': pos['contract'],
                'direction': direction,
                'nominal': nominal,
                'multiplier': multiplier,
                'entry_price': entry_price,
                'entry_date': pos['entry_date'],
                'current_price': _safe_round(current_price, 4),
                'current_price_date': current_date,
                'previous_price': _safe_round(prev_price, 4),
                'month_start_price': _safe_round(month_ref_price, 4),
                'valor_t': _safe_round(valor_t),
                'valor_t1': _safe_round(valor_t1),
                'daily_pnl': _safe_round(daily_pnl),
                'pnl_inception': _safe_round(pnl_inception),
                'pnl_month': _safe_round(pnl_month),
                'price_unit': PRICE_UNITS.get(asset, ''),
            }
            rows.append(row)

            # Acumular totales
            for key in totals:
                val = row[key]
                if val is not None:
                    totals[key] += val

        # Fila total
        rows.append({
            'id': None,
            'asset': 'Total',
            'contract': None,
            'direction': None,
            'nominal': None,
            'multiplier': None,
            'entry_price': None,
            'entry_date': None,
            'current_price': None,
            'current_price_date': None,
            'previous_price': None,
            'month_start_price': None,
            'valor_t': _safe_round(totals['valor_t']),
            'valor_t1': _safe_round(totals['valor_t1']),
            'daily_pnl': _safe_round(totals['daily_pnl']),
            'pnl_inception': _safe_round(totals['pnl_inception']),
            'pnl_month': _safe_round(totals['pnl_month']),
            'price_unit': None,
        })

        return rows

    @staticmethod
    def execute_roll(
        position: dict,
        new_contract: str,
        roll_price: float,
        roll_date: str,
        new_entry_price: float = None,
    ) -> tuple[dict, dict]:
        """
        Prepara los datos para un roll de contrato.

        Args:
            position: Posicion actual (dict de Supabase)
            new_contract: Codigo del nuevo contrato (ej: 'ZCN26')
            roll_price: Precio al que se cierra la posicion vieja
            roll_date: Fecha del roll (YYYY-MM-DD)
            new_entry_price: Precio de entrada del nuevo contrato
                             (default: roll_price)

        Returns:
            (close_update, new_position) - dicts listos para db_risk
        """
        if new_entry_price is None:
            new_entry_price = roll_price

        close_update = {
            'active': False,
            'closed_date': roll_date,
            'closed_price': roll_price,
            'rolled_to': new_contract,
        }

        new_position = {
            'asset': position['asset'],
            'contract': new_contract,
            'direction': position['direction'],
            'nominal': position['nominal'],
            'entry_price': new_entry_price,
            'entry_date': roll_date,
            'active': True,
        }
        if position.get('portfolio_id'):
            new_position['portfolio_id'] = position['portfolio_id']

        return close_update, new_position
