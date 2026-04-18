"""Generate notebooks/03_charts.ipynb from Python source.

Six chart sections, all using Plotly for interactivity.
LINK is highlighted as the subject peer throughout.
Charts saved to data/charts/ as HTML + static PNG.
"""
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks" / "03_charts.ipynb"

nb = nbf.v4.new_notebook()
cells = []

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

cells.append(nbf.v4.new_markdown_cell("""# 03 — Charts

Produces the visual layer for the Chainlink valuation framework.

**Data sources:**
- `data/metrics/peer_table.csv` — snapshot metrics from `02_metrics.ipynb`
- DeFiLlama API (live) — fee/revenue time series
- CoinGecko API (live) — 365d price performance
- `unlocks.yaml` — 90d at-risk unlock schedule
- Dune (live, via cached results) — 180d dormancy

**Prerequisite:** re-run `02_metrics.ipynb` after any Dune query update to
ensure `peer_table.csv` reflects the latest supply dynamics and buyback data.

All figures saved to `data/charts/` as `<name>.html` (interactive) and
`<name>.png` (static, requires `kaleido`).

> LINK is highlighted in **#2563EB** (Chainlink blue) throughout. Other peers
> use a neutral palette so LINK stands out in peer comparisons.
"""))

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

cells.append(nbf.v4.new_code_cell("""\
import sys
from pathlib import Path

ROOT = Path().resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import yaml

from src.config import load_peers, METRICS_DIR, CHARTS_DIR
from src.sources import defillama, coingecko

CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# --- Load peer table ---
pt = pd.read_csv(METRICS_DIR / "peer_table.csv")
peers = load_peers()
peer_map = {p.symbol: p for p in peers}

print(f"Loaded {len(pt)} peers from peer_table.csv")
print(pt[["symbol", "market_cap", "annualized_fees", "annualized_revenue"]].to_string(index=False))
"""))

cells.append(nbf.v4.new_code_cell("""\
# --- Shared style helpers ---

# Per-peer brand colours (neutral for context, distinct for LINK)
COLORS = {
    "LINK": "#2563EB",  # Chainlink blue — subject peer
    "ETH":  "#6B7280",
    "SOL":  "#9333EA",
    "AAVE": "#B45309",
    "UNI":  "#E11D48",
    "LDO":  "#059669",
    "CRV":  "#D97706",
    "OP":   "#EA580C",
}

def peer_color(symbol: str) -> str:
    return COLORS.get(symbol, "#94A3B8")

def bar_colors(symbols) -> list:
    return [peer_color(s) for s in symbols]

def save_fig(fig, name: str) -> None:
    path_html = CHARTS_DIR / f"{name}.html"
    fig.write_html(str(path_html))
    print(f"  Saved {path_html.name}")
    try:
        path_png = CHARTS_DIR / f"{name}.png"
        fig.write_image(str(path_png), width=1100, height=550, scale=2)
        print(f"  Saved {path_png.name}")
    except Exception:
        print("  (kaleido not installed — PNG skipped; HTML saved)")

LAYOUT = dict(
    font_family="Inter, sans-serif",
    plot_bgcolor="white",
    paper_bgcolor="white",
    margin=dict(l=60, r=30, t=60, b=50),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
"""))

# ---------------------------------------------------------------------------
# Section 1 — Valuation multiples
# ---------------------------------------------------------------------------

cells.append(nbf.v4.new_markdown_cell("""\
---
## 1 · Valuation Multiples

Peer-ranked horizontal bar charts for the three headline multiples.

- **P/F** = Market Cap / Annualized Total Fees
- **P/RF** = Market Cap / Annualized Retained Fees (Revenue)
- **Economic P/E** = Market Cap / Economic Earnings (Revenue − Token Incentive Expense)

Lower = cheaper relative to activity generated. LINK highlighted.
"""))

