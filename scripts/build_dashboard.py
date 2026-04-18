"""Generate a static HTML dashboard from peer_table.csv + existing Plotly charts.

No Node, no framework, no build step — just Python reads the metrics CSV,
renders 6 HTML pages with Tailwind (CDN), and copies the Plotly charts into
dashboard/charts/ so iframes resolve. Vercel deploys the dashboard/ dir as
static hosting with zero config.

Usage:
    python scripts/build_dashboard.py

Output: dashboard/*.html + dashboard/charts/*.html
"""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "data" / "metrics" / "peer_table.csv"
CHARTS_SRC = ROOT / "data" / "charts"
OUT = ROOT / "dashboard"
OUT_CHARTS = OUT / "charts"

AS_OF = date(2026, 4, 18)
SUBJECT = "LINK"
LINK_BLUE = "#2563EB"

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def fmt_usd(v, precision=1):
    if v is None or pd.isna(v):
        return "—"
    v = float(v)
    if abs(v) >= 1e12:
        return f"${v / 1e12:.{precision}f}T"
    if abs(v) >= 1e9:
        return f"${v / 1e9:.{precision}f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.{precision}f}M"
    if abs(v) >= 1e3:
        return f"${v / 1e3:.{precision}f}K"
    return f"${v:.2f}"


def fmt_pct(v, precision=2, sign=False):
    if v is None or pd.isna(v):
        return "—"
    v = float(v) * 100
    return f"{v:+.{precision}f}%" if sign else f"{v:.{precision}f}%"


def fmt_num(v, precision=2):
    if v is None or pd.isna(v):
        return "—"
    v = float(v)
    if abs(v) >= 1e9:
        return f"{v / 1e9:.{precision}f}B"
    if abs(v) >= 1e6:
        return f"{v / 1e6:.{precision}f}M"
    if abs(v) >= 1e3:
        return f"{v / 1e3:.{precision}f}K"
    return f"{v:.{precision}f}"


def fmt_multiple(v, precision=1):
    if v is None or pd.isna(v):
        return "—"
    return f"{float(v):.{precision}f}x"


ACCRUAL_STYLES = {
    "burn": ("bg-orange-950/60 text-orange-300 ring-orange-900/50", "Burn"),
    "buyback": ("bg-emerald-950/60 text-emerald-300 ring-emerald-900/50", "Buyback"),
    "staking": ("bg-sky-950/60 text-sky-300 ring-sky-900/50", "Staking"),
    "fee_share": ("bg-violet-950/60 text-violet-300 ring-violet-900/50", "Fee Share"),
    "none": ("bg-zinc-800 text-zinc-400 ring-zinc-700", "None"),
}


def accrual_chip(mechanism):
    cls, label = ACCRUAL_STYLES.get(str(mechanism), ACCRUAL_STYLES["none"])
    return f'<span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset {cls}">{label}</span>'


# ---------------------------------------------------------------------------
# Layout primitives
# ---------------------------------------------------------------------------

NAV = [
    ("valuation", "Valuation"),
    ("supply", "Supply"),
    ("dormancy", "Dormancy"),
    ("incentives", "Incentives"),
    ("methodology", "Methodology"),
]


def page(title: str, active: str, body: str) -> str:
    nav_items = "".join(
        f'<a href="{href}.html" '
        f'class="px-3 py-2 text-sm rounded-md transition '
        f'{"bg-zinc-800 text-white" if href == active else "text-zinc-400 hover:text-white hover:bg-zinc-900"}">'
        f'{label}</a>'
        for href, label in NAV
    )
    return f"""<!doctype html>
<html lang="en" class="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} · Chainlink Peer Valuation</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
    .chart-frame {{ width: 100%; height: 560px; border: 0; background: white; border-radius: 0.5rem; }}
    .link-accent {{ color: {LINK_BLUE}; }}
    .link-row {{ background: linear-gradient(90deg, rgba(37,99,235,0.08), transparent); }}
    .mono {{ font-family: 'SF Mono', Menlo, Consolas, monospace; }}
  </style>
</head>
<body class="bg-zinc-950 text-zinc-200 min-h-screen">
  <nav class="border-b border-zinc-900 bg-zinc-950/80 backdrop-blur sticky top-0 z-10">
    <div class="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
      <a href="index.html" class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full" style="background:{LINK_BLUE}"></span>
        <span class="font-semibold text-white">Chainlink Peer Valuation</span>
      </a>
      <div class="flex items-center gap-1">{nav_items}</div>
    </div>
  </nav>
  <main class="max-w-7xl mx-auto px-4 py-8">
    {body}
  </main>
  <footer class="max-w-7xl mx-auto px-4 py-8 text-xs text-zinc-500 border-t border-zinc-900 mt-12">
    <div class="flex justify-between">
      <span>As of {AS_OF.isoformat()} · Subject: <span class="link-accent font-medium">LINK</span></span>
      <span>Sources: CoinGecko · DeFiLlama · CoinDesk · Dune · Etherscan</span>
    </div>
  </footer>
</body>
</html>"""


