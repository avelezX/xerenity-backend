"""
Collector for Anserma coffee prices (published via public Google Sheet).

Source: Google Sheet pubhtml
  - Date: cell with format D/M/YYYY in the sheet header
  - 5 prices in positional order:
      [precio_base_f90, precio_ref_f94, precio_nespresso_f90,
       precio_cp_creciente_f90, precio_humedo_cereza]
  - All values in COP.
  - Free, no API key required.

The NESPRESSO and CP/CRECIENTE labels are rendered as images in the sheet and
are not present as text in the HTML, so parsing is positional. If the number of
price cells is not exactly 5, the parse aborts with an explicit error.
"""

import re
import requests
from datetime import date
from bs4 import BeautifulSoup

SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vTclf-p5H5bOjhCJQfN4sCYKM_QtNUdPoj5BBUy8RHvLlFKi0k9SRh-Hp37e_Tp3COiBrt15NLdMSlJ"
    "/pubhtml/sheet?headers=false&gid=889724279"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

PRICE_TYPES_IN_ORDER = [
    "precio_base_f90",
    "precio_ref_f94",
    "precio_nespresso_f90",
    "precio_cp_creciente_f90",
    "precio_humedo_cereza",
]

_RE_FECHA = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")
_RE_PRECIO = re.compile(r"^\s*\$\s*([\d\.]+)\s*$")


def _fetch_sheet() -> str | None:
    try:
        resp = requests.get(SHEET_URL, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            resp.encoding = "utf-8"
            return resp.text
        print(f"  Anserma sheet returned status {resp.status_code}")
    except requests.RequestException as exc:
        print(f"  Anserma sheet fetch error: {exc}")
    return None


def _parse_date(texts: list[str]) -> date | None:
    for t in texts:
        m = _RE_FECHA.match(t)
        if m:
            d, mo, y = map(int, m.groups())
            try:
                return date(y, mo, d)
            except ValueError:
                continue
    return None


def _parse_prices(texts: list[str]) -> list[int]:
    prices: list[int] = []
    for t in texts:
        m = _RE_PRECIO.match(t)
        if not m:
            continue
        raw = m.group(1).replace(".", "")
        try:
            prices.append(int(raw))
        except ValueError:
            continue
    return prices


def fetch_anserma_prices() -> dict | None:
    """
    Fetch current Anserma coffee prices.

    Returns dict with keys:
      fecha (YYYY-MM-DD), prices ({tipo_precio: int})
    or None if unavailable / unparseable.
    """
    raw = _fetch_sheet()
    if raw is None:
        return None

    soup = BeautifulSoup(raw, "lxml")
    texts = [td.get_text(strip=True) for td in soup.find_all("td")]

    fecha = _parse_date(texts)
    if fecha is None:
        print("  Anserma date not found (D/M/YYYY cell missing)")
        return None

    prices = _parse_prices(texts)
    if len(prices) != 5:
        print(
            f"  Anserma parse aborted: expected 5 price cells, found {len(prices)}. "
            f"Sheet layout may have changed."
        )
        return None

    return {
        "fecha": fecha.isoformat(),
        "prices": dict(zip(PRICE_TYPES_IN_ORDER, prices)),
    }