cells.append(nbf.v4.new_code_cell("""\
multiples = pt[["symbol", "mcap_over_fees", "mcap_over_revenue", "economic_pe"]].copy()
multiples = multiples.rename(columns={
    "mcap_over_fees": "P/F",
    "mcap_over_revenue": "P/RF",
    "economic_pe": "Econ P/E",
})

for col in ["P/F", "P/RF", "Econ P/E"]:
    fig_data = multiples.dropna(subset=[col]).sort_values(col)
    fig = go.Figure(go.Bar(
        x=fig_data[col],
        y=fig_data["symbol"],
        orientation="h",
        marker_color=bar_colors(fig_data["symbol"]),
        text=fig_data[col].apply(lambda v: f"{v:.1f}x"),
        textposition="outside",
    ))
    title_map = {
        "P/F":      "Price / Annualized Fees",
        "P/RF":     "Price / Annualized Retained Revenue",
        "Econ P/E": "Economic P/E  (MC / Economic Earnings)",
    }
    fig.update_layout(**LAYOUT,
        title=title_map[col],
        xaxis_title=col,
        yaxis_title="",
        height=380,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#F1F5F9")
    save_fig(fig, f"valuation_{col.lower().replace('/', '_')}")
    fig.show()
"""))

# ---------------------------------------------------------------------------
# Section 2 — Revenue & fees
# ---------------------------------------------------------------------------

cells.append(nbf.v4.new_markdown_cell("""\
---
## 2 · Revenue & Fees

Two views:
1. **Annualized snapshot bar** — current run-rate across all peers
2. **90d daily trend lines** — recent trajectory per peer (DeFiLlama live)
"""))

cells.append(nbf.v4.new_code_cell("""\
# 2a — Snapshot bar: annualized fees vs revenue
snap = pt[["symbol", "annualized_fees", "annualized_revenue"]].dropna(subset=["annualized_fees"])
snap = snap.sort_values("annualized_fees", ascending=False)

fig = go.Figure()
fig.add_trace(go.Bar(
    name="Total Fees",
    x=snap["symbol"],
    y=snap["annualized_fees"] / 1e6,
    marker_color=[peer_color(s) for s in snap["symbol"]],
    opacity=0.9,
))
fig.add_trace(go.Bar(
    name="Retained Revenue",
    x=snap["symbol"],
    y=snap["annualized_revenue"] / 1e6,
    marker_color=[peer_color(s) for s in snap["symbol"]],
    opacity=0.45,
))
fig.update_layout(**LAYOUT,
    title="Annualized Fees vs Retained Revenue (USD)",
    yaxis_title="USD millions",
    barmode="overlay",
    height=420,
)
fig.update_yaxes(showgrid=True, gridcolor="#F1F5F9")
save_fig(fig, "fees_snapshot")
fig.show()
"""))

cells.append(nbf.v4.new_code_cell("""\
# 2b — 90d daily fee trend (DeFiLlama)
from tqdm.auto import tqdm

fee_series = {}
for p in tqdm(peers, desc="Fetching fee series"):
    try:
        df = defillama.get_fees_timeseries(p.defillama_slug, data_type="dailyFees")
        if not df.empty:
            df = df.rename(columns={"value": "fees_usd"})
            df = df[df["date"] >= pd.Timestamp.now() - pd.Timedelta(days=90)]
            fee_series[p.symbol] = df
    except Exception as e:
        print(f"  {p.symbol}: {e}")

fig = go.Figure()
for symbol, df in sorted(fee_series.items()):
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["fees_usd"] / 1e6,
        mode="lines",
        name=symbol,
        line=dict(
            color=peer_color(symbol),
            width=3 if symbol == "LINK" else 1.5,
        ),
        opacity=1.0 if symbol == "LINK" else 0.7,
    ))
fig.update_layout(**LAYOUT,
    title="Daily Total Fees — Trailing 90 Days (USD millions)",
    yaxis_title="USD millions",
    height=460,
)
fig.update_yaxes(showgrid=True, gridcolor="#F1F5F9")
save_fig(fig, "fees_90d_trend")
fig.show()
"""))

