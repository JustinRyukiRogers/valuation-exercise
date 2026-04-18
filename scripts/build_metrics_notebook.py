"""Generate notebooks/02_metrics.ipynb from Python source.

Follows the same pattern as `build_ingest_notebook.py`: code is authored in
plain .py for linting/typing/diff sanity, and the .ipynb is a regenerated
artifact.
"""
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks" / "02_metrics.ipynb"

nb = nbf.v4.new_notebook()
cells = []

cells.append(nbf.v4.new_markdown_cell("""# 02 — Metrics

Compute the **uniform metric table** over the full peer set, combining:
- Snapshot valuation / fees / TVL data from `01_ingest.ipynb`
- CoinDesk historical supply breakdown (issued, burned, staked, locked)
- CoinGecko implied supply (fallback for tokens CoinDesk doesn't fully cover)
- **Per-project custom handlers** (`src.metrics.compute.CUSTOM_SUPPLY_HANDLERS`)
  that override or flag default values where a project has known
  CoinDesk-untracked behavior (e.g. SOL base-fee burn, OP pre-minted supply).

Output: `data/metrics/peer_table.csv` — the single source of truth for the
charts notebook and the Vercel dashboard.

### CoinDesk coverage audit (8-token peer set)

Per `scripts/probe_coindesk.py` (run 2026-04-15):

| Tier | Tokens | Fields available |
|---|---|---|
| Full breakdown | ETH, AAVE, OP | circulating, issued, burned, **staked**, locked |
| Near-full      | LINK, SOL, UNI, LDO, CRV | circulating, issued, burned, locked |

→ **Net inflation** is universal via CoinDesk for all 8 tokens.
→ **Staked supply %** is available for ETH, AAVE, and OP (3 of 8).
→ **Locked supply %** is universal — primary dormancy proxy across the peer set.

### Why the per-project layer exists

Per PLAN.md §3: *"the logic for determining supply dynamics is expected to
become increasingly custom per project. Do not brute force a single endpoint."*

The default CoinDesk path is correct for some projects and **wrong** for
others — without exception. Examples:

- **SOL**: CoinDesk doesn't track Solana's 50% base-fee burn (it happens at
  the protocol level, not as ERC-20 events). Default `burn_rate == 0` is
  wrong; we **flag** it pending a Dune query against `solana.transactions`.
- **OP**: Pre-minted supply means `issued` is constant. Default `gross == 0`
  is technically correct, but **understates** dilution because real sell
  pressure comes from the unlock schedule (handled separately in
  `unlocks.yaml`, flagged here).
- **LINK**: Treasury outflow is discretionary, not programmatic — `issued`
  stays at 1B. Flag for follow-up Dune analysis of the non-circulating
  multisig.
- **AAVE**: Buyback-and-distribute is the value-accrual mechanism — flag
  pending Aave-specific Dune query.
- **CRV**: Gross inflation is right but the incentive-expense interpretation
  needs a veCRV split.

Flagged metrics surface in two new columns: `custom_handler_applied` (which
handler ran) and `needs_custom` (semicolon-separated list of fields a human
needs to follow up on). The dashboard can render a "⚠️ flagged" badge from
these without us needing to fabricate numbers.
"""))

cells.append(nbf.v4.new_code_cell("""# --- setup ---
import sys
from pathlib import Path

ROOT = Path().resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from src.config import load_peers, RAW_DIR, METRICS_DIR, ROOT
from src.metrics.compute import (
    supply_dynamics, supply_velocity, economic_earnings,
    build_forward_supply_panel,
    CUSTOM_SUPPLY_HANDLERS,
    incentive_capture_yield,
)

peers = load_peers()
snapshot = pd.read_csv(RAW_DIR / "peer_snapshot.csv")
print(f"Loaded snapshot: {len(snapshot)} rows, {len(snapshot.columns)} cols")
print(f"Peers to process: {[p.symbol for p in peers]}")
print(f"Custom handlers registered: {sorted(CUSTOM_SUPPLY_HANDLERS.keys())}")"""))

