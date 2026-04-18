"""Dune Analytics client — flagship on-chain queries.

Used for metrics CoinDesk + Etherscan can't cover:
  * True age-based dormancy (1yr+ untouched ERC-20 balances)
  * Project-specific events (SKY Smart Burn, MKR/AAVE buybacks)

Budget: Dune free tier allows 2,500 query executions / month. We assume
daily refresh (≈30 runs/day/query ≈ 90/month per query) so we can afford
3-5 flagship queries without going over budget.

API flow (see https://docs.dune.com/api-reference/):
  1. POST /v1/query/{id}/execute      → returns execution_id
  2. GET  /v1/execution/{id}/status    → poll until state == QUERY_STATE_COMPLETED
  3. GET  /v1/execution/{id}/results   → fetch the result rows

To avoid hammering on every notebook run we also support:
  * execute_query(cache_ttl=86400)   — cache results for a day
  * fetch_latest_results(query_id)   — read the last saved execution without
                                        re-running (0 credits).

Writing the SQL is out of scope for this module — queries are authored
interactively on dune.com and referenced here by their numeric ID. This
keeps the Python side stable and makes the SQL reviewable in the Dune UI.
"""
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


# ---------------------------------------------------------------------------
# Low-level query execution (costs 1 credit)
# ---------------------------------------------------------------------------


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
    """Execute `query_id` on Dune and return rows as a DataFrame.

    Uses the project's on-disk cache (data/cache/) to avoid re-running the
    same query within `cache_ttl`. Costs 1 query credit when not cached.
    """
    cache_key = f"dune:execute:{query_id}:{params or {}}"
    cached = cache.get(cache_key, ttl_seconds=cache_ttl)
    if cached is not None:
        return pd.DataFrame(cached)

    execution_id = _execute(query_id, params)
    _poll(execution_id)
    rows = _fetch_results(execution_id)
    cache.set(cache_key, rows)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Latest-results (0 credits) — recommended default for the dashboard
# ---------------------------------------------------------------------------


def fetch_latest_results(query_id: int, cache_ttl: int = DEFAULT_TTL) -> pd.DataFrame:
    """Fetch the most recent execution's results without re-running.

    Dune scheduled refreshes (configured in the Dune UI) write to this endpoint
    automatically, so a dashboard can hit it freely. This is how we stay well
    under the 2,500 credits/month limit.
    """
    cache_key = f"dune:latest:{query_id}"
    cached = cache.get(cache_key, ttl_seconds=cache_ttl)
    if cached is not None:
        return pd.DataFrame(cached)

    raw = http_get(
        f"{BASE_URL}/query/{query_id}/results",
        headers=_headers(),
        cache_key=None,  # we handle caching one level up, keyed on query_id
    )
    rows = raw.get("result", {}).get("rows", [])
    cache.set(cache_key, rows)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Named flagship queries
# ---------------------------------------------------------------------------
#
# Each of these references a query we've authored on dune.com. The ID lives
# here; the SQL lives in the Dune UI where it can be versioned/forked.
#
# Set these IDs after creating the queries. Until then the helpers raise
# NotImplementedError with a clear message so callers know what's pending.