# ---------------------------------------------------------------------------
# Section 3 — Supply dynamics
# ---------------------------------------------------------------------------

cells.append(nbf.v4.new_markdown_cell("""\
---
## 3 · Supply Dynamics

- **Net inflation bar** — gross issuance minus burn, annualized % of circ supply
- **Locked + staked %** — share of supply that is illiquid (CoinDesk)
- **At-risk unlocks** — 90d forward unlock $ and % of circ (from `unlocks.yaml`)
"""))

cells.append(nbf.v4.new_code_cell("""\
# 3a — Net inflation (gross vs burn vs net)
inf = pt[["symbol", "gross_inflation_annualized", "burn_rate_annualized",
          "net_inflation_annualized"]].copy()
inf = inf.dropna(subset=["gross_inflation_annualized"])
inf = inf.sort_values("net_inflation_annualized", ascending=False)

fig = go.Figure()
fig.add_trace(go.Bar(
    name="Gross Issuance",
    x=inf["symbol"],
    y=(inf["gross_inflation_annualized"] * 100),
    marker_color=[peer_color(s) for s in inf["symbol"]],
    opacity=0.5,
))
fig.add_trace(go.Bar(
    name="Net Inflation (after burn)",
    x=inf["symbol"],
    y=(inf["net_inflation_annualized"] * 100),
    marker_color=[peer_color(s) for s in inf["symbol"]],
    opacity=1.0,
))
fig.update_layout(**LAYOUT,
    title="Annualized Token Inflation — Gross vs Net (% of Circulating Supply)",
    yaxis_title="%",
    barmode="overlay",
    height=400,
)
fig.update_yaxes(showgrid=True, gridcolor="#F1F5F9", zeroline=True, zerolinecolor="#CBD5E1")
save_fig(fig, "supply_inflation")
fig.show()
"""))

cells.append(nbf.v4.new_code_cell("""\
# 3b — Locked + staked %
liq = pt[["symbol", "locked_supply_pct", "staked_supply_pct"]].copy()
liq["locked_supply_pct"] = liq["locked_supply_pct"].fillna(0)
liq["staked_supply_pct"] = liq["staked_supply_pct"].fillna(0)
liq["total_illiquid"] = liq["locked_supply_pct"] + liq["staked_supply_pct"]
liq = liq.sort_values("total_illiquid", ascending=False)

fig = go.Figure()
fig.add_trace(go.Bar(
    name="Locked",
    x=liq["symbol"],
    y=(liq["locked_supply_pct"] * 100),
    marker_color="#94A3B8",
))
fig.add_trace(go.Bar(
    name="Staked",
    x=liq["symbol"],
    y=(liq["staked_supply_pct"] * 100),
    marker_color="#2563EB",
))
fig.update_layout(**LAYOUT,
    title="Illiquid Supply % — Locked + Staked (% of Circulating)",
    yaxis_title="%",
    barmode="stack",
    height=400,
)
fig.update_yaxes(showgrid=True, gridcolor="#F1F5F9")
save_fig(fig, "supply_illiquid")
fig.show()
"""))

cells.append(nbf.v4.new_markdown_cell("""\
### 3c · Forward supply curve — 90-day at-risk new supply

Combines two sources of forward supply pressure into one visual so the
"how is this project funding itself?" question is answerable at a glance:

- **Inflation slope** — continuous new issuance (validator rewards, gauge
  emissions). Only newly minted tokens count; EIP-1559 burn, priority fees,
  and MEV are redistribution of existing supply, not new issuance.
- **Unlock steps** — discrete cliff events from `unlocks.yaml`. For peers with
  `counted_in_inflation: true`, unlocks are ignored to avoid double-counting
  the emission that already shows up in the inflation slope.

A slope-dominated peer (SOL, CRV) funds itself through inflation. A
step-dominated peer (OP) funds itself through insider cliffs. Both are sell
pressure; this chart puts them on the same y-axis.
"""))