cells.append(nbf.v4.new_markdown_cell("""## Compute per-peer supply dynamics

Default CoinDesk → CoinGecko-implied path runs first; then any handler
registered in `CUSTOM_SUPPLY_HANDLERS` runs and may override fields or
append to `needs_custom`."""))

cells.append(nbf.v4.new_code_cell("""dynamics_rows = []
for peer in tqdm(peers, desc="Supply dynamics"):
    try:
        dyn = supply_dynamics(peer, window_days=365)
    except Exception as e:
        print(f"  [warn] {peer.symbol}: {e}")
        dyn = {}
    # Stringify the list field so it survives the round-trip to CSV.
    dyn["needs_custom"] = "; ".join(dyn.get("needs_custom") or []) or None
    dyn["symbol"] = peer.symbol
    dynamics_rows.append(dyn)

dyn_df = pd.DataFrame(dynamics_rows)
cols = [
    "symbol", "coindesk_covered", "inflation_source",
    "gross_inflation_annualized", "burn_rate_annualized", "net_inflation_annualized",
    "locked_supply_pct", "staked_supply_pct", "locked_plus_staked_pct",
    "custom_handler_applied", "needs_custom",
]
dyn_df[cols].round(4)"""))

cells.append(nbf.v4.new_markdown_cell("""## Merge into a single peer table

Start from the ingest snapshot, append supply dynamics, then compute incentive expense and supply velocity.

The economic-earnings call now passes the full dynamics dict (not just
`gross_inflation`) so the `needs_custom` flags propagate into the
`ee_inherits_flags` column — making it visible when an incentive-expense
number is built on a flagged input."""))

cells.append(nbf.v4.new_code_cell("""peer_table = snapshot.merge(dyn_df, on="symbol", how="left")

# Supply velocity — universal metric (CoinGecko volume / circ supply, annualized)
peer_table["supply_velocity_annualized"] = peer_table.apply(
    lambda r: supply_velocity(r.get("volume_24h"), r.get("circ_supply"), r.get("price_usd")),
    axis=1,
)

# ---------------------------------------------------------------------------
# Burns + Buybacks — unified USD metric, annualized
# ---------------------------------------------------------------------------
# Rolls up per-project sources into one comparable column:
#   ETH/SOL : burn_rate_annualized × market_cap
#   AAVE    : aave_buyback_spend_usd_30d × 12  (30d preferred — 365d is front-loaded)
#   LINK    : link_reserve_annualized_link × price_usd  (130K LINK/wk × 52, mid-point)
#   UNI     : uni_firepit_burn_annual_tokens × price_usd  (~4M UNI/yr Firepit)
#   LDO     : $20M buyback approved 2026-03-30 — too early to annualize; flagged via
#             ldo_buyback_started column, not modeled in this USD figure
#   CRV/OP  : no buyback or burn mechanism
def _buyback_burn_usd(row) -> float | None:
    sym = row["symbol"]
    price = row.get("price_usd")
    mc = row.get("market_cap")
    if sym in ("ETH", "SOL"):
        b = row.get("burn_rate_annualized")
        return float(b * mc) if pd.notna(b) and pd.notna(mc) else None
    if sym == "AAVE":
        v = row.get("aave_buyback_spend_usd_30d")
        return float(v * 12) if pd.notna(v) else None
    if sym == "LINK":
        tokens = row.get("link_reserve_annualized_link")
        return float(tokens * price) if pd.notna(tokens) and pd.notna(price) else None
    if sym == "UNI":
        # Prefer the Dune-sourced USD figure (uses actual avg price at burn time)
        usd = row.get("uni_firepit_burn_usd")
        if pd.notna(usd):
            return float(usd)
        tokens = row.get("uni_firepit_burn_annual_tokens")
        return float(tokens * price) if pd.notna(tokens) and pd.notna(price) else None
    return None

peer_table["buyback_burn_usd_annualized"] = peer_table.apply(_buyback_burn_usd, axis=1)
print("Burns + Buybacks (annualized USD):")
print(peer_table[["symbol", "buyback_burn_usd_annualized"]].assign(
    usd_m=lambda d: d["buyback_burn_usd_annualized"].map(lambda v: f"${v/1e6:,.1f}M" if pd.notna(v) else "—")
)[["symbol", "usd_m"]].to_string(index=False))

# Incentive expense / economic earnings / economic P/E
ee_rows = []
for _, row in peer_table.iterrows():
    peer = next(p for p in peers if p.symbol == row["symbol"])
    # Pass the full dynamics dict so flags propagate.
    nc_raw = row.get("needs_custom")
    nc_list = nc_raw.split("; ") if isinstance(nc_raw, str) and nc_raw else []
    dyn_dict = {
        "gross_inflation_annualized": row.get("gross_inflation_annualized"),
        "needs_custom": nc_list,
    }
    ee = economic_earnings(peer, row, dyn_dict)
    if isinstance(ee.get("ee_inherits_flags"), list):
        ee["ee_inherits_flags"] = "; ".join(ee["ee_inherits_flags"]) or None
    ee_rows.append({**ee, "symbol": row["symbol"]})

ee_df = pd.DataFrame(ee_rows)
peer_table = peer_table.merge(ee_df, on="symbol", how="left")
print(f"Peer table: {peer_table.shape}")"""))

