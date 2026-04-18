"""CoinGecko client — price, market cap, FDV, supply, historical market_chart.

Works with or without an API key, but a free Demo key is strongly recommended:
  * Without key:  ~5-10 req/min (aggressive rate-limit; deprecated for prod use)
  * Demo key:     30 req/min, 10k req/month, 365d historical
  * Pro key:      unlimited history

If `COINGECKO_API_KEY` is set, the Demo API base + `x-cg-demo-api-key` header
are used automatically.

Key derived technique: `implied_circulating_supply(t) = market_cap(t) / price(t)`.
This lets us reconstruct historical supply from the free market_chart endpoint
and therefore compute gross inflation over any window.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.config import coingecko_key
from src.http import request

PUBLIC_BASE = "https://api.coingecko.com/api/v3"
DEMO_BASE = "https://api.coingecko.com/api/v3"  # same URL; auth via header

DEFAULT_TTL = 3600  # 1 hour


def _headers() -> dict:
    key = coingecko_key()
    if key:
        return {"x-cg-demo-api-key": key, "accept": "application/json"}
    return {"accept": "application/json"}


def fetch_coin(coingecko_id: str) -> dict:
    """Fetch comprehensive coin data including market_data block."""
    return request(
        f"{PUBLIC_BASE}/coins/{coingecko_id}",
        params={
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
        },
        headers=_headers(),
        cache_key=f"coingecko:coin:{coingecko_id}",
        cache_ttl=DEFAULT_TTL,
    )


def fetch_market_chart(coingecko_id: str, days: int = 365) -> dict:
    """Fetch historical price, market cap, and volume.

    Free/Demo tier caps `days` at 365. Returns raw dict with keys:
    prices, market_caps, total_volumes — each is [[timestamp_ms, value], ...].
    """
    return request(
        f"{PUBLIC_BASE}/coins/{coingecko_id}/market_chart",
        params={"vs_currency": "usd", "days": str(days)},
        headers=_headers(),
        cache_key=f"coingecko:market_chart:{coingecko_id}:{days}",
        cache_ttl=DEFAULT_TTL,
    )


# ---------------------------------------------------------------------------
# Normalized helpers
# ---------------------------------------------------------------------------

def get_market_snapshot(coingecko_id: str) -> dict:
    """Return a flat dict of the headline valuation fields.

    Keys: price_usd, market_cap, fdv, circ_supply, total_supply, max_supply,
          volume_24h, price_change_24h_pct
    """
    coin = fetch_coin(coingecko_id)
    md = coin.get("market_data", {}) or {}
    return {
        "coingecko_id": coingecko_id,
        "price_usd": md.get("current_price", {}).get("usd"),
        "market_cap": md.get("market_cap", {}).get("usd"),
        "fdv": md.get("fully_diluted_valuation", {}).get("usd"),
        "circ_supply": md.get("circulating_supply"),
        "total_supply": md.get("total_supply"),
        "max_supply": md.get("max_supply"),
        "volume_24h": md.get("total_volume", {}).get("usd"),
        "price_change_24h_pct": md.get("price_change_percentage_24h"),
    }


def get_market_chart_df(coingecko_id: str, days: int = 365) -> pd.DataFrame:
    """Return historical market data with derived implied circulating supply.

    Columns: date, price_usd, market_cap, volume, implied_circ_supply
    """
    raw = fetch_market_chart(coingecko_id, days)

    prices = pd.DataFrame(raw.get("prices", []), columns=["timestamp", "price_usd"])
    mcaps = pd.DataFrame(raw.get("market_caps", []), columns=["timestamp", "market_cap"])
    vols = pd.DataFrame(raw.get("total_volumes", []), columns=["timestamp", "volume"])

    df = prices.merge(mcaps, on="timestamp").merge(vols, on="timestamp")
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
    # Derived supply: this is the core technique — no separate supply API call needed.
    df["implied_circ_supply"] = df["market_cap"] / df["price_usd"]
    return df[["date", "price_usd", "market_cap", "volume", "implied_circ_supply"]]


def compute_inflation(coingecko_id: str, window_days: int = 365) -> Optional[dict]:
    """Compute gross inflation rate over the window, using implied supply.

    Returns a dict with:
      start_supply, end_supply, abs_change, pct_change, pct_change_annualized

    Skips leading rows where implied supply is 0 or NaN — common for tokens
    with mid-window listings or rebrands (e.g. MKR → SKY).
    """
    df = get_market_chart_df(coingecko_id, days=window_days)
    if df.empty or len(df) < 2:
        return None

    # Drop leading/zero/NaN supply rows so the anchor is the first day with
    # real market-cap tracking.
    df = df[(df["implied_circ_supply"].notna()) & (df["implied_circ_supply"] > 0)]
    if len(df) < 2:
        return None

    start = df.iloc[0]["implied_circ_supply"]
    end = df.iloc[-1]["implied_circ_supply"]
    if not start or pd.isna(start):
        return None

    pct = (end - start) / start
    # Annualize based on actual window
    actual_days = (df.iloc[-1]["date"] - df.iloc[0]["date"]).days or window_days
    annualized = pct * (365 / actual_days)

    return {
        "window_days": actual_days,
        "start_supply": float(start),
        "end_supply": float(end),
        "abs_change": float(end - start),
        "pct_change": float(pct),
        "pct_change_annualized": float(annualized),
    }
