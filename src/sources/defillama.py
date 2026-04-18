"""DeFiLlama client — TVL, fees, and revenue data.

No API key required. Endpoints used (all confirmed free as of April 2026):
  * /protocol/{slug}              — protocol detail + TVL history
  * /summary/fees/{slug}          — fee and revenue totals + daily chart
  * /overview/fees                — global fees overview (all protocols)
  * /protocols                    — all protocols list (includes CEX entries)
  * /chains                       — per-chain TVL

Paywalled (don't use): /emissions, /emission/{slug}, /treasuries
"""
from __future__ import annotations

from typing import Literal, Optional

import pandas as pd

from src.http import request

BASE_URL = "https://api.llama.fi"

# Cache TTL in seconds — 1 hour is fine since we're looking at daily granularity
DEFAULT_TTL = 1

DataType = Literal["dailyFees", "dailyRevenue"]


def fetch_protocol(slug: str) -> dict:
    """Fetch protocol detail including TVL history.

    Returns the raw JSON dict; caller can navigate `tvl`, `currentChainTvls`, etc.
    """
    return request(
        f"{BASE_URL}/protocol/{slug}",
        cache_key=f"defillama:protocol:{slug}",
        cache_ttl=DEFAULT_TTL,
    )


def fetch_fees_summary(slug: str, data_type: DataType = "dailyFees") -> dict:
    """Fetch fee/revenue summary for a protocol.

    `data_type`:
      * "dailyFees"    — total ecosystem fees paid by users
      * "dailyRevenue" — protocol-retained revenue (after operator/LP payments)
    """
    return request(
        f"{BASE_URL}/summary/fees/{slug}",
        params={"dataType": data_type},
        cache_key=f"defillama:fees:{slug}:{data_type}",
        cache_ttl=DEFAULT_TTL,
    )


def fetch_protocols() -> list[dict]:
    """Fetch all protocols with TVL and metadata. Includes CEX entries."""
    return request(
        f"{BASE_URL}/protocols",
        cache_key="defillama:protocols",
        cache_ttl=DEFAULT_TTL,
    )


def fetch_chains() -> list[dict]:
    """Fetch per-chain TVL data."""
    return request(
        f"{BASE_URL}/chains",
        cache_key="defillama:chains",
        cache_ttl=DEFAULT_TTL,
    )


# ---------------------------------------------------------------------------
# Normalized helpers — these extract the bits our metric layer actually needs.
# ---------------------------------------------------------------------------

def _chain_tvl_lookup(slug: str) -> Optional[float]:
    """Look up a chain's TVL via /chains. Tries multiple fuzzy matches:
    exact slug, slug stripped of `-mainnet`, then equality against the
    chain's `name`, `gecko_id`, or `tokenSymbol`.

    Matching tokenSymbol catches the case where the fees slug differs from
    the chain identifier (e.g. fees='op-mainnet' but chain entry is
    name='Optimism', tokenSymbol='OP').
    """
    chains = fetch_chains()
    candidates = {slug.lower(), slug.lower().replace("-mainnet", "")}
    for c in chains:
        name = (c.get("name") or "").lower()
        gecko = (c.get("gecko_id") or "").lower()
        token = (c.get("tokenSymbol") or "").lower()
        if name in candidates or gecko in candidates or (token and token in candidates):
            return c.get("tvl")
    return None


def get_protocol_summary(slug: str) -> dict:
    """Return a flat dict of fee + revenue totals for one protocol or chain.

    Keys:
      fees_24h, fees_7d, fees_30d, fees_all_time
      revenue_24h, revenue_7d, revenue_30d, revenue_all_time
      tvl_current, category

    Handles three slug patterns:
      * Plain protocol  (e.g. 'aave')        — both /protocol and /summary/fees work
      * Chain alias     (e.g. 'ethereum')    — /protocol works, TVL via /chains as backup
      * Chain-only slug (e.g. 'op-mainnet')  — only /summary/fees works; TVL via /chains
    """
    fees = fetch_fees_summary(slug, "dailyFees")
    try:
        revenue = fetch_fees_summary(slug, "dailyRevenue")
    except RuntimeError:
        # Some protocols (e.g. pure oracle networks) have no revenue series
        revenue = {}

    # /protocol/{slug} 400s for chain-only slugs like 'op-mainnet'. Catch and
    # fall through to /chains.
    tvl_current: Optional[float] = None
    try:
        protocol = fetch_protocol(slug)
        tvl_series = protocol.get("tvl", [])
        if tvl_series:
            tvl_current = tvl_series[-1]["totalLiquidityUSD"]
    except RuntimeError:
        pass

    if tvl_current is None:
        tvl_current = _chain_tvl_lookup(slug)

    return {
        "slug": slug,
        "name": fees.get("name") or slug.capitalize(),
        "category": fees.get("category"),
        "fees_24h": fees.get("total24h"),
        "fees_7d": fees.get("total7d"),
        "fees_30d": fees.get("total30d"),
        "fees_all_time": fees.get("totalAllTime"),
        "revenue_24h": revenue.get("total24h"),
        "revenue_7d": revenue.get("total7d"),
        "revenue_30d": revenue.get("total30d"),
        "revenue_all_time": revenue.get("totalAllTime"),
        "tvl_current": tvl_current,
    }


def get_fees_timeseries(slug: str, data_type: DataType = "dailyFees") -> pd.DataFrame:
    """Return a daily-granularity DataFrame with `date` and `value` columns."""
    raw = fetch_fees_summary(slug, data_type)
    chart = raw.get("totalDataChart", [])
    if not chart:
        return pd.DataFrame(columns=["date", "value"])
    df = pd.DataFrame(chart, columns=["timestamp", "value"])
    df["date"] = pd.to_datetime(df["timestamp"], unit="s")
    return df[["date", "value"]]


def get_tvl_timeseries(slug: str) -> pd.DataFrame:
    """Return a daily DataFrame of protocol TVL (USD)."""
    raw = fetch_protocol(slug)
    tvl = raw.get("tvl", [])
    if not tvl:
        return pd.DataFrame(columns=["date", "tvl_usd"])
    df = pd.DataFrame(tvl)
    df["date"] = pd.to_datetime(df["date"], unit="s")
    return df.rename(columns={"totalLiquidityUSD": "tvl_usd"})[["date", "tvl_usd"]]


def find_cex_balance(symbol: str, exchange: Optional[str] = None) -> list[dict]:
    """Search the `/protocols` list for CEX entries matching a token symbol.

    DeFiLlama tracks known exchange wallet balances as pseudo-protocols (e.g.
    "Binance CEX", "Coinbase CEX"). This is a free proxy for exchange balance
    without paying for CryptoQuant. Returns the raw entries; coverage varies.
    """
    protocols = fetch_protocols()
    hits = []
    for p in protocols:
        name = p.get("name", "")
        if "CEX" not in name:
            continue
        if exchange and exchange.lower() not in name.lower():
            continue
        tokens = p.get("tokens", {}) or {}
        if symbol.upper() in {k.upper() for k in tokens.keys()}:
            hits.append(p)
    return hits