cells.append(nbf.v4.new_markdown_cell("""## Headline comparison table

The columns most useful for the methodology writeup and dashboard header.
The trailing two columns make the per-project custom-logic layer visible."""))

cells.append(nbf.v4.new_code_cell("""headline_cols = [
    "symbol", "category", "value_accrual",
    "market_cap", "fdv", "fdv_mc_ratio",
    "annualized_revenue", "mcap_over_revenue",
    "net_inflation_annualized", "locked_supply_pct", "staked_supply_pct",
    "buyback_burn_usd_annualized",
    "token_incentive_expense_usd", "incentive_over_revenue", "economic_earnings_usd",
    "inflation_source", "custom_handler_applied", "needs_custom",
]
view = peer_table[[c for c in headline_cols if c in peer_table.columns]].copy()
for c in ("market_cap", "fdv", "annualized_revenue", "token_incentive_expense_usd",
          "economic_earnings_usd", "buyback_burn_usd_annualized"):
    if c in view.columns:
        view[c] = view[c].map(lambda v: f"${v/1e6:,.1f}M" if pd.notna(v) else "—")
for c in ("fdv_mc_ratio", "mcap_over_revenue", "supply_velocity_annualized", "incentive_over_revenue"):
    if c in view.columns:
        view[c] = view[c].map(lambda v: f"{v:,.2f}" if pd.notna(v) else "—")
for c in ("net_inflation_annualized", "locked_supply_pct", "staked_supply_pct"):
    if c in view.columns:
        view[c] = view[c].map(lambda v: f"{v*100:+.2f}%" if pd.notna(v) else "—")
view"""))

cells.append(nbf.v4.new_markdown_cell("""## Sanity & coverage checks

1. **Locked + staked should not exceed ~100%** of circulating supply.
2. **Every peer should have run through a registered custom handler** — if a
   peer shows `custom_handler_applied == None`, the registry is missing an
   entry and the table is silently using the generic default.
3. **Flagged metrics roll up** — print the symbol → needs_custom map so the
   gaps are visible at a glance, not buried in the CSV.
"""))

