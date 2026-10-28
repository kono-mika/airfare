"""Currencies: the one AirFare compares prices in (picked in Settings), and converting the others into it.

Sources show prices in their own currency: Aviasales.ru in rubles, Skyscanner in whatever its site is set
to. AirFare converts every price to the chosen currency with the day's exchange rates before anything is
compared, so the analyst, the alerts and the price history always see one currency. Rates come from the
European Central Bank (euro reference rates) with open.er-api.com filling in what the ECB doesn't publish,
such as the ruble. They are kept in data/rates.json, so a check without internet uses the last ones.
"""
from __future__ import annotations

import json
import logging
import math
import re
import urllib.request
from datetime import datetime, timedelta

from .config import DATA_DIR, read_json, write_json

log = logging.getLogger(__name__)

# The currencies Settings offers (the ECB's daily list plus the ruble), with the sign the pages show.
CURRENCIES = {
    "EUR": "€", "GBP": "£", "USD": "$", "RUB": "₽",
    "CHF": "CHF", "PLN": "zł", "CZK": "Kč", "HUF": "Ft", "RON": "lei", "BGN": "лв", "SEK": "kr", "NOK": "kr",
    "DKK": "kr", "ISK": "kr", "TRY": "₺", "ILS": "₪", "AUD": "A$", "NZD": "NZ$", "CAD": "C$", "MXN": "MX$",
    "BRL": "R$", "ZAR": "R", "JPY": "¥", "CNY": "CN¥", "HKD": "HK$", "SGD": "S$", "KRW": "₩", "INR": "₹",
    "THB": "฿", "MYR": "RM", "IDR": "Rp", "PHP": "₱",
}
MAIN = ("EUR", "GBP", "USD", "RUB")        # the four big buttons in Settings; the others sit in a list
# Signs written after the amount, with a space, as their countries do: 1 234 Kč, 15 400 ₽.
AFTER = frozenset({"RUB", "CHF", "PLN", "CZK", "HUF", "RON", "BGN", "SEK", "NOK", "DKK", "ISK", "MYR", "IDR"})
DEFAULT = "EUR"

RATES_FILE = DATA_DIR / "rates.json"
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
OPEN_URL = "https://open.er-api.com/v6/latest/EUR"
# open.er-api.com's free rates ask for this link wherever they are shown. It is the provider's wording, so it
# stays in English in every language, and it is fixed here: nothing a download says ever goes into it.
CREDIT_HTML = '<a href="https://www.exchangerate-api.com">Rates By Exchange Rate API</a>'
CREDIT_MD = "[Rates By Exchange Rate API](https://www.exchangerate-api.com)"
MAX_AGE = timedelta(hours=12)
MAX_JUMP = 0.5          # a rate that moved more than 50% since the last download is a data error, not news

# Signs as sources print them, longest first so "US$" wins over "$".
_SIGNS = [("US$", "USD"), ("C$", "CAD"), ("CA$", "CAD"), ("A$", "AUD"), ("AU$", "AUD"), ("NZ$", "NZD"),
          ("HK$", "HKD"), ("S$", "SGD"), ("R$", "BRL"), ("MX$", "MXN"), ("€", "EUR"), ("£", "GBP"), ("₽", "RUB"),
          ("руб", "RUB"), ("₹", "INR"), ("₩", "KRW"), ("CN¥", "CNY"), ("¥", "JPY"), ("zł", "PLN"), ("Kč", "CZK"),
          ("Ft", "HUF"), ("₺", "TRY"), ("lei", "RON"), ("CHF", "CHF"), ("₪", "ILS"), ("฿", "THB"), ("₱", "PHP"),
          ("лв", "BGN"), ("RM", "MYR"), ("Rp", "IDR")]
# "$" and "kr" depend on the site: skyscanner.ca shows Canadian dollars, skyscanner.se Swedish kronor.
_DOLLAR_SITES = {".ca": "CAD", ".com.au": "AUD", ".co.nz": "NZD", ".com.mx": "MXN", ".com.sg": "SGD",
                 ".com.hk": "HKD", ".com.br": "BRL"}
_KRONA_SITES = {".se": "SEK", ".no": "NOK", ".dk": "DKK"}
_CODE_RE = re.compile(r"\b([A-Z]{3})\b")


def detect(text: str, site: str = "") -> str | None:
    """The ISO code of the currency a price text is in ("178 €" -> EUR), or None when it can't tell."""
    text = text or ""
    for sign, code in _SIGNS:
        if sign in text:
            return code
    site = (site or "").lower()
    if "$" in text:
        return next((c for end, c in _DOLLAR_SITES.items() if site.endswith(end)), "USD")
    if re.search(r"\bkr\b", text):
        return next((c for end, c in _KRONA_SITES.items() if site.endswith(end)), "SEK")
    m = _CODE_RE.search(text)
    return m.group(1) if m else None


def sign(code: str) -> str:
    return CURRENCIES.get((code or "").upper(), (code or "").upper())


def fmt(amount: float, code: str) -> str:
    """A price as the dashboard and notifications show it: €214, £150, $230, 15 400 ₽, 1 234 Kč."""
    code = (code or DEFAULT).upper()
    whole = f"{round(amount):,}"
    if code not in CURRENCIES:
        return f"{whole} {code}"
    if code in AFTER:
        return whole.replace(",", " ") + " " + CURRENCIES[code]
    return CURRENCIES[code] + whole


