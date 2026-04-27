"""
Collector for FNC (Federacion Nacional de Cafeteros) internal coffee reference price.

Source: https://federaciondecafeteros.org/wp/
  - Field: "Precio interno de referencia" (COP per 125kg load)
  - Date: published inside the dropdown of the banner widget as "Fecha: YYYY-MM-DD"
  - Free, no API key required.
"""

from __future__ import annotations

import re
import html
import requests

PAGE_URL = "https://federaciondecafeteros.org/wp/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
}

_RE_FECHA = re.compile(r"Fecha:\s*</strong>\s*(\d{4}-\d{2}-\d{2})")
_RE_PRECIO = re.compile(r"Precio interno de referencia[^\d]+([\d\.]+)")


def _fetch_page() -> str | None:
    try:
        resp = requests.get(PAGE_URL, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            return resp.text
        print(f"  FNC page returned status {resp.status_code}")
    except requests.RequestException as exc:
        print(f"  FNC page fetch error: {exc}")
    return None


def fetch_fnc_precio_interno() -> dict | None:
    """
    Fetch current FNC internal reference price.

    Returns a dict with keys: fecha (YYYY-MM-DD), valor (int COP), or None if unavailable.
    """
    raw = _fetch_page()
    if raw is None:
        return None

    text = html.unescape(raw)

    fecha_match = _RE_FECHA.search(text)
    if not fecha_match:
        print("  FNC date not found in page (selector may have changed)")
        return None

    precio_match = _RE_PRECIO.search(text)
    if not precio_match:
        print("  FNC price not found in page (selector may have changed)")
        return None

    precio_raw = precio_match.group(1).replace(".", "")
    try:
        valor = int(precio_raw)
    except ValueError:
        print(f"  FNC price could not be parsed: {precio_match.group(1)!r}")
        return None

    return {
        "fecha": fecha_match.group(1),
        "valor": valor,
    }