def chart(name: str, title: str, caption: str = "") -> str:
    cap = f'<p class="text-xs text-zinc-500 mt-2">{caption}</p>' if caption else ""
    return f"""
    <section class="mb-8">
      <h3 class="text-sm font-semibold text-zinc-300 mb-3">{title}</h3>
      <iframe src="charts/{name}.html" class="chart-frame" loading="lazy"></iframe>
      {cap}
    </section>"""


def card(label: str, value: str, sub: str = "", emphasis: bool = False) -> str:
    val_class = "text-2xl font-semibold" + (f' style="color:{LINK_BLUE}"' if emphasis else ' text-white"')
    # Fix: emphasis path needs class attr too
    if emphasis:
        val_html = f'<div class="text-2xl font-semibold" style="color:{LINK_BLUE}">{value}</div>'
    else:
        val_html = f'<div class="text-2xl font-semibold text-white">{value}</div>'
    sub_html = f'<div class="text-xs text-zinc-500 mt-1">{sub}</div>' if sub else ""
    return f"""
    <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-4">
      <div class="text-xs uppercase tracking-wider text-zinc-500">{label}</div>
      {val_html}
      {sub_html}
    </div>"""


def section_header(title: str, sub: str = "") -> str:
    sub_html = f'<p class="text-sm text-zinc-400 mt-1">{sub}</p>' if sub else ""
    return f"""
    <header class="mb-6 pb-4 border-b border-zinc-900">
      <h1 class="text-2xl font-semibold text-white">{title}</h1>
      {sub_html}
    </header>"""


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------


