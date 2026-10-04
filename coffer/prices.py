"""Latest prices from public endpoints.

This is the only network access in the app. Requests carry nothing but the
symbols being priced: no account, no amounts, no identifiers. With offline
mode on, nothing leaves the device and prices are typed in by hand.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import date

from . import store
from .errors import Offline

TIMEOUT_SECONDS = 10
USER_AGENT = "Mozilla/5.0 (Macintosh) Coffer/0.1"


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed https hosts
        return json.loads(response.read().decode())


def _yahoo(symbol: str, currency: str) -> float:
    """Yahoo's chart endpoint is unofficial and keyless; it can change without
    notice, which is why every asset can fall back to manual prices."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol) + "?range=1d&interval=1d"
    meta = _get_json(url)["chart"]["result"][0]["meta"]
    quoted = (meta.get("currency") or "").upper()
    price = float(meta["regularMarketPrice"])
    if quoted and quoted != currency:
        raise ValueError(f"quoted in {quoted}, not {currency}: pick a listing in {currency}")
    return price


def _coingecko(ids: list[str], currency: str) -> dict[str, float]:
    query = urllib.parse.urlencode({"ids": ",".join(ids), "vs_currencies": currency.lower()})
    data = _get_json("https://api.coingecko.com/api/v3/simple/price?" + query)
    return {coin: float(values[currency.lower()]) for coin, values in data.items() if currency.lower() in values}


def refresh(conn: sqlite3.Connection) -> list[dict]:
    settings = store.get_settings(conn)
    if settings["offline_mode"]:
        raise Offline()
    currency = settings["currency"]
    today = date.today().isoformat()
    assets = [a for a in store.list_assets(conn) if a["price_source"] != "manual"]
    results: list[dict] = []
    fetched: list[tuple[int, float]] = []

    coins = [a for a in assets if a["price_source"] == "coingecko"]
    if coins:
        try:
            quotes = _coingecko(sorted({a["source_id"] for a in coins}), currency)
        except Exception as exc:  # network errors, HTTP errors, malformed JSON
            quotes = {}
            error = _describe(exc)
        else:
            error = "coin id not found"
        for asset in coins:
            if asset["source_id"] in quotes:
                fetched.append((asset["id"], quotes[asset["source_id"]]))
                results.append({"symbol": asset["symbol"], "ok": True, "price": quotes[asset["source_id"]]})
            else:
                results.append({"symbol": asset["symbol"], "ok": False, "message": error})

    for asset in (a for a in assets if a["price_source"] == "yahoo"):
        try:
            price = _yahoo(asset["source_id"] or asset["symbol"], currency)
        except Exception as exc:
            results.append({"symbol": asset["symbol"], "ok": False, "message": _describe(exc)})
        else:
            fetched.append((asset["id"], price))
            results.append({"symbol": asset["symbol"], "ok": True, "price": price})

    with conn:
        conn.execute("BEGIN")
        conn.executemany(
            "INSERT OR REPLACE INTO prices (asset_id, date, price, source) VALUES (?, ?, ?, 'online')",
            [(asset_id, today, price) for asset_id, price in fetched],
        )
    return results


def _describe(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, (KeyError, IndexError, TypeError)):
        return "symbol not found"
    return "service unreachable"
