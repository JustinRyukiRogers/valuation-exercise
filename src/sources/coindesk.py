"""CoinDesk Data client — historical supply with breakdown.

The headline endpoint we care about is `/onchain/v2/historical/supply/days`,
which returns daily supply data with these series (where available):
  * issued        — gross emissions
  * burned        — destroyed supply
  * staked        — currently staked supply
  * locked        — locked / vesting / governance / bridge supply
  * future        — scheduled future supply (proxy for unlock pressure)
  * circulating   — current circulating supply

Requires a free API key (https://developers.coindesk.com/).

Coverage caveat: BTC and ETH are well-covered. Coverage for the long tail of
peer-set tokens (LINK, AAVE, etc.) needs to be audited per-token; the helper
`probe_asset()` below makes that easy.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.config import coindesk_key
from src.http import request

BASE_URL = "https://data-api.coindesk.com"
DEFAULT_TTL = 3600  # 1 hour


def _headers() -> dict:
    key = coindesk_key()
    if not key:
        raise RuntimeError(
            "COINDESK_API_KEY is not set. Add it to .env "
            "(free signup at https://developers.coindesk.com/)."
        )
    return {"Authorization": f"Apikey {key}", "accept": "application/json"}


def fetch_historical_supply(
    asset: str,
    *,
    limit: int = 365,
    groups: str = "ID,SUPPLY",
) -> dict:
    """Fetch daily historical supply with breakdown for `asset` (e.g. 'ETH').

    `groups` controls which field families are returned. 'SUPPLY' is the one we
    care about; 'ID' is essentially metadata. Pass additional groups (e.g.
    'OHLCV') if you need them.
    """
    return request(
        f"{BASE_URL}/onchain/v2/historical/supply/days",
        params={"asset": asset, "groups": groups, "limit": str(limit)},
        headers=_headers(),
        cache_key=f"coindesk:supply:{asset}:{limit}:{groups}",
        cache_ttl=DEFAULT_TTL,
    )


# ---------------------------------------------------------------------------
# Normalized helpers
# ---------------------------------------------------------------------------

# CoinDesk returns columns prefixed with SUPPLY_. We map to shorter lowercase
# names for downstream use. SUPPLY_BURNT (not BURNED) is the real field name.
SUPPLY_COLUMN_MAP = {
    "SUPPLY_CIRCULATING": "circulating",
    "SUPPLY_TOTAL": "total",
    "SUPPLY_MAX": "max",
    "SUPPLY_ISSUED": "issued",
    "SUPPLY_BURNT": "burned",
    "SUPPLY_STAKED": "staked",
    "SUPPLY_LOCKED": "locked",
    "SUPPLY_FUTURE": "future",
}

# CoinDesk uses -1 as a sentinel meaning "series not applicable / not tracked".
SENTINEL_VALUE = -1


def get_supply_timeseries(asset: str, days: int = 365) -> pd.DataFrame:
    """Return a daily DataFrame of CoinDesk supply breakdown.

    Columns (where present): date, circulating, total, max, issued, burned,
    staked, locked, future. `-1` sentinel values are converted to NaN. Series
    that are entirely `-1` across the window are dropped — those represent
    dimensions CoinDesk does not track for this asset.
    """
    raw = fetch_historical_supply(asset, limit=days)
    rows = raw.get("Data", [])
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    if "TIMESTAMP" in df.columns:
        df["date"] = pd.to_datetime(df["TIMESTAMP"], unit="s")
    elif "DATE" in df.columns:
        df["date"] = pd.to_datetime(df["DATE"])

    rename_map = {k: v for k, v in SUPPLY_COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    supply_cols = [v for v in SUPPLY_COLUMN_MAP.values() if v in df.columns]
    for col in supply_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].where(df[col] != SENTINEL_VALUE)

    # Drop series that are entirely missing (CoinDesk doesn't track them here)
    meaningful = [c for c in supply_cols if df[c].notna().any()]
    keep = ["date"] + meaningful
    return df[keep].sort_values("date").reset_index(drop=True)


def get_inflation_breakdown(asset: str, window_days: int = 365) -> Optional[dict]:
    """Compute net inflation over the window using CoinDesk supply data.

    Returns a dict with:
      window_days, start_circulating, end_circulating,
      total_issued, total_burned, net_change, net_change_pct, annualized_pct
    """
    df = get_supply_timeseries(asset, days=window_days)
    if df.empty or "circulating" not in df.columns:
        return None

    # Filter to the actual window
    df = df.dropna(subset=["circulating"]).sort_values("date")
    if len(df) < 2:
        return None

    start = df.iloc[0]
    end = df.iloc[-1]
    actual_days = (end["date"] - start["date"]).days or window_days

    issued = (end.get("issued", 0) or 0) - (start.get("issued", 0) or 0) if "issued" in df.columns else None
    burned = (end.get("burned", 0) or 0) - (start.get("burned", 0) or 0) if "burned" in df.columns else None

    net_change = end["circulating"] - start["circulating"]
    net_pct = net_change / start["circulating"] if start["circulating"] else None
    annualized = (net_pct * (365 / actual_days)) if net_pct is not None else None

    return {
        "asset": asset,
        "window_days": actual_days,
        "start_circulating": float(start["circulating"]),
        "end_circulating": float(end["circulating"]),
        "total_issued": float(issued) if issued is not None else None,
        "total_burned": float(burned) if burned is not None else None,
        "net_change": float(net_change),
        "net_change_pct": float(net_pct) if net_pct is not None else None,
        "annualized_pct": float(annualized) if annualized is not None else None,
    }


def get_supply_snapshot(asset: str) -> Optional[dict]:
    """Return a flat snapshot of the most recent supply breakdown for `asset`.

    Useful for the peer-set summary table.
    """
    df = get_supply_timeseries(asset, days=2)
    if df.empty:
        return None
    last = df.iloc[-1]
    snap = {"asset": asset, "as_of": last["date"].isoformat() if hasattr(last["date"], "isoformat") else str(last["date"])}
    for col in SUPPLY_COLUMN_MAP.values():
        if col in df.columns:
            snap[col] = float(last[col]) if pd.notna(last[col]) else None
    return snap


def probe_asset(asset: str) -> dict:
    """Diagnostic — report which supply series are available for `asset`.

    Use this to audit which peer-set tokens have full breakdown coverage
    versus which only have basic circulating supply.
    """
    df = get_supply_timeseries(asset, days=2)
    if df.empty:
        return {"asset": asset, "covered": False, "available_columns": []}
    return {
        "asset": asset,
        "covered": True,
        "available_columns": [c for c in df.columns if c != "date"],
        "row_count": len(df),
    }