def build_overview(df: pd.DataFrame) -> str:
    link = df[df["symbol"] == "LINK"].iloc[0]

    cards = f"""
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
      {card("Market Cap", fmt_usd(link["market_cap"]), "Circulating × price", emphasis=True)}
      {card("P / Retained Revenue", fmt_multiple(link["mcap_over_revenue"]), f"Revenue: {fmt_usd(link['annualized_revenue'])}/yr")}
      {card("Net Dilution (annualized)", fmt_pct(link["net_dilution_annualized"], sign=True), "90d forward × 365/90")}
      {card("Rewards-Adj Dilution", fmt_pct(link["rewards_adjusted_dilution"], sign=True), f"Staking yield: {fmt_pct(link['incentive_yield_annualized'])}")}
    </div>"""

    # Peer summary table
    df_sorted = df.sort_values("market_cap", ascending=False).copy()
    rows = []
    for _, r in df_sorted.iterrows():
        is_link = r["symbol"] == "LINK"
        row_cls = "link-row" if is_link else ""
        sym_cls = "font-semibold link-accent" if is_link else "font-medium text-zinc-200"
        rows.append(f"""
        <tr class="{row_cls} border-b border-zinc-900">
          <td class="py-2 pr-4 {sym_cls}">{r['symbol']}</td>
          <td class="py-2 pr-4 text-zinc-400 text-sm">{r['name']}</td>
          <td class="py-2 pr-4 mono text-right">{fmt_usd(r['market_cap'])}</td>
          <td class="py-2 pr-4 mono text-right">{fmt_multiple(r['mcap_over_fees'])}</td>
          <td class="py-2 pr-4 mono text-right">{fmt_multiple(r['mcap_over_revenue'])}</td>
          <td class="py-2 pr-4 mono text-right">{fmt_pct(r['net_dilution_annualized'], sign=True)}</td>
          <td class="py-2 pr-4 mono text-right">{fmt_pct(r['rewards_adjusted_dilution'], sign=True)}</td>
          <td class="py-2">{accrual_chip(r['value_accrual'])}</td>
        </tr>""")

    table = f"""
    <section class="mb-10">
      <h2 class="text-lg font-semibold text-white mb-4">Peer Snapshot</h2>
      <div class="overflow-x-auto rounded-lg border border-zinc-900 bg-zinc-950">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-900">
              <th class="py-3 px-4">Symbol</th>
              <th class="py-3 px-4">Name</th>
              <th class="py-3 px-4 text-right">Market Cap</th>
              <th class="py-3 px-4 text-right">P/F</th>
              <th class="py-3 px-4 text-right">P/RR</th>
              <th class="py-3 px-4 text-right">Net Dilution</th>
              <th class="py-3 px-4 text-right">Rewards-Adj</th>
              <th class="py-3 px-4">Accrual</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>"""

    findings = """
    <section class="mb-10">
      <h2 class="text-lg font-semibold text-white mb-4">Key Findings</h2>
      <div class="grid md:grid-cols-2 gap-4">
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-5">
          <div class="text-xs uppercase tracking-wider text-zinc-500 mb-2">Value Accrual Gap</div>
          <p class="text-sm text-zinc-300 leading-relaxed">LINK has <span class="text-white font-medium">real activity revenue</span> (~$55M/yr from node operators) but no direct token claim. Staking v0.2 rewards (4.35% APR) come from the treasury reserve, not protocol revenue.</p>
        </div>
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-5">
          <div class="text-xs uppercase tracking-wider text-zinc-500 mb-2">Headline Supply Pressure</div>
          <p class="text-sm text-zinc-300 leading-relaxed">OP leads with <span class="text-white font-medium">+17.8% annualized dilution</span> from three monthly cliffs (94M OP / 4.4% of circ). LINK's 7.5% comes from discretionary treasury releases — no on-chain vesting contract.</p>
        </div>
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-5">
          <div class="text-xs uppercase tracking-wider text-zinc-500 mb-2">Reserve Buyback</div>
          <p class="text-sm text-zinc-300 leading-relaxed">Chainlink Reserve (Aug 2025) converts non-LINK fees into LINK weekly — <span class="text-white font-medium">130K LINK/wk run-rate</span> (~$62M/yr). PA v2 in audit (Mar 2026) will route all enterprise fees.</p>
        </div>
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-5">
          <div class="text-xs uppercase tracking-wider text-zinc-500 mb-2">Net of Staking Yield</div>
          <p class="text-sm text-zinc-300 leading-relaxed">For active holders (staking enabled), LINK rewards-adjusted dilution is <span class="text-white font-medium">+3.16%</span>, between AAVE (−2.6%, deflationary via buyback) and CRV (+0.5%, near-neutral via fee share).</p>
        </div>
      </div>
    </section>"""

    body = section_header(
        "Chainlink Peer Valuation Framework",
        "Standardized Web3 token metrics across 8 peers. Subject: LINK.",
    ) + cards + findings + table
    return page("Overview", "index", body)


