"""Metric computation — turn raw source data into the uniform peer table.

Each public function takes a `Peer` and returns a flat dict of metric values
(or None where the metric is not applicable). The metrics notebook stitches
these together row-by-row into `peer_table.csv`.

# Architecture: default + per-project overrides

Per the PLAN.md note on supply dynamics: "the logic for determining supply
dynamics is expected to become increasingly custom per project." We honour
that with a two-stage pipeline:

  1. The **default handler** (`_default_supply_dynamics`) runs first. It
     pulls CoinDesk historical supply, derives gross/burn/net inflation, and
     records locked/staked share. CoinGecko implied supply is the fallback
     for inflation when CoinDesk lacks `issued`.
  2. A **per-project handler** registered in `CUSTOM_SUPPLY_HANDLERS` may
     then override individual fields, augment with new ones, or **flag** the
     metric as needing custom research that hasn't been done yet by adding
     to the `needs_custom` list.

Project-specific handlers should:
  * Override only the fields they have a better source for.
  * Append to `out["needs_custom"]` when they detect a known gap that requires
    follow-up work (e.g. a Dune query) — do NOT silently fix or fudge.
  * Leave any field they don't understand alone (return without touching it).

This means: the default path always produces *some* number, the override path
sharpens it where possible, and any field flagged in `needs_custom` is a
visible TODO in the output table. We never block on a missing data source.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Callable, Optional

import pandas as pd

from src.config import Peer
from src.sources import coindesk, coingecko


# ---------------------------------------------------------------------------
# Default supply dynamics — CoinDesk primary, CoinGecko fallback
# ---------------------------------------------------------------------------


def _default_supply_dynamics(peer: Peer, window_days: int = 365) -> dict:
    """The generic CoinDesk → CoinGecko-implied supply path.

    Returns the dict that all peers start from. Per-project handlers run on
    top of this and may override any field.
    """
    out: dict = {
        "coindesk_covered": False,
        "gross_inflation_annualized": None,
        "burn_rate_annualized": None,
        "net_inflation_annualized": None,
        "locked_supply_pct": None,
        "staked_supply_pct": None,
        "locked_plus_staked_pct": None,
        "inflation_source": None,
        "needs_custom": [],  # list of metric names with known gaps
        "custom_handler_applied": None,  # name of handler if any ran
    }

    try:
        df = coindesk.get_supply_timeseries(peer.symbol, days=window_days)
    except Exception:
        df = pd.DataFrame()

    if not df.empty and "circulating" in df.columns and len(df) >= 2:
        out["coindesk_covered"] = True
        start = df.iloc[0]
        end = df.iloc[-1]
        actual_days = max((end["date"] - start["date"]).days, 1)
        scale = 365 / actual_days
        start_circ = start["circulating"]

        if "issued" in df.columns and pd.notna(start.get("issued")) and pd.notna(end.get("issued")) and start_circ:
            gross = (end["issued"] - start["issued"]) / start_circ * scale
            out["gross_inflation_annualized"] = float(gross)
            out["inflation_source"] = "coindesk"

        if "burned" in df.columns and pd.notna(start.get("burned")) and pd.notna(end.get("burned")) and start_circ:
            burn = (end["burned"] - start["burned"]) / start_circ * scale
            out["burn_rate_annualized"] = float(burn)

        if out["gross_inflation_annualized"] is not None and out["burn_rate_annualized"] is not None:
            out["net_inflation_annualized"] = out["gross_inflation_annualized"] - out["burn_rate_annualized"]
        elif out["gross_inflation_annualized"] is not None:
            out["net_inflation_annualized"] = out["gross_inflation_annualized"]

        end_circ = end["circulating"]
        if "locked" in df.columns and pd.notna(end.get("locked")) and end_circ:
            out["locked_supply_pct"] = float(end["locked"] / end_circ)
        if "staked" in df.columns and pd.notna(end.get("staked")) and end_circ:
            out["staked_supply_pct"] = float(end["staked"] / end_circ)
        if out["locked_supply_pct"] is not None or out["staked_supply_pct"] is not None:
            out["locked_plus_staked_pct"] = (out["locked_supply_pct"] or 0) + (out["staked_supply_pct"] or 0)

    # Fallback for inflation: derive from CoinGecko market_chart implied supply.
    if out["gross_inflation_annualized"] is None:
        try:
            implied = coingecko.compute_inflation(peer.coingecko_id, window_days=window_days)
        except Exception:
            implied = None
        if implied and implied.get("pct_change_annualized") is not None:
            out["net_inflation_annualized"] = float(implied["pct_change_annualized"])
            out["inflation_source"] = "coingecko_implied"

    return out


# ---------------------------------------------------------------------------
# Per-project custom handlers
# ---------------------------------------------------------------------------
#
# Each handler signature: (peer, default_result, window_days) -> partial dict
# of overrides. Returned keys are merged into the default result; keys not
# returned are left alone. Append metric names to `needs_custom` to flag
# known gaps that need follow-up (e.g. an unauthored Dune query).
#
# Convention: handlers should be cheap (no slow API calls beyond what the
# default path already did) unless they're the *only* source for a field.
# Heavy work belongs in src/sources/dune.py and is loaded lazily.


def _sol_supply_dynamics(peer: Peer, default: dict, window_days: int) -> dict:
    """Solana — replace CoinDesk burn (always 0) with Dune base-fee burn.

    CoinDesk reports burned == 0 for SOL because the protocol-level lamport
    destruction isn't tracked as a supply event. Dune query 7328502 computes
    the true base-fee-only burn (required_signatures × 5000 lamports × 50%)
    against solana.transactions. The approx column (50% of total fee) is ~9x
    higher due to priority fee dominance and should not be used.
    """
    # Lazy import avoids a hard dependency on the Dune API key at module load.
    from src.sources import dune as _dune

    try:
        df = _dune.sol_base_fee_burn()
        burn_rate = float(df.iloc[0]["sol_burn_rate_annualized_base_fee"])
    except Exception:
        # Dune unavailable or query not yet executed — flag for follow-up.
        return {
            "needs_custom": ["burn_rate_annualized", "net_inflation_annualized"],
            "custom_handler_applied": "sol_supply_dynamics",
        }

    gross = default.get("gross_inflation_annualized")
    net = (gross - burn_rate) if gross is not None else None

    return {
        "burn_rate_annualized": burn_rate,
        "net_inflation_annualized": net,
        "custom_handler_applied": "sol_supply_dynamics",
    }


def _op_supply_dynamics(peer: Peer, default: dict, window_days: int) -> dict:
    """Optimism — pre-minted supply with chain-of-custody release.

    OP token total supply is fixed at genesis; "issuance" in the CoinDesk
    sense (newly minted tokens) is zero. The real forward sell-pressure
    figure is the unlock schedule from `unlocks.yaml` (Core Contributors,
    Investors, RetroPGF, Token House grants). CoinDesk's `issued` series
    correctly shows ~0 inflation, but that *understates* effective dilution
    from the holder perspective.

    Action: leave inflation == 0 as reported, but flag that the forward
    dilution figure must be sourced from unlocks.yaml downstream.
    """
    return {
        "needs_custom": ["effective_dilution_from_unlocks"],
        "custom_handler_applied": "op_supply_dynamics",
        # Make the data-asymmetry explicit in the output:
        "inflation_source": (default.get("inflation_source") or "coindesk_pre_minted"),
    }


def _link_supply_dynamics(peer: Peer, default: dict, window_days: int) -> dict:
    """Chainlink — CoinDesk inflation (~0) correct; Reserve buyback tracked separately.

    LINK max supply is fixed at 1B; CoinDesk `issued` is flat, gross_inflation ≈ 0.
    The Chainlink Reserve (launched Aug 2025) converts non-LINK service fees to
    LINK on-market via Payment Abstraction dutch auctions. Historical weekly inflows:
      84K LINK/wk (Dec 2025) → 125K (Feb 5 2026) → 137K (Feb 19 2026)
    Mid-point of recent 120K–140K/wk range = 130K/wk used as forward estimate.
    Source: https://cryptonews.net/news/altcoins/32460837/ (as of 2026-02-19)
    PA v2 (audit started Mar 2026) will route ALL enterprise fees → more upside.

    Treasury outflow is a separate, separate question from buyback — tracked in
    unlocks.yaml (Dune Q2, ID 7328638, ~41.5M LINK/yr from non-circulating multisigs).
    """
    # 130K LINK/wk × 52 wks = 6.76M LINK/yr annualized buyback (conservative mid-point)
    LINK_RESERVE_WEEKLY = 130_000
    return {
        "link_reserve_weekly_link": LINK_RESERVE_WEEKLY,
        "link_reserve_annualized_link": LINK_RESERVE_WEEKLY * 52,
        "custom_handler_applied": "link_supply_dynamics",
    }


def _crv_supply_dynamics(peer: Peer, default: dict, window_days: int) -> dict:
    """Curve — override CoinDesk gross_inflation with the post-reduction rate.

    CoinDesk's trailing `issued` series reflects the old ~9.25% schedule.
    CRV emissions follow a time-decay schedule hardcoded in the token contract;
    the most recent reduction brought the annualized rate to ~5.02% as of
    early 2026. Source: https://metamask.io/price/curve-dao-token
    Next reduction is Aug 2026.
    """
    GROSS = 0.0502
    return {
        "gross_inflation_annualized": GROSS,
        "net_inflation_annualized": GROSS - (default.get("burn_rate_annualized") or 0.0),
        "inflation_source": "manual_post_reduction",
        "custom_handler_applied": "crv_supply_dynamics",
    }


def _ldo_supply_dynamics(peer: Peer, default: dict, window_days: int) -> dict:
    """Lido — incentives ended Q2 2023; $20M buyback just started (Mar 2026).

    Default CoinDesk `issued` shows ~0 inflation, which is correct: there are
    no programmatic emissions. Treasury moves require Aragon votes.

    Buyback note: Lido DAO approved a $20M LDO buyback program on ~2026-03-30.
    Too early to annualize (launched <30 days before as-of date); not modeled
    in burn_rate_annualized. Set `ldo_buyback_started = True` so the dashboard
    can render a "buyback recently started" footnote rather than leaving the
    Burns+Buybacks cell blank.
    Source: https://tokenomist.ai/lido-dao
    """
    return {
        "ldo_buyback_started": True,
        "custom_handler_applied": "ldo_supply_dynamics",
    }


def _aave_supply_dynamics(peer: Peer, default: dict, window_days: int) -> dict:
    """Aave — CoinDesk inflation values are correct (~0); buyback from Dune Q3.

    Default produces gross_inflation from `issued` (~0, AAVE is fully
    circulating) and burn_rate from `burned` (~0, AAVE doesn't burn). The
    real value-accrual mechanism is the Aavenomics buyback-and-distribute
    (AIP-434, launched 2025-04-17): protocol TWAP executors continuously buy
    AAVE on Ethereum DEXes and distribute to Safety Module stakers.

    Dune Q3 (query 7328824) surfaces $453M buyback spend over 365d — ~13%
    of circulating supply acquired. The 30d figure ($3.6M) is much lower than
    the 365d monthly average ($37.7M/month), indicating buybacks were front-
    loaded in the early AIP period.
    """
    from src.sources import dune as _dune

    try:
        df = _dune.aave_buyback_spend()
        row = df.iloc[0]
        return {
            "aave_buyback_spend_usd_365d": float(row["aave_buyback_spend_usd_365d"]),
            "aave_buyback_spend_usd_30d": float(row["aave_buyback_spend_usd_30d"]),
            "aave_tokens_bought_365d": float(row["aave_tokens_bought_365d"]),
            "custom_handler_applied": "aave_supply_dynamics",
        }
    except Exception:
        return {
            "needs_custom": ["aave_buyback_spend_usd"],
            "custom_handler_applied": "aave_supply_dynamics",
        }


def _uni_supply_dynamics(peer: Peer, default: dict, window_days: int) -> dict:
    """Uniswap — Firepit burn from Dune Q6 (6430914), sourced on-chain.

    UNIfication (Dec 2025) routes protocol fees to a burn address on ETH +
    Unichain. Dune query 6430914 tracks daily UNI sent to that address and
    exposes `projected_burn` (cumulative ÷ days × 365) as the live annualized
    estimate. 110 days of data as of 2026-04-17: 3.164M UNI burned, projecting
    ~10.5M UNI/yr (~$34.7M at $3.30).

    This replaces the earlier static 4M/yr estimate from the UNIfication blog
    which proved 2.6× too low once live data was available.
    """
    from src.sources import dune as _dune

    try:
        df = _dune.uni_firepit_burn()
        row = df.iloc[0]  # most recent day (sorted descending)
        projected_tokens = float(row["projected_burn"])
        projected_usd = float(row["projected_burn_usd"])
        days_of_data = int(row["days"])
        # Use CoinGecko circ_supply for consistency with all other metrics.
        # Prior version fetched CoinDesk circulating (~728M) which diverges
        # from CoinGecko (634M after Dec 2025 100M treasury burn) and caused
        # a ~15% denominator error.
        cg_snap = coingecko.get_snapshot(peer.coingecko_id)
        circ = float(cg_snap["circ_supply"]) if cg_snap.get("circ_supply") else None
        return {
            "burn_rate_annualized": burn_pct,
            "net_inflation_annualized": (0.0 - burn_pct) if burn_pct is not None else None,
            "uni_firepit_burn_annual_tokens": projected_tokens,
            "uni_firepit_burn_usd": projected_usd,
            "uni_firepit_days_of_data": days_of_data,
            "custom_handler_applied": "uni_supply_dynamics",
        }
    except Exception:
        return {
            "needs_custom": ["uni_firepit_burn"],
            "custom_handler_applied": "uni_supply_dynamics",
        }


def _eth_supply_dynamics(peer: Peer, default: dict, window_days: int) -> dict:
    """Ethereum — override CoinDesk issuance with beacon-chain formula.

    CoinDesk's `issued` field for ETH reconstructs issuance from changes in
    circulating supply, which systematically undercounts validator block
    rewards because those rewards accrue to the *staked* balance, not the
    circulating balance. Empirically it reports ~35K ETH/yr issuance vs
    actual ~1M ETH/yr — off by ~30x.

    The beacon chain issuance formula is well-known and derives from the
    base_reward_factor:
        annual_issuance_ETH ≈ 166.3 × sqrt(total_staked_ETH)

    This matches ethereum.org's cited ~1,700 ETH/day at ~14M staked exactly
    (166.3 × sqrt(14e6) = 622K/yr = 1,705/day). At current ~37.7M staked,
    formula gives ~1.02M ETH/yr = ~2,800 ETH/day, consistent with
    beaconcha.in / ultrasound.money.

    We override burn with a 30-day CoinDesk window rather than the 365-day
    default. The EIP-1559 burn rate has dropped dramatically since the Dencun
    upgrade (Mar 2024) reduced L1 calldata costs, so the 365-day trailing
    average (~45K ETH/yr, 123/day) grossly overstates the current run-rate.
    30-day window gives ~11.4K ETH/yr (31/day), consistent with ~$26M/yr per
    ultrasound.money in Apr 2026. Using a shorter window is the correct choice
    here because the structural break (Dencun) was permanent, not cyclical.
    """
    import math

    try:
        df_full = coindesk.get_supply_timeseries(peer.symbol, days=window_days)
    except Exception:
        df_full = pd.DataFrame()

    if df_full.empty or "staked" not in df_full.columns or "circulating" not in df_full.columns:
        return {
            "needs_custom": ["gross_inflation_annualized"],
            "custom_handler_applied": "eth_supply_dynamics",
        }

    end = df_full.dropna(subset=["staked", "circulating"]).iloc[-1]
    staked_eth = float(end["staked"])
    circ_eth = float(end["circulating"])

    annual_issuance_eth = 166.3 * math.sqrt(staked_eth)
    gross = annual_issuance_eth / circ_eth

    # 30-day burn window — use a fresh 31-row slice to avoid the Dencun artefact
    burn_rate_30d = None
    try:
        df_30 = coindesk.get_supply_timeseries(peer.symbol, days=31)
        if "burned" in df_30.columns and len(df_30) >= 2:
            df_30 = df_30.dropna(subset=["burned", "circulating"]).sort_values("date")
            s30, e30 = df_30.iloc[0], df_30.iloc[-1]
            actual_days = max((e30["date"] - s30["date"]).days, 1)
            burn_delta = float(e30["burned"]) - float(s30["burned"])
            burn_rate_30d = (burn_delta / float(e30["circulating"])) * (365 / actual_days)
    except Exception:
        pass

    burn = burn_rate_30d if burn_rate_30d is not None else (default.get("burn_rate_annualized") or 0.0)
    net = gross - burn

    return {
        "gross_inflation_annualized": gross,
        "burn_rate_annualized": burn,
        "net_inflation_annualized": net,
        "inflation_source": "beacon_chain_formula",
        "custom_handler_applied": "eth_supply_dynamics",
    }


CustomSupplyHandler = Callable[[Peer, dict, int], dict]

CUSTOM_SUPPLY_HANDLERS: dict[str, CustomSupplyHandler] = {
    "ETH": _eth_supply_dynamics,
    "SOL": _sol_supply_dynamics,
    "LINK": _link_supply_dynamics,
    "AAVE": _aave_supply_dynamics,
    "UNI": _uni_supply_dynamics,
    "CRV": _crv_supply_dynamics,
    "LDO": _ldo_supply_dynamics,
    "OP": _op_supply_dynamics,
}


def supply_dynamics(peer: Peer, window_days: int = 365) -> dict:
    """Compute supply dynamics for a peer using the registry pattern.

    Runs the default CoinDesk-first handler, then layers a per-project
    override on top if one is registered. Returned dict always includes:

      coindesk_covered, gross_inflation_annualized, burn_rate_annualized,
      net_inflation_annualized, locked_supply_pct, staked_supply_pct,
      locked_plus_staked_pct, inflation_source,
      custom_handler_applied (str|None), needs_custom (list[str]).
    """
    out = _default_supply_dynamics(peer, window_days=window_days)
    handler = CUSTOM_SUPPLY_HANDLERS.get(peer.symbol)
    if handler is not None:
        try:
            overrides = handler(peer, out, window_days)
        except Exception as e:
            # A custom handler should never block the pipeline. Surface the
            # error in needs_custom and continue with default values.
            out["needs_custom"].append(f"handler_error:{e!r}")
            return out
        # Merge: lists are concatenated, scalars are overwritten.
        for k, v in overrides.items():
            if k == "needs_custom" and isinstance(v, list):
                out["needs_custom"] = list({*out["needs_custom"], *v})
            else:
                out[k] = v
    return out


# ---------------------------------------------------------------------------
# Supply velocity — universal proxy for turnover / liquidity pressure
# ---------------------------------------------------------------------------


def supply_velocity(volume_24h: Optional[float], circ_supply: Optional[float],
                     price_usd: Optional[float]) -> Optional[float]:
    """Annualized trading volume / circulating market cap.

    A velocity of 2.0 means the full circulating supply turns over twice/year.
    """
    if not volume_24h or not circ_supply or not price_usd:
        return None
    vol_tokens_annual = (volume_24h / price_usd) * 365
    return float(vol_tokens_annual / circ_supply)


# ---------------------------------------------------------------------------
# Dormancy — share of circulating supply that hasn't moved in 180d
# ---------------------------------------------------------------------------
#
# Dormancy is computed as (total_supply - active_supply) / total_supply, where
# `active_supply` is the sum of balances for addresses whose latest balance
# row is within the 180d window (Dune queries 7328755/7328758/7328772). Total
# supply comes from CoinGecko (the canonical source for the rest of the
# pipeline) — we deliberately don't use the Dune `holding_supply_total`
# column, since it includes contracts (treasury, staking pools) and may
# differ from the analyst-facing circulating figure.
#
# Caveats (must be surfaced in the methodology doc):
#   * ERC-20 and OP queries use the outbound-transfer signal (addresses that
#     have *sent* tokens in 180d) to avoid dust-attack inflation of the active
#     set. SOL uses balance-row updates — the dust-attack threat is blunted
#     by rent-exempt costs (~$440K+ to spam every account).
#   * ETH uses native-balance reconstruction (Dune Q7332769): an address is
#     active if it sent a successful value-tx in 180d, and its balance is
#     reconstructed from genesis + withdrawals + tx/trace flows - gas. Some
#     edge cases (suicide traces, pre-Byzantium ommers) produce negative
#     reconstructed balances; those are floored to zero rather than propagated.
#   * CEX hot wallets, MEV bots, and active protocol contracts still inflate
#     "active" across all chains — this is a *behavioural* rather than
#     *holder-count* signal.


@lru_cache(maxsize=1)
def _cached_dormancy_summary() -> pd.DataFrame:
    """One-shot fetch of the unified dormancy table for the run."""
    from src.sources import dune as _dune
    return _dune.dormancy_summary()


def dormancy(peer: Peer, snapshot_row: pd.Series, dynamics: dict,
             window_days: int = 180) -> dict:
    """Compute dormant share of supply for a peer.

    Returns:
      active_supply_180d        — tokens active in the last 180d
      dormant_supply_pct_180d   — 1 - active / total_supply
      dormancy_source           — 'dune_active_balance'
      needs_custom              — list of gaps if the figure couldn't be derived
    """
    out = {
        "active_supply_180d": None,
        "dormant_supply_pct_180d": None,
        "dormancy_source": None,
        "dormancy_needs_custom": [],
    }

    try:
        df = _cached_dormancy_summary()
    except Exception:
        out["dormancy_needs_custom"] = ["dormant_supply_pct_180d"]
        return out

    row = df[df["symbol"] == peer.symbol]
    if row.empty:
        out["dormancy_needs_custom"] = ["dormant_supply_pct_180d"]
        return out

    active = row.iloc[0]["active_supply_180d"]
    # Use total_supply as denominator — Dune counts all token activity including
    # locked/vested supply, so circ_supply understates the pool being measured.
    # For uncapped tokens (ETH, SOL) total_supply == circ_supply, no change.
    total = snapshot_row.get("total_supply") or snapshot_row.get("circ_supply")
    if active is None or not total:
        out["dormancy_needs_custom"] = ["dormant_supply_pct_180d"]
        return out

    out["active_supply_180d"] = float(active)
    out["dormant_supply_pct_180d"] = float(max(0.0, 1.0 - (active / total)))
    out["dormancy_source"] = "dune_active_balance"
    return out


# ---------------------------------------------------------------------------
# Economic earnings — treats emissions as stock-based comp
# ---------------------------------------------------------------------------


def economic_earnings(peer: Peer, snapshot_row: pd.Series,
                       dynamics: dict) -> dict:
    """Compute incentive expense, economic earnings, and economic P/E.

    Token incentive expense (USD) = gross_inflation * circ_supply * price
    Economic earnings (USD)       = annualized protocol revenue - incentive expense
    Economic P/E                  = market cap / economic earnings (if positive)
    Incentive/Revenue ratio       = incentive expense / annualized fees

    Inherits any flags in `dynamics["needs_custom"]` so downstream consumers
    can see when the incentive number is built on a flagged input.
    """
    out = {
        "token_incentive_expense_usd": None,
        "incentive_over_revenue": None,
        "incentive_over_fees": None,
        "economic_earnings_usd": None,
        "economic_pe": None,
        "ee_inherits_flags": list(dynamics.get("needs_custom", [])) or None,
    }

    gross = dynamics.get("gross_inflation_annualized")
    circ = snapshot_row.get("circ_supply")
    price = snapshot_row.get("price_usd")
    rev = snapshot_row.get("annualized_revenue")
    fees = snapshot_row.get("annualized_fees")
    mc = snapshot_row.get("market_cap")

    if gross is not None and gross > 0 and circ and price:
        incentive = gross * circ * price
        out["token_incentive_expense_usd"] = float(incentive)

        if rev and rev > 0:
            out["incentive_over_revenue"] = float(incentive / rev)
            ee = rev - incentive
            out["economic_earnings_usd"] = float(ee)
            if ee > 0 and mc:
                out["economic_pe"] = float(mc / ee)
        if fees and fees > 0:
            out["incentive_over_fees"] = float(incentive / fees)

    return out


# ---------------------------------------------------------------------------
# Forward supply curve — 90-day cumulative at-risk new supply
# ---------------------------------------------------------------------------
#
# Combines two additive components:
#   1. **Inflation slope** — a straight ramp at gross_inflation_annualized / 365
#      per day, representing continuous new issuance (validator block rewards,
#      gauge emissions, etc.). Only counts newly minted tokens — EIP-1559 burn,
#      priority fees, and MEV are redistribution of existing supply, not new
#      issuance, and do not enter this metric.
#   2. **Unlock steps** — discrete cliff events from unlocks.yaml. Each event
#      produces a step jump on its date.
#
# Both are normalized to % of current circulating supply so peers are
# comparable on one y-axis. A project with `counted_in_inflation: true` in its
# unlocks entry has its scheduled emissions already reflected in the inflation
# slope — we do not layer events on top (that would double-count).


BUYBACK_CADENCE_DAYS: dict[str, int] = {
    "ETH": 1,   # continuous EIP-1559 burn
    "SOL": 1,   # continuous base-fee burn
    "LINK": 7,  # weekly Reserve dutch-auction accumulation
    "AAVE": 30, # monthly TWAP executor buyback
    "UNI": 1,   # daily Firepit burns
}


def compute_forward_supply_curve(
    peer: Peer,
    snapshot_row: pd.Series,
    dynamics: dict,
    unlock_entry: Optional[dict],
    days: int = 90,
    as_of: Optional[date] = None,
    buyback_annual_pct: float = 0.0,
    cadence_days: int = 1,
) -> pd.DataFrame:
    """Build a daily forward supply-pressure series for a single peer.

    Returns a DataFrame with one row per day (day 0 = as_of), columns:
        symbol, date, days_out,
        inflation_cumulative_pct      — decimal share of circ added by inflation
        unlock_cumulative_pct         — decimal share of circ added by unlocks
        total_cumulative_pct          — sum of the two (gross dilution)
        buyback_cumulative_pct        — decimal share of circ removed by buybacks/burns
        net_cumulative_pct            — total_cumulative_pct − buyback_cumulative_pct
        inflation_cumulative_tokens   — absolute tokens from inflation
        unlock_cumulative_tokens      — absolute tokens from unlock events
        total_cumulative_tokens       — sum

    `unlock_entry` is the matching entry from unlocks.yaml (a dict). Pass None
    to skip the unlock component entirely.

    `buyback_annual_pct` is the annualized buyback/burn as a fraction of circ
    supply (e.g. 0.01 = 1%). `cadence_days` is how often buybacks occur as a
    step function (1 = daily, 7 = weekly, 30 = monthly).
    """
    if as_of is None:
        as_of = date.today()

    circ = snapshot_row.get("circ_supply")
    if not circ or circ <= 0:
        # Can't normalize — return an empty frame with the right shape.
        return pd.DataFrame(columns=[
            "symbol", "date", "days_out",
            "inflation_cumulative_pct", "unlock_cumulative_pct", "total_cumulative_pct",
            "buyback_cumulative_pct", "net_cumulative_pct",
            "inflation_cumulative_tokens", "unlock_cumulative_tokens", "total_cumulative_tokens",
        ])

    # Inflation component: annualized gross rate turned into a daily ramp.
    # Floor at 0 — we don't treat net-deflationary issuance as "at-risk new
    # supply" (the burn component isn't new supply entering circulation).
    gross = dynamics.get("gross_inflation_annualized") or 0.0
    gross = max(float(gross), 0.0)
    daily_infl_pct = gross / 365.0

    # Unlock component: step function from the events list.
    events: list[dict] = []
    if unlock_entry and not unlock_entry.get("counted_in_inflation", False):
        for ev in (unlock_entry.get("events") or []):
            ev_date = ev.get("date")
            if isinstance(ev_date, str):
                ev_date = datetime.strptime(ev_date, "%Y-%m-%d").date()
            ev_tokens = float(ev.get("tokens") or 0)
            if ev_date and ev_tokens > 0:
                events.append({"date": ev_date, "tokens": ev_tokens})

    # Buyback component: step function at `cadence_days` intervals.
    # Per-event amount = annual rate apportioned to one cadence period.
    buyback_annual_pct = max(float(buyback_annual_pct or 0.0), 0.0)
    buyback_per_event_pct = buyback_annual_pct * cadence_days / 365.0

    rows = []
    unlock_cum_tokens = 0.0
    buyback_cum_pct = 0.0
    for d in range(days + 1):  # include day 0 and day `days`
        current = as_of + timedelta(days=d)

        # Bank any unlock events that occurred on/before today.
        for ev in events:
            if ev["date"] == current:
                unlock_cum_tokens += ev["tokens"]

        # Buyback steps fire on day cadence_days, 2*cadence_days, etc.
        # Day 0 is the baseline; first event lands at d == cadence_days.
        if d > 0 and cadence_days > 0 and d % cadence_days == 0:
            buyback_cum_pct += buyback_per_event_pct

        infl_pct = daily_infl_pct * d
        unlock_pct = unlock_cum_tokens / circ
        infl_tokens = infl_pct * circ

        rows.append({
            "symbol": peer.symbol,
            "date": current,
            "days_out": d,
            "inflation_cumulative_pct": infl_pct,
            "unlock_cumulative_pct": unlock_pct,
            "total_cumulative_pct": infl_pct + unlock_pct,
            "buyback_cumulative_pct": buyback_cum_pct,
            "net_cumulative_pct": (infl_pct + unlock_pct) - buyback_cum_pct,
            "inflation_cumulative_tokens": infl_tokens,
            "unlock_cumulative_tokens": unlock_cum_tokens,
            "total_cumulative_tokens": infl_tokens + unlock_cum_tokens,
        })

    return pd.DataFrame(rows)


def build_forward_supply_panel(
    peers: list[Peer],
    peer_table: pd.DataFrame,
    dynamics_by_symbol: dict[str, dict],
    unlocks_yaml: dict,
    days: int = 90,
    as_of: Optional[date] = None,
) -> pd.DataFrame:
    """Stitch per-peer forward curves into a single long-format DataFrame.

    `peer_table` provides circ_supply per symbol; `dynamics_by_symbol` provides
    gross_inflation; `unlocks_yaml` is the loaded yaml dict (with an "unlocks"
    key whose value is a list of entries). Returns ~len(peers) × (days+1) rows.

    Buyback/burn offsets are read from `buyback_burn_usd_annualized` and
    `market_cap` in peer_table; cadences come from BUYBACK_CADENCE_DAYS.
    """
    if as_of is None:
        as_of = date.today()

    unlocks_by_symbol = {u["symbol"]: u for u in unlocks_yaml.get("unlocks", [])}

    frames = []
    for peer in peers:
        row = peer_table[peer_table["symbol"] == peer.symbol]
        if row.empty:
            continue
        snapshot_row = row.iloc[0]
        dynamics = dynamics_by_symbol.get(peer.symbol, {})
        unlock_entry = unlocks_by_symbol.get(peer.symbol)

        # Derive buyback_annual_pct from USD figures in peer_table.
        buyback_annual_pct = 0.0
        bb_usd = snapshot_row.get("buyback_burn_usd_annualized")
        mc = snapshot_row.get("market_cap")
        if bb_usd and mc and float(mc) > 0:
            buyback_annual_pct = float(bb_usd) / float(mc)
        cadence_days = BUYBACK_CADENCE_DAYS.get(peer.symbol, 1)

        curve = compute_forward_supply_curve(
            peer, snapshot_row, dynamics, unlock_entry,
            days=days, as_of=as_of,
            buyback_annual_pct=buyback_annual_pct,
            cadence_days=cadence_days,
        )
        if not curve.empty:
            frames.append(curve)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Incentive Capture Yield
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_incentive_yields() -> dict[str, dict]:
    """Load incentive_yield.yaml; returns a dict keyed by symbol.

    Cached so repeated calls within a notebook session don't re-read disk.
    """
    import yaml
    from src.config import ROOT

    path = ROOT / "incentive_yield.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)

    return {entry["symbol"]: entry for entry in (data.get("yields") or [])}


def incentive_capture_yield(symbol: str) -> dict:
    """Return incentive yield fields for one peer.

    Returns:
        incentive_yield_annualized   — decimal (e.g. 0.0475), or None
        incentive_yield_mechanism    — human-readable label, or None
        incentive_yield_notes        — context string, or None
    """
    yields = load_incentive_yields()
    entry = yields.get(symbol)
    if entry is None:
        return {
            "incentive_yield_annualized": None,
            "incentive_yield_mechanism": None,
            "incentive_yield_notes": None,
        }
    return {
        "incentive_yield_annualized": float(entry["yield_annualized"]),
        "incentive_yield_mechanism": entry.get("mechanism"),
        "incentive_yield_notes": entry.get("notes"),
    }
