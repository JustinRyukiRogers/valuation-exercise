
from __future__ import annotations

import time
from typing import Optional

import pandas as pd
import requests

from src.config import dune_key
from src.http import request as http_get
from src import cache

BASE_URL = "https://api.dune.com/api/v1"

# Poll every 5s for up to 5 minutes — most small queries finish in <30s.
POLL_INTERVAL_S = 5
MAX_POLL_S = 300

# Default cache TTL for query results (1 day)
DEFAULT_TTL = 86_400


def _headers() -> dict:
    key = dune_key()
    if not key:
        raise RuntimeError(
            "DUNE_API_KEY is not set. Add it to .env "
            "(free signup at https://dune.com/settings/api)."
        )
    return {"X-Dune-API-Key": key, "accept": "application/json"}


# Low-level queries


def _execute(query_id: int, params: Optional[dict] = None) -> str:
    """Kick off a query execution; returns the execution_id."""
    body = {"query_parameters": params} if params else {}
    resp = requests.post(
        f"{BASE_URL}/query/{query_id}/execute",
        headers=_headers(),
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["execution_id"]


def _poll(execution_id: str) -> None:
    """Block until the execution completes or we hit MAX_POLL_S."""
    start = time.time()
    while time.time() - start < MAX_POLL_S:
        resp = requests.get(
            f"{BASE_URL}/execution/{execution_id}/status",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        state = resp.json().get("state")
        if state == "QUERY_STATE_COMPLETED":
            return
        if state in ("QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED", "QUERY_STATE_EXPIRED"):
            raise RuntimeError(f"Dune execution {execution_id} ended in {state}")
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(f"Dune execution {execution_id} did not complete in {MAX_POLL_S}s")


def _fetch_results(execution_id: str) -> list[dict]:
    resp = requests.get(
        f"{BASE_URL}/execution/{execution_id}/results",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", {}).get("rows", [])


def execute_query(
    query_id: int,
    params: Optional[dict] = None,
    *,
    cache_ttl: int = DEFAULT_TTL,
) -> pd.DataFrame:

    cache_key = f"dune:execute:{query_id}:{params or {}}"
    cached = cache.get(cache_key, ttl_seconds=cache_ttl)
    if cached is not None:
        return pd.DataFrame(cached)

    execution_id = _execute(query_id, params)
    _poll(execution_id)
    rows = _fetch_results(execution_id)
    cache.set(cache_key, rows)
    return pd.DataFrame(rows)


# Latest-results


def fetch_latest_results(query_id: int, cache_ttl: int = DEFAULT_TTL) -> pd.DataFrame:

    cache_key = f"dune:latest:{query_id}"
    cached = cache.get(cache_key, ttl_seconds=cache_ttl)
    if cached is not None:
        return pd.DataFrame(cached)

    try:
        raw = http_get(
            f"{BASE_URL}/query/{query_id}/results",
            headers=_headers(),
            cache_key=None,
        )
    except RuntimeError as e:
        if "404" in str(e):
            # No prior execution on Dune's servers — run the query fresh.
            return execute_query(query_id, cache_ttl=cache_ttl)
        raise

    rows = raw.get("result", {}).get("rows", [])
    cache.set(cache_key, rows)
    return pd.DataFrame(rows)


# flagship queries

FLAGSHIP_QUERIES = {


    # Q1: SOL base-fee burn (30d actuals, annualized).
    # Columns: sol_burned_30d_approx, sol_burned_365d_approx, sol_burn_rate_annualized_approx,
    #          sol_burned_30d_base_fee, sol_burned_365d_base_fee, sol_burn_rate_annualized_base_fee,
    #          as_of_date
    "sol_base_fee_burn": 7328502,

    # Q2: LINK treasury outflow from the 15 non-circulating treasury shards (365d).
    # Columns: link_treasury_outflow_tokens_365d, link_treasury_outflow_annualized_pct, as_of_date
    "link_treasury_outflow": 7328638,

    # Q3: AAVE buyback spend (USD) by the Aavenomics TWAP executor bots.
    # Columns: aave_buyback_spend_usd_365d, aave_tokens_bought_365d,
    #          aave_buyback_spend_usd_30d, aave_tokens_bought_30d,
    #          trade_count_365d, as_of_date
    "aave_buyback_spend": 7328824,

    # Q5: Dormancy as "active supply" — sum of balances for addresses whose
    "sol_dormancy": 7328755,            # solana_utils.latest_balances
    "evm_dormancy_ethereum": 7328758,   # tokens_ethereum.balances (LINK/AAVE/UNI/LDO/CRV)
    "evm_dormancy_optimism": 7328772,   # tokens_optimism.balances (OP)
    # Native ETH dormancy: no curated balance table exists on Dune, so this
    "eth_dormancy": 7332769,

    # Q6: UNI Firepit burn — UNI tokens sent to the burn address on Ethereum
    # Columns: time, amount_raw, amount_usd, days, raw_cum, usd_cum,
    #          projected_burn, projected_burn_usd
    "uni_firepit_burn": 6430914,
}


def dormancy_share(contract_address: str) -> pd.DataFrame:
    """Return 1yr+ dormant share of circulating supply for an ERC-20.

    Output columns: address_count, dormant_tokens, circulating_supply,
                    dormant_share_pct.
    """
    qid = FLAGSHIP_QUERIES["erc20_dormancy"]
    if qid is None:
        raise NotImplementedError(
            "Flagship dormancy query not yet registered in FLAGSHIP_QUERIES. "
            "Author the SQL on dune.com, then set FLAGSHIP_QUERIES['erc20_dormancy'] = <id>."
        )
    return fetch_latest_results(qid).assign(contract_address=contract_address)


def sky_smart_burn(lookback_days: int = 30) -> pd.DataFrame:
    qid = FLAGSHIP_QUERIES["sky_smart_burn"]
    if qid is None:
        raise NotImplementedError("Set FLAGSHIP_QUERIES['sky_smart_burn']")
    return fetch_latest_results(qid)


def aave_buyback_spend() -> pd.DataFrame:
    qid = FLAGSHIP_QUERIES["aave_buyback_spend"]
    if qid is None:
        raise NotImplementedError("Set FLAGSHIP_QUERIES['aave_buyback_spend']")
    return fetch_latest_results(qid)


def sol_base_fee_burn() -> pd.DataFrame:
    """SOL burned via the 50% base-fee mechanic (30d actuals, annualized).

    Output columns: sol_burned_30d_approx, sol_burned_365d_approx,
                    sol_burn_rate_annualized_approx, sol_burned_30d_base_fee,
                    sol_burned_365d_base_fee, sol_burn_rate_annualized_base_fee,
                    as_of_date
    Use sol_burn_rate_annualized_base_fee as the canonical figure — the approx
    columns include priority fees (not actually burned) and overstate by ~9x.
    """
    qid = FLAGSHIP_QUERIES["sol_base_fee_burn"]
    if qid is None:
        raise NotImplementedError("Set FLAGSHIP_QUERIES['sol_base_fee_burn']")
    return fetch_latest_results(qid)


def link_treasury_outflow() -> pd.DataFrame:
    """LINK tokens released from the non-circulating multisig over 365d.

    Output columns: link_treasury_outflow_tokens_365d,
                    link_treasury_outflow_annualized_pct, as_of_date
    """
    qid = FLAGSHIP_QUERIES["link_treasury_outflow"]
    if qid is None:
        raise NotImplementedError("Set FLAGSHIP_QUERIES['link_treasury_outflow']")
    return fetch_latest_results(qid)



def sol_dormancy() -> pd.DataFrame:
    """Active SOL balance over the 180d window."""
    qid = FLAGSHIP_QUERIES["sol_dormancy"]
    if qid is None:
        raise NotImplementedError("Set FLAGSHIP_QUERIES['sol_dormancy']")
    return execute_query(qid)


def evm_dormancy_ethereum() -> pd.DataFrame:
    """Active ERC-20 balance per token on Ethereum (LINK/AAVE/UNI/LDO/CRV), 180d."""
    qid = FLAGSHIP_QUERIES["evm_dormancy_ethereum"]
    if qid is None:
        raise NotImplementedError("Set FLAGSHIP_QUERIES['evm_dormancy_ethereum']")
    df = execute_query(qid)
    if "active_sender_count" in df.columns and "active_address_count" not in df.columns:
        df = df.rename(columns={"active_sender_count": "active_address_count"})
    return df


def evm_dormancy_optimism() -> pd.DataFrame:
    """Active OP balance on Optimism (180d)."""
    qid = FLAGSHIP_QUERIES["evm_dormancy_optimism"]
    if qid is None:
        raise NotImplementedError("Set FLAGSHIP_QUERIES['evm_dormancy_optimism']")
    df = execute_query(qid)
    if "active_sender_count" in df.columns and "active_address_count" not in df.columns:
        df = df.rename(columns={"active_sender_count": "active_address_count"})
    return df


def uni_firepit_burn() -> pd.DataFrame:
    """UNI tokens burned via the Firepit mechanism (ETH + Unichain)."""
    qid = FLAGSHIP_QUERIES["uni_firepit_burn"]
    if qid is None:
        raise NotImplementedError("Set FLAGSHIP_QUERIES['uni_firepit_burn']")
    df = fetch_latest_results(qid)
    # Sort descending by time so iloc[0] is always the latest day
    if "time" in df.columns:
        df = df.sort_values("time", ascending=False).reset_index(drop=True)
    return df


def eth_dormancy() -> pd.DataFrame:
    """Active native-ETH balance via balance reconstruction (180d)."""
    qid = FLAGSHIP_QUERIES["eth_dormancy"]
    if qid is None:
        raise NotImplementedError("Set FLAGSHIP_QUERIES['eth_dormancy']")
    return fetch_latest_results(qid)


def dormancy_summary() -> pd.DataFrame:
    """Unified active-balance figures across SOL, native ETH, ERC-20s, and OP."""
    parts = []
    sol = sol_dormancy()
    if not sol.empty:
        sol = sol.assign(holding_supply_total=pd.NA)
        parts.append(sol[["symbol", "active_supply_180d", "holding_supply_total",
                          "active_address_count", "as_of_date"]])
    eth = eth_dormancy()
    if not eth.empty:
        eth = eth.rename(columns={"active_holder_count": "active_address_count"}).assign(
            holding_supply_total=pd.NA
        )
        parts.append(eth[["symbol", "active_supply_180d", "holding_supply_total",
                          "active_address_count", "as_of_date"]])
    parts.append(evm_dormancy_ethereum())
    parts.append(evm_dormancy_optimism())
    return pd.concat(parts, ignore_index=True)


# Auth sanity check


def check_auth() -> dict:
    """Hit a cheap endpoint to confirm the key is live. Returns the raw response."""
    resp = requests.get(
        f"{BASE_URL}/user/context",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