def build_valuation(df: pd.DataFrame) -> str:
    df_sorted = df.sort_values("market_cap", ascending=False).copy()
    rows = []
    for _, r in df_sorted.iterrows():
        is_link = r["symbol"] == "LINK"
        row_cls = "link-row" if is_link else ""
        sym_cls = "font-semibold link-accent" if is_link else "text-zinc-200"
        fdv = fmt_usd(r["fdv"]) if not r.get("uncapped") else '<span class="text-zinc-500">Uncapped</span>'
        fdv_mc = fmt_multiple(r["fdv_mc_ratio"]) if not r.get("uncapped") else '<span class="text-zinc-500">—</span>'
        rows.append(f"""
        <tr class="{row_cls} border-b border-zinc-900">
          <td class="py-2 px-4 {sym_cls}">{r['symbol']}</td>
          <td class="py-2 px-4 mono text-right">{fmt_usd(r['market_cap'])}</td>
          <td class="py-2 px-4 mono text-right">{fdv}</td>
          <td class="py-2 px-4 mono text-right">{fdv_mc}</td>
          <td class="py-2 px-4 mono text-right">{fmt_usd(r['annualized_fees'])}</td>
          <td class="py-2 px-4 mono text-right">{fmt_multiple(r['mcap_over_fees'])}</td>
          <td class="py-2 px-4 mono text-right">{fmt_usd(r['annualized_revenue'])}</td>
          <td class="py-2 px-4 mono text-right">{fmt_multiple(r['mcap_over_revenue'])}</td>
          <td class="py-2 px-4">{accrual_chip(r['value_accrual'])}</td>
        </tr>""")

    table = f"""
    <section class="mb-10">
      <h2 class="text-lg font-semibold text-white mb-4">Valuation Multiples</h2>
      <div class="overflow-x-auto rounded-lg border border-zinc-900 bg-zinc-950">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-900">
              <th class="py-3 px-4">Symbol</th>
              <th class="py-3 px-4 text-right">Market Cap</th>
              <th class="py-3 px-4 text-right">FDV</th>
              <th class="py-3 px-4 text-right">FDV/MC</th>
              <th class="py-3 px-4 text-right">Fees (ann)</th>
              <th class="py-3 px-4 text-right">P/F</th>
              <th class="py-3 px-4 text-right">Revenue (ann)</th>
              <th class="py-3 px-4 text-right">P/RR</th>
              <th class="py-3 px-4">Accrual</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
      <p class="text-xs text-zinc-500 mt-3">ETH & SOL have no hard max supply — FDV reported as Uncapped. DeFiLlama <span class="mono">dailyRevenue</span> reported as-is for LINK/UNI; value accrual is a separate question.</p>
    </section>"""

    body = section_header(
        "Valuation & Fees",
        "Market cap, FDV, and price-to-fees / price-to-retained-revenue multiples.",
    ) + table + chart(
        "valuation_p_f",
        "Market Cap / Total Fees (P/F)",
        "User-paid fees — covers operators, LPs, treasury.",
    ) + chart(
        "valuation_p_rf",
        "Market Cap / Retained Revenue (P/RR)",
        "DeFiLlama dailyRevenue × 365. Lower = cheaper relative to retained protocol revenue.",
    ) + chart(
        "fees_snapshot",
        "Annualized Fees & Revenue Snapshot",
    ) + chart(
        "fees_90d_trend",
        "90-Day Fee Trend",
        "Relative momentum vs. the snapshot figures above.",
    )
    return page("Valuation", "valuation", body)