cells.append(nbf.v4.new_code_cell("""checks = []

# 1. Dormancy totals under 100%
over = peer_table[peer_table["locked_plus_staked_pct"] > 1.0]
checks.append(("locked+staked under 100%", len(over) == 0, f"{len(over)} violators: {list(over['symbol'])}"))

# 2. Every peer has a registered handler
unhandled = peer_table[peer_table["custom_handler_applied"].isna()]
checks.append((
    "every peer has a custom handler",
    len(unhandled) == 0,
    f"{len(unhandled)} unhandled: {list(unhandled['symbol'])}",
))

for name, passed, detail in checks:
    print(f"  [{'OK' if passed else 'CHECK'}] {name:40s} {detail}")

print()
print("Per-peer custom-logic flags:")
flag_view = peer_table[["symbol", "custom_handler_applied", "needs_custom"]].copy()
for _, r in flag_view.iterrows():
    flags = r["needs_custom"] or "(none)"
    handler = r["custom_handler_applied"] or "(default only)"
    print(f"  {r['symbol']:5s} {handler:35s}  needs: {flags}")"""))

cells.append(nbf.v4.new_markdown_cell("""## Forward supply curve (90-day)

Combines two sources of at-risk new supply into a single daily time series:

1. **Inflation slope** — `gross_inflation_annualized / 365` per day, continuous ramp
   (validator rewards, gauge emissions, etc.). Only counts newly minted tokens.
   EIP-1559 burn, priority fees, and MEV are redistribution of existing supply,
   not new issuance, and are not included.
2. **Unlock events** — discrete cliff jumps from `unlocks.yaml`. For peers with
   `counted_in_inflation: true` (e.g. ETH validator issuance, CRV gauge
   emissions), unlock events are ignored to avoid double-counting with the
   inflation slope.

Output is normalized to % of current circulating supply so peers are comparable
on a single y-axis in `03_charts.ipynb`."""))

cells.append(nbf.v4.new_code_cell("""import yaml
from datetime import date

with open(ROOT / "unlocks.yaml") as f:
    unlocks_yaml = yaml.safe_load(f)

# Rehydrate per-peer dynamics dicts from peer_table so the curve reads gross
# inflation straight out of the already-computed table (not a second call).
dynamics_by_symbol = {
    r["symbol"]: {"gross_inflation_annualized": r.get("gross_inflation_annualized") or 0.0}
    for _, r in peer_table.iterrows()
}

as_of = pd.to_datetime(unlocks_yaml["as_of"]).date()
forward_panel = build_forward_supply_panel(
    peers, peer_table, dynamics_by_symbol, unlocks_yaml,
    days=unlocks_yaml.get("window_days", 90),
    as_of=as_of,
)

print(f"Forward supply panel: {forward_panel.shape} ({forward_panel['symbol'].nunique()} peers × {forward_panel['days_out'].nunique()} days)")
print()
print(f"Day-{unlocks_yaml.get('window_days', 90)} cumulative at-risk new supply (% of circ):")
day_end = forward_panel[forward_panel["days_out"] == unlocks_yaml.get("window_days", 90)].copy()
day_end["infl_pct"] = (day_end["inflation_cumulative_pct"] * 100).round(3)
day_end["unlock_pct"] = (day_end["unlock_cumulative_pct"] * 100).round(3)
day_end["total_pct"] = (day_end["total_cumulative_pct"] * 100).round(3)
day_end["buyback_pct"] = (day_end["buyback_cumulative_pct"] * 100).round(3)
day_end["net_pct"] = (day_end["net_cumulative_pct"] * 100).round(3)
day_end[["symbol", "infl_pct", "unlock_pct", "total_pct", "buyback_pct", "net_pct"]].sort_values("total_pct", ascending=False)"""))

cells.append(nbf.v4.new_markdown_cell("""## Incentive Capture Yield

Annualized yield available to **active** token holders who opt into the primary
yield mechanism (staking, locking, validating). Sourced from `incentive_yield.yaml`
— manually curated, re-verify quarterly.

Peers excluded (no yield path to token holders today):
- **UNI**: fee switch off
- **LDO**: stETH yield flows to stETH holders, not LDO holders
- **OP**: no staking or fee-return mechanism
- **AAVE**: stkAAVE retired post-Aavenomics restructure (AIP-434)
"""))