def floor_price(amount: float) -> float:
    """Alert targets in whole units, rounded down: "€164 or less" is exactly what is checked."""
    return float(math.floor(amount + 1e-9))


# ----- exchange rates ---------------------------------------------------------------------

def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "AirFare"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read(2_000_000)


def _sane(rates) -> dict[str, float]:
    """Only well-formed codes with positive, finite rates (units per euro)."""
    out = {}
    if not isinstance(rates, dict):
        return out
    for code, value in rates.items():
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if re.fullmatch(r"[A-Z]{3}", str(code)) and 0 < v < 1e7 and math.isfinite(v):
            out[str(code)] = v
    return out


def fetch_rates() -> dict:
    """Today's rates per euro: the ECB's, plus open.er-api.com for currencies the ECB doesn't publish."""
    rates: dict[str, float] = {}
    sources, day = [], None
    try:
        data = json.loads(_get(OPEN_URL).decode("utf-8"))
        if isinstance(data, dict) and data.get("result") == "success" and data.get("base_code") == "EUR":
            rates.update(_sane(data.get("rates")))
            sources.append("open.er-api.com")
    except Exception as e:                    # whatever the service sends, a check must not fail over it
        log.warning("couldn't load exchange rates from open.er-api.com: %s", e)
    try:
        xml = _get(ECB_URL).decode("utf-8")
        ecb = _sane(dict(re.findall(r"currency=['\"]([A-Z]{3})['\"]\s+rate=['\"]([\d.]+)['\"]", xml)))
        if ecb:
            rates.update(ecb)                 # the ECB's own figures win where both have a rate
            sources.insert(0, "European Central Bank")
            m = re.search(r"time=['\"](\d{4}-\d{2}-\d{2})['\"]", xml)
            day = m.group(1) if m else None
    except Exception as e:
        log.warning("couldn't load exchange rates from the ECB: %s", e)
    if not rates:
        raise OSError("no exchange rates available")
    rates["EUR"] = 1.0
    return {"fetched": datetime.now().isoformat(timespec="minutes"), "date": day or datetime.now().date().isoformat(),
            "source": " and ".join(sources), "rates": rates}


def rates(refresh: bool = True) -> dict:
    """The rate table {"rates": {code: units per euro}, "date", "source"}; empty rates if never loaded."""
    cached = read_json(RATES_FILE, {}) or {}
    try:
        fresh = datetime.now() - datetime.fromisoformat(cached.get("fetched", "")) < MAX_AGE
    except ValueError:
        fresh = False
    if refresh and not fresh:
        try:
            cached = _steady(fetch_rates(), cached)
            write_json(RATES_FILE, cached)
        except OSError as e:
            log.warning("using %s exchange rates: %s", "saved" if cached.get("rates") else "no", e)
    cached.setdefault("rates", {})
    cached["rates"] = {**_sane(cached["rates"]), "EUR": 1.0}
    return cached


def _steady(new: dict, old: dict) -> dict:
    """New rates, except any that jumped implausibly since the last download: those keep their old value,
    so one bad figure can't turn a fare into a fake LOW PRICE. A jump the next download repeats is real (a
    currency that moved while AirFare wasn't running, or an old rates file) and goes through then; without
    that, the saved value would be compared against forever."""
    before = _sane(old.get("rates") if isinstance(old, dict) else None)
    rejected = old.get("rejected") if isinstance(old, dict) and isinstance(old.get("rejected"), dict) else {}
    held = {}
    for code, value in list(new["rates"].items()):
        prev = before.get(code)
        if prev and abs(value - prev) / prev > MAX_JUMP:
            last = rejected.get(code)
            if isinstance(last, (int, float)) and last > 0 and abs(value - last) / last <= MAX_JUMP:
                log.warning("taking the new %s rate %s (was %s): two downloads in a row agree", code, value, prev)
                continue
            log.warning("ignoring the new %s rate %s (was %s): too big a jump", code, value, prev)
            new["rates"][code] = prev
            held[code] = value
    if held:
        new["rejected"] = held
    return new


def convert(amount: float, src: str, dst: str, table: dict) -> float | None:
    """amount in src as dst, or None without a rate for one of them."""
    src, dst = (src or "").upper(), (dst or "").upper()
    if src == dst:
        return float(amount)
    r = (table or {}).get("rates") or {}
    if src not in r or dst not in r:
        return None
    return float(amount) / r[src] * r[dst]


def rate_line(dst: str, table: dict, also: tuple[str, ...] = ()) -> str:
    """'1 EUR = 0.84 GBP = 1.12 USD = 91.20 RUB' style line, for the analyst and the dashboard: the user's
    currency, the main ones, and any others asked for (the sites' own currencies)."""
    r = (table or {}).get("rates") or {}
    codes = [c for c in dict.fromkeys((dst, *MAIN, *also)) if c in r]
    if dst not in r or len(codes) < 2:
        return ""
    parts = [f"1 {dst}"] + [f"{r[c] / r[dst]:.4g} {c}" for c in codes if c != dst]
    return " = ".join(parts)


def needs_credit(table: dict | None) -> bool:
    """Whether these rates came partly from open.er-api.com, so CREDIT_HTML goes wherever they are shown."""
    source = (table or {}).get("source")
    return isinstance(source, str) and "open.er-api.com" in source