def build_supply(df: pd.DataFrame) -> str:
    df_sorted = df.sort_values("net_dilution_annualized", ascending=False).copy()
    rows = []
    for _, r in df_sorted.iterrows():
        is_link = r["symbol"] == "LINK"
        row_cls = "link-row" if is_link else ""
        sym_cls = "font-semibold link-accent" if is_link else "text-zinc-200"
        rows.append(f"""
        <tr class="{row_cls} border-b border-zinc-900">
          <td class="py-2 px-4 {sym_cls}">{r['symbol']}</td>
          <td class="py-2 px-4 mono text-right">{fmt_pct(r['gross_inflation_annualized'], sign=True)}</td>
          <td class="py-2 px-4 mono text-right">{fmt_pct(r['burn_rate_annualized'])}</td>
          <td class="py-2 px-4 mono text-right">{fmt_pct(r['net_inflation_annualized'], sign=True)}</td>
          <td class="py-2 px-4 mono text-right">{fmt_usd(r['buyback_burn_usd_annualized'])}</td>
          <td class="py-2 px-4 mono text-right">{fmt_pct(r['net_dilution_annualized'], sign=True)}</td>
          <td class="py-2 px-4 mono text-right">{fmt_pct(r['rewards_adjusted_dilution'], sign=True)}</td>
        </tr>""")

    table = f"""
    <section class="mb-10">
      <h2 class="text-lg font-semibold text-white mb-4">Supply Dynamics</h2>
      <div class="overflow-x-auto rounded-lg border border-zinc-900 bg-zinc-950">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-900">
              <th class="py-3 px-4">Symbol</th>
              <th class="py-3 px-4 text-right">Gross Inflation</th>
              <th class="py-3 px-4 text-right">Burn Rate</th>
              <th class="py-3 px-4 text-right">Net Inflation</th>
              <th class="py-3 px-4 text-right">Buyback/Burn ($/yr)</th>
              <th class="py-3 px-4 text-right">Net Dilution (ann)</th>
              <th class="py-3 px-4 text-right">Rewards-Adj</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
      <p class="text-xs text-zinc-500 mt-3">Net dilution = 90d forward supply panel (inflation + unlocks − buybacks) annualized by ×365/90. Rewards-adjusted subtracts the incentive capture yield available to active holders.</p>
    </section>"""

    body = section_header(
        "Supply Dynamics",
        "Inflation, unlocks, and buyback offsets on a forward-looking 90-day basis.",
    ) + table + chart(
        "forward_supply_total",
        "90-Day Forward Supply — Gross",
        "Cumulative new supply entering circulation (inflation + unlock events) as % of current circ.",
    ) + chart(
        "forward_supply_net",
        "90-Day Forward Supply — Net of Buybacks",
        "Gross dilution minus buyback/burn offsets (ETH EIP-1559, SOL base fee, AAVE TWAP, LINK Reserve, UNI Firepit).",
    ) + chart(
        "supply_inflation",
        "Gross Issuance, Burn, and Net Inflation",
        "Gross issuance (faint) with burn offset (orange, negative) and net inflation (solid). UNI shows negative net due to Firepit burn exceeding zero gross issuance. CRV rate updated to 5.02% post-reduction (source: MetaMask, next cut Aug 2026).",
    )
    return page("Supply", "supply", body)


def build_dormancy(df: pd.DataFrame) -> str:
    body = section_header(
        "Dormancy",
        "Share of circulating supply held by addresses with no qualifying activity in the last 180 days.",
    ) + chart(
        "dormancy_180d",
        "180-Day Dormant Supply %",
        "EVM: outbound-transfer signal (dust-attack resistant). SOL: balance-row updates. ETH: native-balance reconstruction via Dune Q7332769.",
    ) + """
    <section class="rounded-lg border border-zinc-900 bg-zinc-950 p-5 mt-6">
      <h3 class="text-sm font-semibold text-white mb-3">Why the signal differs by chain</h3>
      <ul class="text-sm text-zinc-400 space-y-2 leading-relaxed list-disc pl-5">
        <li><span class="text-zinc-200 font-medium">EVM (LINK / AAVE / UNI / LDO / CRV / OP):</span> active = addresses that have <em>sent</em> the token in 180d. Balance-update signal is vulnerable to dust attacks — an observed spammer touched every UNI holder.</li>
        <li><span class="text-zinc-200 font-medium">Solana:</span> balance-row updates are acceptable. Rent-exempt minimums make spamming 500M+ accounts cost ~$440K+.</li>
        <li><span class="text-zinc-200 font-medium">Ethereum (native):</span> no curated Dune balance table; Q7332769 reconstructs native-ETH balance from genesis + withdrawals + tx/trace flows − gas. ~29.7% dormant tracks the CoinDesk staked proxy (31.3%).</li>
      </ul>
    </section>"""
    return page("Dormancy", "dormancy", body)