cells.append(nbf.v4.new_code_cell("""\
panel = pd.read_csv(METRICS_DIR / "forward_supply_curve.csv", parse_dates=["date"])
print(f"Forward panel: {panel.shape}  symbols: {sorted(panel['symbol'].unique())}")

end_day = panel["days_out"].max()
summary = panel[panel["days_out"] == end_day][
    ["symbol", "inflation_cumulative_pct", "unlock_cumulative_pct", "total_cumulative_pct"]
].copy()
for c in ("inflation_cumulative_pct", "unlock_cumulative_pct", "total_cumulative_pct"):
    summary[c] = (summary[c] * 100).round(3)
summary = summary.sort_values("total_cumulative_pct", ascending=False)
print()
print(f"Day-{end_day} cumulative at-risk new supply (% of circ):")
print(summary.to_string(index=False))
"""))

cells.append(nbf.v4.new_code_cell("""\
# Unified line chart: total forward supply pressure, one line per peer.
# Smooth slopes = inflation-driven peers; visible vertical jumps = cliff unlocks.
PEER_ORDER = ["LINK", "OP", "CRV", "SOL", "UNI", "ETH", "AAVE", "LDO"]

fig = go.Figure()
for sym in PEER_ORDER:
    sub = panel[panel["symbol"] == sym]
    if sub.empty:
        continue
    fig.add_trace(go.Scatter(
        x=sub["date"],
        y=sub["total_cumulative_pct"] * 100,
        mode="lines",
        name=sym,
        line=dict(
            color=peer_color(sym),
            width=3 if sym == "LINK" else 1.8,
            shape="hv",  # step shape so cliff events show as clean vertical jumps
        ),
        opacity=1.0 if sym == "LINK" else 0.85,
        hovertemplate="<b>%{fullData.name}</b><br>%{x|%Y-%m-%d}<br>%{y:.2f}% of circ<extra></extra>",
    ))

fig.update_layout(**LAYOUT,
    title="90-Day Forward Supply Pressure — cumulative new supply as % of circulating",
    xaxis_title="Date",
    yaxis_title="% of Circulating Supply",
    height=520,
    hovermode="x unified",
)
fig.update_yaxes(showgrid=True, gridcolor="#F1F5F9", ticksuffix="%")
save_fig(fig, "forward_supply_total")
fig.show()
"""))

# ---------------------------------------------------------------------------
# Section 3d — Net dilution (gross − buybacks/burns)
# ---------------------------------------------------------------------------

cells.append(nbf.v4.new_markdown_cell("""\
---
### 3d · Net 90-Day Dilution — gross supply pressure minus buybacks & burns

The gross forward supply curve (3c) shows all new tokens entering circulation.
This chart subtracts scheduled buybacks and protocol burns to show **net**
dilution: what token holders actually absorb after value-return mechanisms fire.

Buyback/burn cadences per peer:
- **ETH / SOL / UNI**: daily (continuous burn — EIP-1559, base-fee, Firepit)
- **LINK**: weekly (Reserve dutch-auction accumulation, ~130K LINK/week)
- **AAVE**: monthly (TWAP executor buyback, ~$3.6M/30d post AIP-434)
- **CRV / OP / LDO**: no buyback or burn — net = gross

A line **below zero** means buybacks exceed new issuance over that window
(net deflationary). The chart shows whether the buyback program materially
offsets dilution or is cosmetic relative to inflation + unlocks.
"""))

