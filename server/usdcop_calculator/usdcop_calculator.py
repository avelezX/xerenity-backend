import os
import math

import numpy as np
import pandas as pd
import requests

from server.main_server import XerenityError, responseHttpOk


TRADING_DAYS = 252
VOL_WINDOW = 180
FETCH_LIMIT = 250
BANREP_TRM_ID_SERIE = 25


class UsdCopCalculator:
    """Calcula TRM spot y volatilidad (diaria/anual) desde BanRep via Supabase REST."""

    def calculate(self):
        url = os.getenv("XTY_URL")
        key = os.getenv("XTY_TOKEN")
        bearer = os.getenv("COLLECTOR_BEARER") or key

        if not url or not key:
            raise XerenityError("XTY_URL / XTY_TOKEN no configuradas", 500)

        session = requests.Session()
        session.headers.update({
            "apikey": key,
            "Authorization": f"Bearer {bearer}",
            "Accept-Profile": "xerenity",
        })

        resp = session.get(
            f"{url}/rest/v1/banrep_series_value_v2"
            f"?select=fecha,valor"
            f"&id_serie=eq.{BANREP_TRM_ID_SERIE}"
            f"&order=fecha.desc"
            f"&limit={FETCH_LIMIT}",
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data:
            raise XerenityError("No se encontraron datos de TRM en banrep_series_value_v2", 404)

        df = pd.DataFrame(data)
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
        df = df.dropna(subset=["valor"]).sort_values("fecha").reset_index(drop=True)

        if len(df) < 2:
            raise XerenityError("Datos insuficientes de TRM para calcular retornos", 400)

        log_returns = np.log(df["valor"] / df["valor"].shift(1)).dropna()

        window = log_returns.tail(VOL_WINDOW)
        if len(window) < 30:
            raise XerenityError(
                f"Datos insuficientes para vol rolling: {len(window)} retornos (min 30)",
                400,
            )

        vol_diaria = float(window.std())
        vol_anual = vol_diaria * math.sqrt(TRADING_DAYS)

        return responseHttpOk(body={
            "trm": float(df["valor"].iloc[-1]),
            "vol_diaria": vol_diaria,
            "vol_anual": vol_anual,
            "fecha": str(df["fecha"].iloc[-1]),
        })