def build_incentives(df: pd.DataFrame) -> str:
    df_sorted = df.sort_values("incentive_yield_annualized", ascending=False, na_position="last").copy()
    rows = []
    for _, r in df_sorted.iterrows():
        is_link = r["symbol"] == "LINK"
        row_cls = "link-row" if is_link else ""
        sym_cls = "font-semibold link-accent" if is_link else "text-zinc-200"
        mech = r.get("incentive_yield_mechanism") if pd.notna(r.get("incentive_yield_mechanism")) else "—"
        rows.append(f"""
        <tr class="{row_cls} border-b border-zinc-900">
          <td class="py-2 px-4 {sym_cls}">{r['symbol']}</td>
          <td class="py-2 px-4 mono text-right">{fmt_pct(r['incentive_yield_annualized'])}</td>
          <td class="py-2 px-4 text-xs text-zinc-400">{mech}</td>
          <td class="py-2 px-4 mono text-right">{fmt_pct(r['net_dilution_annualized'], sign=True)}</td>
          <td class="py-2 px-4 mono text-right">{fmt_pct(r['rewards_adjusted_dilution'], sign=True)}</td>
        </tr>""")

    table = f"""
    <section class="mb-10">
      <h2 class="text-lg font-semibold text-white mb-4">Incentive Capture Yield</h2>
      <div class="overflow-x-auto rounded-lg border border-zinc-900 bg-zinc-950">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-900">
              <th class="py-3 px-4">Symbol</th>
              <th class="py-3 px-4 text-right">Yield (ann)</th>
              <th class="py-3 px-4">Mechanism</th>
              <th class="py-3 px-4 text-right">Net Dilution</th>
              <th class="py-3 px-4 text-right">Rewards-Adj</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
      <p class="text-xs text-zinc-500 mt-3">AAVE shows negative dilution because the buyback (~$43M/yr) exceeds any emission. LDO has no active incentive channel. UNI has no yield (fee switch inactive).</p>
    </section>"""

    body = section_header(
        "Incentives",
        "Yield available to active holders through the token's value-accrual mechanism, and its offset against dilution.",
    ) + table + chart(
        "incentive_capture_yield",
        "Incentive Capture Yield by Peer",
    ) + chart(
        "rewards_adjusted_dilution",
        "Rewards-Adjusted Dilution",
        "Negative bars = active holders are net positive (yield > dilution). Positive = even active holders are diluted on net.",
    )
    return page("Incentives", "incentives", body)