cells.append(nbf.v4.new_code_cell("""\
# panel already loaded above (3c); net_cumulative_pct is the new column.
# Peers with no buyback program (LDO, CRV, OP) have NaN — fill with gross so
# they still appear on the chart (net = gross when no offset exists).
panel_net = panel.copy()
panel_net["net_cumulative_pct"] = panel_net["net_cumulative_pct"].fillna(
    panel_net["total_cumulative_pct"]
)

fig = go.Figure()
for sym in PEER_ORDER:
    sub = panel_net[panel_net["symbol"] == sym]
    if sub.empty:
        continue
    fig.add_trace(go.Scatter(
        x=sub["date"],
        y=sub["net_cumulative_pct"] * 100,
        mode="lines",
        name=sym,
        line=dict(
            color=peer_color(sym),
            width=3 if sym == "LINK" else 1.8,
            shape="hv",
        ),
        opacity=1.0 if sym == "LINK" else 0.85,
        hovertemplate="<b>%{fullData.name}</b><br>%{x|%Y-%m-%d}<br>%{y:.2f}% net<extra></extra>",
    ))

# Zero line — cross = buybacks exceed gross dilution
fig.add_hline(y=0, line_dash="dot", line_color="#94A3B8", line_width=1)

fig.update_layout(**LAYOUT,
    title="90-Day Net Dilution — gross supply pressure minus buybacks & burns",
    xaxis_title="Date",
    yaxis_title="% of Circulating Supply (net)",
    height=520,
    hovermode="x unified",
)
fig.update_yaxes(showgrid=True, gridcolor="#F1F5F9", ticksuffix="%")
save_fig(fig, "forward_supply_net")
fig.show()
"""))

# ---------------------------------------------------------------------------
# Section 3e — Incentive Capture Yield
# ---------------------------------------------------------------------------

cells.append(nbf.v4.new_markdown_cell("""\
---
### 3e · Incentive Capture Yield — annualized yield to active token holders

Annualized yield available to token holders who opt into the primary yield
mechanism: staking (LINK, ETH, SOL) or locking (CRV veCRV). Passive holders
receive nothing. Peers with no current yield path (UNI, LDO, OP, AAVE) show
zero — that is itself the finding.

This metric sets up the **Rewards-Adjusted Dilution** framing: a project with
high gross dilution but high incentive yield may be better for active holders
than a project with low dilution but no yield.
"""))

cells.append(nbf.v4.new_code_cell("""\
iy = pt[["symbol", "incentive_yield_annualized", "incentive_yield_mechanism"]].copy()
iy["incentive_yield_annualized"] = iy["incentive_yield_annualized"].fillna(0.0)
iy = iy.sort_values("incentive_yield_annualized", ascending=True)

fig = go.Figure(go.Bar(
    x=iy["incentive_yield_annualized"] * 100,
    y=iy["symbol"],
    orientation="h",
    marker_color=[peer_color(s) for s in iy["symbol"]],
    text=[
        f"{v:.2f}%  {mech}" if mech else f"{v:.2f}%"
        for v, mech in zip(iy["incentive_yield_annualized"] * 100, iy["incentive_yield_mechanism"].fillna(""))
    ],
    textposition="outside",
    cliponaxis=False,
    hovertemplate="<b>%{y}</b><br>Yield: %{x:.2f}%<extra></extra>",
))
fig.update_layout(**LAYOUT,
    title="Incentive Capture Yield — annualized yield to active token holders",
    xaxis_title="Annualized Yield (%)",
    yaxis_title=None,
    height=420,
)
fig.update_xaxes(ticksuffix="%")
save_fig(fig, "incentive_capture_yield")
fig.show()
"""))

# ---------------------------------------------------------------------------
# Section 3f — Rewards-Adjusted Dilution
# ---------------------------------------------------------------------------

cells.append(nbf.v4.new_markdown_cell("""\
---
### 3f · Rewards-Adjusted Dilution — net dilution after incentive yield

Annualized net dilution (buybacks already subtracted) minus the yield active
holders can earn back. Formula: `(net_cumulative_pct_90d × 365/90) − incentive_yield_annualized`

- **Negative** = active holders are net positive; yield exceeds dilution
- **Positive** = even stakers/lockers absorb net dilution
- Peers with no buyback program (LDO, CRV, OP): net dilution = gross dilution
- Peers with no yield (UNI, LDO, OP, AAVE): yield term = 0
"""))