FLAGSHIP_QUERIES = {
    # 1yr+ dormant share of ERC-20 circulating supply for a given contract.
    # Bound parameter: {{contract_address}}
    "erc20_dormancy": None,

    # SKY Smart Burn Engine: tokens bought and burned in the last N days.
    # Bound parameter: {{lookback_days}}
    "sky_smart_burn": None,

    # --- Queries authored for the Chainlink take-home (5-query batch) ---

    # Q1: SOL base-fee burn (30d actuals, annualized).
    # Columns: sol_burned_30d_approx, sol_burned_365d_approx, sol_burn_rate_annualized_approx,
    #          sol_burned_30d_base_fee, sol_burned_365d_base_fee, sol_burn_rate_annualized_base_fee,
    #          as_of_date
    "sol_base_fee_burn": 7328502,

    # Q2: LINK treasury outflow from the 15 non-circulating treasury shards (365d).
    # The original single multisig (0x98C6...) was sharded in June 2022; this query
    # covers all 15 successor addresses. 3 of 15 were active in the trailing 365d.
    # Columns: link_treasury_outflow_tokens_365d, link_treasury_outflow_annualized_pct, as_of_date
    "link_treasury_outflow": 7328638,

    # Q3: AAVE buyback spend (USD) by the Aavenomics TWAP executor bots.
    # AIP-434 launched 2025-04-17; executors identified via diagnostic query 7328830.
    # Columns: aave_buyback_spend_usd_365d, aave_tokens_bought_365d,
    #          aave_buyback_spend_usd_30d, aave_tokens_bought_30d,
    #          trade_count_365d, as_of_date
    "aave_buyback_spend": 7328824,

    # Q4 (dropped): CRV LP incentive split was scoped out — gross CRV inflation
    # is used as incentive expense directly. Bribe/LP split is footnote-level
    # detail, not needed for the peer comparison.

    # Q5: Dormancy as "active supply" — sum of balances for addresses whose
    # latest balance row is within the 180d window. Dormant share is computed
    # in Python as (total_supply_external - active_supply) / total_supply.
    # Caveats: CEX hot wallets, MEV bots, and protocol contracts inflate the
    # "active" figure. Read as "share of supply that has moved recently",
    # not "share of holders that are active".
    "sol_dormancy": 7328755,            # solana_utils.latest_balances
    "evm_dormancy_ethereum": 7328758,   # tokens_ethereum.balances (LINK/AAVE/UNI/LDO/CRV)
    "evm_dormancy_optimism": 7328772,   # tokens_optimism.balances (OP)
    # Native ETH dormancy: no curated balance table exists on Dune, so this
    # query reconstructs the native-ETH balance of every address that sent a
    # successful value-tx in the 180d window (genesis + withdrawals + tx/trace
    # inflows - outflows - gas). Active supply is the sum of positive balances.
    "eth_dormancy": 7332769,

    # Q6: UNI Firepit burn — UNI tokens sent to the burn address on Ethereum
    # + Unichain. Activated by UNIfication (Jan 2026). Returns daily rows with
    # cumulative totals and a projected annualized burn rate.
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
    """UNI tokens burned via the Firepit mechanism (ETH + Unichain).

    UNIfication (effective Jan 1 2026) routes a share of protocol fees to
    a burn address. Query 6430914 returns one row per day with cumulative
    totals and a projected annualized figure (cumulative ÷ days × 365).

    Use the most-recent row's `projected_burn` / `projected_burn_usd` as
    the annualized estimate — these self-update as the burn accumulates.
    """
    qid = FLAGSHIP_QUERIES["uni_firepit_burn"]
    if qid is None:
        raise NotImplementedError("Set FLAGSHIP_QUERIES['uni_firepit_burn']")
    df = fetch_latest_results(qid)
    # Sort descending by time so iloc[0] is always the latest day
    if "time" in df.columns:
        df = df.sort_values("time", ascending=False).reset_index(drop=True)
    return df


def eth_dormancy() -> pd.DataFrame:
    """Active native-ETH balance via balance reconstruction (180d).

    Query 7332769 is public but not owned by us — fetch_latest_results (GET,
    0 credits) works; execute (POST) returns 403.
    """
    qid = FLAGSHIP_QUERIES["eth_dormancy"]
    if qid is None:
        raise NotImplementedError("Set FLAGSHIP_QUERIES['eth_dormancy']")
    return fetch_latest_results(qid)


def dormancy_summary() -> pd.DataFrame:
    """Unified active-balance figures across SOL, native ETH, ERC-20s, and OP.

    Returns one row per token with columns:
        symbol, active_supply_180d, active_address_count,
        holding_supply_total (NaN for SOL and ETH — no analogous column in
        the source queries; reconcile against CoinGecko circ_supply in
        compute.dormancy() instead), as_of_date
    """
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


# ---------------------------------------------------------------------------
# Auth sanity check
# ---------------------------------------------------------------------------


def check_auth() -> dict:
    """Hit a cheap endpoint to confirm the key is live. Returns the raw response."""
    resp = requests.get(
        f"{BASE_URL}/user/context",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