def build_methodology() -> str:
    body = section_header(
        "Methodology",
        "Metric definitions, data sources, and the rationale for dropped metrics.",
    ) + """
    <section class="mb-10">
      <h2 class="text-lg font-semibold text-white mb-4">Data Sources</h2>
      <div class="grid md:grid-cols-2 gap-4">
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-4">
          <div class="text-sm font-medium text-white mb-1">CoinGecko</div>
          <p class="text-xs text-zinc-400">Price, market cap, FDV, circulating & total supply, 365d price series.</p>
        </div>
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-4">
          <div class="text-sm font-medium text-white mb-1">DeFiLlama</div>
          <p class="text-xs text-zinc-400">Protocol fees, revenue, TVL. Free tier. <span class="mono">dailyRevenue</span> used as-is for all peers.</p>
        </div>
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-4">
          <div class="text-sm font-medium text-white mb-1">CoinDesk</div>
          <p class="text-xs text-zinc-400">Historical supply breakdown — issued, burned, staked, locked. Primary source for inflation & illiquid share.</p>
        </div>
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-4">
          <div class="text-sm font-medium text-white mb-1">Dune Analytics</div>
          <p class="text-xs text-zinc-400">On-chain SQL for SOL burn, AAVE buyback, UNI Firepit, 180d dormancy, LINK treasury outflow. 2,500 q/mo budget.</p>
        </div>
      </div>
    </section>

    <section class="mb-10">
      <h2 class="text-lg font-semibold text-white mb-4">Canonical Metrics</h2>
      <div class="rounded-lg border border-zinc-900 bg-zinc-950 divide-y divide-zinc-900">
        <div class="p-4">
          <div class="text-sm font-medium text-white">Market Cap, FDV, FDV/MC</div>
          <p class="text-xs text-zinc-400 mt-1">Circ × price; max × price; supply overhang ratio. Uncapped tokens (ETH/SOL) report FDV as N/A.</p>
        </div>
        <div class="p-4">
          <div class="text-sm font-medium text-white">Annualized Fees, P/F, Retained Revenue, P/RR</div>
          <p class="text-xs text-zinc-400 mt-1">30-day trailing × 12. Retained revenue is DeFiLlama <span class="mono">dailyRevenue</span> accepted as-is — whether the token claims that revenue is captured separately by Value Accrual Mechanism.</p>
        </div>
        <div class="p-4">
          <div class="text-sm font-medium text-white">90d At-Risk Unlocks</div>
          <p class="text-xs text-zinc-400 mt-1">Forward token supply entering circulation over 90d — team/investor/ecosystem cliffs + scheduled emissions. Sourced from <span class="mono">unlocks.yaml</span> (manual, per-peer).</p>
        </div>
        <div class="p-4">
          <div class="text-sm font-medium text-white">Burns + Buybacks</div>
          <p class="text-xs text-zinc-400 mt-1">Annualized USD destroyed/repurchased. ETH (EIP-1559), SOL (base fee), AAVE (TWAP, 30d rate), LINK (Reserve dutch auction), UNI (Firepit).</p>
        </div>
        <div class="p-4">
          <div class="text-sm font-medium text-white">Net Dilution & Rewards-Adjusted Dilution</div>
          <p class="text-xs text-zinc-400 mt-1">Net = gross forward supply − buybacks, annualized via day-90 × 365/90. Rewards-adjusted subtracts the yield available to active stakers.</p>
        </div>
        <div class="p-4">
          <div class="text-sm font-medium text-white">180d Dormant Supply %</div>
          <p class="text-xs text-zinc-400 mt-1">Share of circ held by addresses with no qualifying activity in 180d. EVM uses outbound-transfer signal; SOL uses balance updates; ETH uses native-balance reconstruction.</p>
        </div>
        <div class="p-4">
          <div class="text-sm font-medium text-white">Incentive Capture Yield</div>
          <p class="text-xs text-zinc-400 mt-1">Yield an active holder captures through the token's accrual mechanism — validator rewards, staking APR, buyback-and-distribute, or veCRV fee share. Mechanism and yield per peer in <span class="mono">incentive_yield.yaml</span>.</p>
        </div>
      </div>
    </section>

    <section class="mb-10">
      <h2 class="text-lg font-semibold text-white mb-4">Dropped Metrics</h2>
      <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-4">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-900 text-left">
              <th class="py-2 pr-4">Metric</th>
              <th class="py-2">Reason</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-900">
            <tr><td class="py-2 pr-4 text-zinc-300">Circulating Supply %</td><td class="py-2 text-xs text-zinc-400">Information already in FDV/MC.</td></tr>
            <tr><td class="py-2 pr-4 text-zinc-300">Forward Revenue Forecasts</td><td class="py-2 text-xs text-zinc-400">Narrative model, not a comparable.</td></tr>
            <tr><td class="py-2 pr-4 text-zinc-300">Gross/Net Inflation standalone</td><td class="py-2 text-xs text-zinc-400">Folded into 90d At-Risk Unlocks.</td></tr>
            <tr><td class="py-2 pr-4 text-zinc-300">Exchange Balance, Flow</td><td class="py-2 text-xs text-zinc-400">CEX attribution inconsistent across peer set at free tier.</td></tr>
            <tr><td class="py-2 pr-4 text-zinc-300">Top 10/100 Holder Concentration</td><td class="py-2 text-xs text-zinc-400">Etherscan Pro required; no comparable SOL equivalent.</td></tr>
            <tr><td class="py-2 pr-4 text-zinc-300">Supply Velocity</td><td class="py-2 text-xs text-zinc-400">30d volume is wash-trade contaminated.</td></tr>
            <tr><td class="py-2 pr-4 text-zinc-300">Real Yield, Staking Penetration</td><td class="py-2 text-xs text-zinc-400">CoinDesk coverage gaps; footnote-level.</td></tr>
            <tr><td class="py-2 pr-4 text-zinc-300">Economic Earnings, P/E</td><td class="py-2 text-xs text-zinc-400">Double-count issues on ETH/SOL validator rewards.</td></tr>
            <tr><td class="py-2 pr-4 text-zinc-300">Token Incentive Expense</td><td class="py-2 text-xs text-zinc-400">Superseded by Incentive Capture Yield.</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="mb-10">
      <h2 class="text-lg font-semibold text-white mb-4">Methodology Footnotes</h2>
      <div class="space-y-3 text-sm text-zinc-400">
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-4">
          <div class="text-zinc-200 font-medium mb-1">LINK net dilution breakdown</div>
          <p>7.5% annualized = 90-day forward × 4.056. At day 90: 15M treasury unlock = +2.06% (discretionary, no on-chain vesting); Reserve buyback = −0.21% (12 weekly events × 0.0176%). Staking v0.2 yield (4.35%) brings rewards-adjusted to +3.16%.</p>
        </div>
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-4">
          <div class="text-zinc-200 font-medium mb-1">ETH issuance uses beacon-chain formula</div>
          <p>CoinDesk <span class="mono">issued</span> field reconstructs from circulating supply and undercounts validator rewards ~30×. We override with <span class="mono">166.3 × sqrt(total_staked_ETH)</span>, matching ethereum.org's cited 1,700 ETH/day at 14M staked. 30-day burn window avoids Dencun artefact.</p>
        </div>
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-4">
          <div class="text-zinc-200 font-medium mb-1">AAVE buyback is front-loaded</div>
          <p>365d figure ($453M) implies ~$37.7M/month but trailing 30d is only $3.6M. Buybacks concentrated post-AIP-434 launch (Apr 2025). Use 30d as near-term signal.</p>
        </div>
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-4">
          <div class="text-zinc-200 font-medium mb-1">OP locked &gt; 100% of circ</div>
          <p>CoinDesk's <span class="mono">locked</span> denominator for pre-minted-supply tokens includes treasury, so it exceeds circulating supply. Documented, not "fixed."</p>
        </div>
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-4">
          <div class="text-zinc-200 font-medium mb-1">FDV for uncapped tokens</div>
          <p>ETH/SOL have no hard max supply. CoinGecko silently sets FDV = MC, reading as "no dilution risk" — the opposite of truth. We render them as Uncapped and omit FDV/MC.</p>
        </div>
        <div class="rounded-lg border border-zinc-900 bg-zinc-950 p-4">
          <div class="text-zinc-200 font-medium mb-1">LINK / UNI retained revenue</div>
          <p>DeFiLlama <span class="mono">dailyRevenue</span> reported as-is (LINK ~$55.5M/yr, UNI ~$41.4M/yr). Not zeroed out — revenue is real activity. The Value Accrual Mechanism column (staking for LINK, none for UNI) carries the "token doesn't claim this" story.</p>
        </div>
      </div>
    </section>"""
    return page("Methodology", "methodology", body)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if OUT_CHARTS.exists():
        shutil.rmtree(OUT_CHARTS)
    OUT_CHARTS.mkdir()

    df = pd.read_csv(METRICS)

    # Render pages
    redirect = '<!doctype html><html><head><meta charset="utf-8"/><meta http-equiv="refresh" content="0; url=valuation.html"/></head><body></body></html>'
    pages = {
        "index.html": redirect,
        "valuation.html": build_valuation(df),
        "supply.html": build_supply(df),
        "dormancy.html": build_dormancy(df),
        "incentives.html": build_incentives(df),
        "methodology.html": build_methodology(),
    }
    for name, html in pages.items():
        (OUT / name).write_text(html)

    # Copy only the charts referenced by dashboard pages
    USED_CHARTS = {
        "valuation_p_f.html", "valuation_p_rf.html",
        "fees_snapshot.html", "fees_90d_trend.html",
        "forward_supply_total.html", "forward_supply_net.html",
        "supply_inflation.html", "dormancy_180d.html",
        "incentive_capture_yield.html", "rewards_adjusted_dilution.html",
    }
    for src in CHARTS_SRC.glob("*.html"):
        name = src.name.replace(" ", "_")
        if name in USED_CHARTS:
            shutil.copy(src, OUT_CHARTS / name)

    # Vercel zero-config static hosting
    vercel_cfg = '{\n  "cleanUrls": true\n}\n'
    (OUT / "vercel.json").write_text(vercel_cfg)

    print(f"Built {len(pages)} pages + {len(list(CHARTS_SRC.glob('*.html')))} charts → {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