cells.append(nbf.v4.new_code_cell("""\
rad = pt[["symbol", "net_dilution_annualized", "incentive_yield_annualized", "rewards_adjusted_dilution"]].copy()
rad["incentive_yield_annualized"] = rad["incentive_yield_annualized"].fillna(0.0)
rad = rad.sort_values("rewards_adjusted_dilution", ascending=True)

# Color: negative bars (good for holders) get a muted green; positive get peer color.
def _rad_color(sym, val):
    if pd.notna(val) and val < 0:
        return "#22C55E"  # green — net positive for active holders
    return peer_color(sym)

fig = go.Figure()

# Net dilution bar (base)
fig.add_trace(go.Bar(
    name="Net annualized dilution",
    x=rad["symbol"],
    y=rad["net_dilution_annualized"] * 100,
    marker_color=[peer_color(s) for s in rad["symbol"]],
    opacity=0.45,
))

# Incentive yield bar (stacked negative — offsets dilution downward)
fig.add_trace(go.Bar(
    name="Incentive yield (offset)",
    x=rad["symbol"],
    y=-rad["incentive_yield_annualized"] * 100,
    marker_color="#22C55E",
    opacity=0.7,
))

# Rewards-adjusted dot overlay
fig.add_trace(go.Scatter(
    name="Rewards-adjusted dilution",
    x=rad["symbol"],
    y=rad["rewards_adjusted_dilution"] * 100,
    mode="markers",
    marker=dict(size=10, color=[_rad_color(s, v) for s, v in zip(rad["symbol"], rad["rewards_adjusted_dilution"])],
                line=dict(width=1.5, color="#1E293B")),
))

fig.add_hline(y=0, line_dash="dot", line_color="#94A3B8", line_width=1)

fig.update_layout(**LAYOUT,
    title="Rewards-Adjusted Dilution — annualized net dilution minus incentive yield",
    xaxis_title=None,
    yaxis_title="Annualized % of Circulating Supply",
    barmode="relative",
    height=480,
)
fig.update_yaxes(ticksuffix="%")
save_fig(fig, "rewards_adjusted_dilution")
fig.show()
"""))

# ---------------------------------------------------------------------------
# Section 4 — Dormancy
# ---------------------------------------------------------------------------

cells.append(nbf.v4.new_markdown_cell("""\
---
## 4 · 180-Day Dormancy

Share of circulating supply that has **not sent** the token in the last 180 days
(outbound-transfer signal — dust-attack resistant).

- ERC-20 tokens (LINK/AAVE/UNI/LDO/CRV): `tokens_ethereum.balances` +
  `tokens.transfers` filtered by `from = holder` (Dune query 7328758)
- OP: `tokens_optimism.*` (Dune query 7328772)
- SOL: `solana_utils.latest_balances` `block_time` proxy (dust-safe — rent barriers)
- ETH: native-balance reconstruction from genesis + withdrawals + tx/trace flows
  (Dune query 7332769)

See STATUS.md for full methodology notes.
"""))

cells.append(nbf.v4.new_code_cell("""\
from src.metrics.compute import dormancy, _default_supply_dynamics
from src.sources import dune as dune_src

dormancy_rows = []
for p in tqdm(peers, desc="Computing dormancy"):
    try:
        snap = pt[pt["symbol"] == p.symbol].iloc[0]
        dyn = _default_supply_dynamics(p)
        d = dormancy(p, snap, dyn)
        dormancy_rows.append({
            "symbol": p.symbol,
            "dormant_pct": d.get("dormant_supply_pct_180d"),
            "source": d.get("dormancy_source", ""),
        })
    except Exception as e:
        print(f"  {p.symbol}: {e}")
        dormancy_rows.append({"symbol": p.symbol, "dormant_pct": None, "source": "error"})

dorm_df = pd.DataFrame(dormancy_rows).dropna(subset=["dormant_pct"])
dorm_df = dorm_df.sort_values("dormant_pct", ascending=False)
print(dorm_df.to_string(index=False))
"""))