cells.append(nbf.v4.new_code_cell("""iy_rows = []
for peer in peers:
    iy = incentive_capture_yield(peer.symbol)
    iy["symbol"] = peer.symbol
    iy_rows.append(iy)

iy_df = pd.DataFrame(iy_rows)
peer_table = peer_table.merge(iy_df[["symbol", "incentive_yield_annualized", "incentive_yield_mechanism"]], on="symbol", how="left")

# Display summary
view = peer_table[["symbol", "incentive_yield_mechanism", "incentive_yield_annualized"]].copy()
view["yield_pct"] = view["incentive_yield_annualized"].map(lambda v: f"{v*100:.2f}%" if pd.notna(v) else "—")
print(view[["symbol", "incentive_yield_mechanism", "yield_pct"]].to_string(index=False))
"""))

cells.append(nbf.v4.new_markdown_cell("""## Rewards-Adjusted Dilution

Net annualized dilution after subtracting what active token holders can earn back.

```
rewards_adjusted_dilution = (net_cumulative_pct_90d × 365/90) − incentive_yield_annualized
```

- **Net dilution** is annualized from the 90-day forward curve (`net_cumulative_pct`),
  which already has buybacks/burns subtracted. For peers with no buyback program
  (LDO, CRV, OP), net = gross.
- **Incentive yield** is the annualized yield from `incentive_yield.yaml`; 0 for
  peers with no active yield path.
- A **negative result** means active holders are net positive — yield exceeds dilution.
- A **positive result** means even active holders are being diluted on net.
"""))

cells.append(nbf.v4.new_code_cell("""# Pull day-90 net_cumulative_pct from the forward panel.
# Fill NaN (peers with no buybacks) with total_cumulative_pct — net = gross for them.
ANNUALIZE = 365 / 90

day90 = forward_panel[forward_panel["days_out"] == 90][["symbol", "net_cumulative_pct", "total_cumulative_pct"]].copy()
day90["net_pct_90d"] = day90["net_cumulative_pct"].fillna(day90["total_cumulative_pct"])
day90["net_dilution_annualized"] = day90["net_pct_90d"] * ANNUALIZE
day90 = day90[["symbol", "net_dilution_annualized"]]

peer_table = peer_table.merge(day90, on="symbol", how="left")

# Incentive yield is 0 where not applicable (not NaN) for the arithmetic.
iy_fill = peer_table["incentive_yield_annualized"].fillna(0.0)
peer_table["rewards_adjusted_dilution"] = peer_table["net_dilution_annualized"] - iy_fill

# Display
rad = peer_table[["symbol", "net_dilution_annualized", "incentive_yield_annualized", "rewards_adjusted_dilution"]].copy()
for c in ("net_dilution_annualized", "incentive_yield_annualized", "rewards_adjusted_dilution"):
    rad[c] = rad[c].map(lambda v: f"{v*100:+.2f}%" if pd.notna(v) else "—")
print(rad.sort_values("rewards_adjusted_dilution").to_string(index=False))
"""))

cells.append(nbf.v4.new_markdown_cell("""## Save"""))

cells.append(nbf.v4.new_code_cell("""out_path = METRICS_DIR / "peer_table.csv"
peer_table.to_csv(out_path, index=False)
print(f"Wrote {out_path}  ({len(peer_table)} rows, {len(peer_table.columns)} cols)")

curve_path = METRICS_DIR / "forward_supply_curve.csv"
forward_panel.to_csv(curve_path, index=False)
print(f"Wrote {curve_path}  ({len(forward_panel)} rows, {len(forward_panel.columns)} cols)")"""))

cells.append(nbf.v4.new_markdown_cell("""## Next

- `03_charts.ipynb` — Plotly visualizations driven by `peer_table.csv`. Flagged metrics get a "⚠️" annotation on the chart.
- `04_analysis.ipynb` — written findings and LINK positioning narrative
- Author the Dune queries that retire the items in `needs_custom`
- Vercel Next.js dashboard
"""))

nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}

OUT.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, OUT)
print(f"Wrote {OUT}")
