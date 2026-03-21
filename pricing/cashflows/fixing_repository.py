"""
Repositorio de fixings overnight para cálculo de flujos realizados.

Consulta IBR ON (BanRep, id_serie=9) y SOFR ON (Fed) desde Supabase
usando el mismo patrón REST que MarketDataLoader.

Rates retornados en porcentaje (e.g., 9.629 = 9.629% IBR, 4.30 = 4.30% SOFR).
"""
from __future__ import annotations

import os
import requests
from typing import Optional


SUPABASE_URL = os.getenv("XTY_URL")
SUPABASE_KEY = os.getenv("XTY_TOKEN")
COLLECTOR_BEARER = os.getenv("COLLECTOR_BEARER")


class FixingRepository:
    """
    Consulta fixings overnight desde Supabase.

    Caché en memoria para evitar queries repetidos en la misma sesión
    (e.g., mismo período consultado por múltiples instrumentos del portfolio).

    Rates retornados en porcentaje:
      - IBR: campo 'valor' de banrep_series_value_v2 (e.g., 9.629)
      - SOFR: campo 'rate' de us_reference_rates (e.g., 4.30)
    """

    def __init__(
        self,
        supabase_url: str = None,
        supabase_key: str = None,
        bearer_token: str = None,
    ):
        self.url = supabase_url or SUPABASE_URL
        key = supabase_key or SUPABASE_KEY
        bearer = bearer_token or COLLECTOR_BEARER or key
        self.session = requests.Session()
        self.session.headers.update({
            "apikey": key,
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
            "Accept-Profile": "xerenity",
            "Content-Profile": "xerenity",
        })
        self._cache: dict[str, list[dict]] = {}

    def _get(self, table: str, params: str = "") -> list:
        resp = self.session.get(f"{self.url}/rest/v1/{table}?{params}")
        resp.raise_for_status()
        return resp.json()

    def get_ibr_on_fixings(self, start_date: str, end_date: str) -> list[dict]:
        """
        Retorna fixings IBR overnight entre start_date y end_date (inclusive).

        Fuente: banrep_series_value_v2 WHERE id_serie=9 (IBR ON).

        Args:
            start_date: ISO date string 'YYYY-MM-DD' (inicio del período, inclusive)
            end_date:   ISO date string 'YYYY-MM-DD' (fin del período, inclusive)

        Returns:
            Lista de {'date': str, 'rate': float} ordenada por fecha ascendente.
            rate en porcentaje (e.g., 9.629 = 9.629%).
        """
        cache_key = f"ibr_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        data = self._get(
            "banrep_series_value_v2",
            f"select=fecha,valor"
            f"&id_serie=eq.9"
            f"&fecha=gte.{start_date}&fecha=lte.{end_date}"
            f"&order=fecha.asc",
        )
        result = [
            {"date": row["fecha"], "rate": float(row["valor"])}
            for row in data
            if row.get("valor") is not None
        ]
        self._cache[cache_key] = result
        return result

    def get_sofr_on_fixings(self, start_date: str, end_date: str) -> list[dict]:
        """
        Retorna fixings SOFR overnight entre start_date y end_date (inclusive).

        Fuente: us_reference_rates WHERE rate_type='SOFR'.

        Args:
            start_date: ISO date string 'YYYY-MM-DD' (inicio del período, inclusive)
            end_date:   ISO date string 'YYYY-MM-DD' (fin del período, inclusive)

        Returns:
            Lista de {'date': str, 'rate': float} ordenada por fecha ascendente.
            rate en porcentaje (e.g., 4.30 = 4.30%).
        """
        cache_key = f"sofr_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        data = self._get(
            "us_reference_rates",
            f"select=fecha,rate"
            f"&rate_type=eq.SOFR"
            f"&fecha=gte.{start_date}&fecha=lte.{end_date}"
            f"&order=fecha.asc",
        )
        result = [
            {"date": row["fecha"], "rate": float(row["rate"])}
            for row in data
            if row.get("rate") is not None
        ]
        self._cache[cache_key] = result
        return result

    def clear_cache(self) -> None:
        """Limpia el caché en memoria."""
        self._cache.clear()