cells.append(nbf.v4.new_code_cell("""\
fig = go.Figure(go.Bar(
    x=dorm_df["dormant_pct"] * 100,
    y=dorm_df["symbol"],
    orientation="h",
    marker_color=bar_colors(dorm_df["symbol"]),
    text=(dorm_df["dormant_pct"] * 100).apply(lambda v: f"{v:.1f}%"),
    textposition="outside",
    customdata=dorm_df["source"],
    hovertemplate="%{y}: %{x:.1f}% dormant<br>Source: %{customdata}<extra></extra>",
))
fig.update_layout(**LAYOUT,
    title="180-Day Dormant Supply % (outbound-sender signal)",
    xaxis_title="% of Circulating Supply",
    yaxis_title="",
    height=380,
)
fig.update_xaxes(showgrid=True, gridcolor="#F1F5F9", range=[0, 100])
save_fig(fig, "dormancy_180d")
fig.show()
"""))

# ---------------------------------------------------------------------------
# Section 5 — Price performance
# ---------------------------------------------------------------------------

cells.append(nbf.v4.new_markdown_cell("""\
---
## 5 · Price Performance — 365 Days

All prices indexed to 100 at the start of the window (365 days ago).

> CoinGecko free/demo tier caps history at 365 days.
"""))

cells.append(nbf.v4.new_code_cell("""\
price_series = {}
for p in tqdm(peers, desc="Fetching price series"):
    try:
        df = coingecko.get_market_chart_df(p.coingecko_id, days=365)
        if not df.empty:
            base = df.iloc[0]["price_usd"]
            df["indexed"] = df["price_usd"] / base * 100
            price_series[p.symbol] = df
    except Exception as e:
        print(f"  {p.symbol}: {e}")

fig = go.Figure()
for symbol, df in sorted(price_series.items()):
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["indexed"],
        mode="lines",
        name=symbol,
        line=dict(
            color=peer_color(symbol),
            width=3 if symbol == "LINK" else 1.5,
        ),
        opacity=1.0 if symbol == "LINK" else 0.6,
    ))
fig.add_hline(y=100, line_dash="dot", line_color="#94A3B8", line_width=1)
fig.update_layout(**LAYOUT,
    title="Price Performance — 365 Days (Indexed to 100)",
    yaxis_title="Index (100 = 365 days ago)",
    height=500,
)
fig.update_yaxes(showgrid=True, gridcolor="#F1F5F9")
save_fig(fig, "price_performance_365d")
fig.show()
"""))

# ---------------------------------------------------------------------------
# Section 6 — Summary export
# ---------------------------------------------------------------------------

cells.append(nbf.v4.new_markdown_cell("""\
---
## 6 · Summary Export

Export the augmented peer table (with dormancy) to `data/metrics/peer_table_with_dormancy.csv`
for use in the analysis notebook and Vercel dashboard.
"""))

cells.append(nbf.v4.new_code_cell("""\
pt_out = pt.copy()

# Merge dormancy
dorm_merge = dorm_df[["symbol", "dormant_pct", "source"]].rename(
    columns={"dormant_pct": "dormant_supply_pct_180d", "source": "dormancy_source"})
pt_out = pt_out.merge(dorm_merge, on="symbol", how="left")

out_path = METRICS_DIR / "peer_table_with_dormancy.csv"
pt_out.to_csv(out_path, index=False)
print(f"Exported {len(pt_out)} rows → {out_path}")

# Print headline summary
display_cols = ["symbol", "market_cap", "mcap_over_fees", "mcap_over_revenue",
                "net_inflation_annualized", "dormant_supply_pct_180d"]
print()
print(pt_out[display_cols].to_string(index=False))
"""))

# ---------------------------------------------------------------------------
# Assemble and write
# ---------------------------------------------------------------------------

nb.cells = cells
nb.metadata = {
    "kernelspec": {
        "display_name": "Chainlink Valuation",
        "language": "python",
        "name": "chainlink-valuation",
    },
    "language_info": {"name": "python", "version": "3.11.0"},
}

OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w") as f:
    nbf.write(nb, f)

print(f"Written: {OUT}")
