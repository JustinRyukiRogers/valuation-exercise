"""Generate notebooks/01_ingest.ipynb from Python source.

We build notebooks programmatically so code is authored in real .py files
(linted, typed, diffable) and the .ipynb is a disposable artifact.
"""
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks" / "01_ingest.ipynb"

nb = nbf.v4.new_notebook()
cells = []

cells.append(nbf.v4.new_markdown_cell("""# 01 — Ingest

Fetch raw data from Tier-1 sources for every peer in `peer_set.yaml`.

Sources used in this notebook (no paid keys required):
- **DeFiLlama** — protocol fees, revenue, TVL
- **CoinGecko** — price, market cap, FDV, circulating/total/max supply, historical market_chart

A Demo CoinGecko API key (free) is recommended for better rate limits but not required."""))

cells.append(nbf.v4.new_code_cell("""# --- setup ---
import sys
from pathlib import Path

# Add project root so `src.*` imports resolve when running from notebooks/
ROOT = Path().resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from tqdm.auto import tqdm

from src.config import load_peers, coingecko_key, RAW_DIR
from src.sources import defillama, coingecko

peers = load_peers()

print(f"Loaded {len(peers)} peers:")
for p in peers:
    print(f"  {p.symbol:6s} {p.name:20s} [{p.category}]")

print()
print(f"CoinGecko API key: {'SET' if coingecko_key() else 'NOT SET (rate-limited public tier)'}")"""))

cells.append(nbf.v4.new_markdown_cell("""## Smoke test — single protocol

Verify both sources work end-to-end against Chainlink before hitting the full peer set."""))

cells.append(nbf.v4.new_code_cell("""peer = peers[0]  # LINK
print(f"Testing sources for {peer.symbol} ({peer.coingecko_id} / {peer.defillama_slug})")
print()

print("CoinGecko snapshot:")
snap = coingecko.get_market_snapshot(peer.coingecko_id)
for k, v in snap.items():
    print(f"  {k:25s} {v}")

print()
print("DeFiLlama summary:")
summary = defillama.get_protocol_summary(peer.defillama_slug)
for k, v in summary.items():
    print(f"  {k:25s} {v}")"""))

cells.append(nbf.v4.new_markdown_cell("""## Fetch: full peer set

For each peer pull CoinGecko snapshot + DeFiLlama summary. Gracefully skip sources that fail so one missing slug doesn't break the run."""))

cells.append(nbf.v4.new_code_cell("""records = []
for peer in tqdm(peers, desc="Fetching peers"):
    row = {
        "symbol": peer.symbol,
        "name": peer.name,
        "category": peer.category,
        "type": peer.type,
        "value_accrual": peer.value_accrual,
    }

    try:
        snap = coingecko.get_market_snapshot(peer.coingecko_id)
        row.update(snap)
    except Exception as e:
        print(f"  [warn] CoinGecko failed for {peer.symbol}: {e}")

    if peer.defillama_slug:
        # The DeFiLlama helper now handles both protocols and chains: chain TVL
        # falls back to /chains when /protocol/{slug} has no tvl series, and
        # /summary/fees/{slug} works for both endpoint types.
        try:
            summary = defillama.get_protocol_summary(peer.defillama_slug)
            row.update({k: v for k, v in summary.items() if k != "name"})
        except Exception as e:
            print(f"  [warn] DeFiLlama failed for {peer.symbol}: {e}")

    records.append(row)

df = pd.DataFrame(records)
print(f"\\nFetched {len(df)} rows")
df.head(12)"""))

cells.append(nbf.v4.new_markdown_cell("""## Derive headline valuation multiples

These are the "Tier 1" metrics — everything computable from the snapshot data we just pulled. Richer metrics (inflation, dormancy, incentive expense) come in `02_metrics.ipynb`."""))

cells.append(nbf.v4.new_code_cell("""# Uncapped tokens (ETH, SOL) have no hard max supply. CoinGecko defaults FDV
# to market cap in that case, which silently tells the reader "no dilution
# risk" — the opposite of the truth. Null the FDV-derived fields for those
# peers and let the dashboard render an explicit "Uncapped" label.
import numpy as np

uncapped_symbols = {p.symbol for p in peers if p.uncapped}
df.loc[df["symbol"].isin(uncapped_symbols), "fdv"] = np.nan

df["fdv_mc_ratio"] = df["fdv"] / df["market_cap"]
df["annualized_fees"] = df["fees_30d"] * 12
df["annualized_revenue"] = df["revenue_30d"] * 12
df["mcap_over_fees"] = df["market_cap"] / df["annualized_fees"]
df["mcap_over_revenue"] = df["market_cap"] / df["annualized_revenue"]
df["fdv_over_revenue"] = df["fdv"] / df["annualized_revenue"]

# Carry the uncapped flag into the snapshot so downstream consumers (charts,
# dashboard) can render "Uncapped" without re-joining against peer_set.yaml.
df["uncapped"] = df["symbol"].isin(uncapped_symbols)

display_cols = [
    "symbol", "category", "market_cap", "fdv", "fdv_mc_ratio", "uncapped",
    "tvl_current", "annualized_fees", "annualized_revenue",
    "mcap_over_fees", "mcap_over_revenue", "fdv_over_revenue",
]
df[display_cols].sort_values("market_cap", ascending=False)"""))

cells.append(nbf.v4.new_markdown_cell("""## Historical supply — demonstrate the inflation derivation

CoinGecko's free `/market_chart` endpoint gives us price and market cap over time.
Dividing them gives us **implied circulating supply**, which is exactly what we need
to compute gross inflation over any window."""))

cells.append(nbf.v4.new_code_cell("""from src.sources.coingecko import get_market_chart_df, compute_inflation

link_chart = get_market_chart_df("chainlink", days=365)
print(link_chart.head())
print(link_chart.tail())

inflation = compute_inflation("chainlink", window_days=365)
print("\\nChainlink gross inflation (last 365d):")
for k, v in inflation.items():
    print(f"  {k:25s} {v}")"""))

cells.append(nbf.v4.new_markdown_cell("""## Save raw data"""))

cells.append(nbf.v4.new_code_cell("""out_path = RAW_DIR / "peer_snapshot.csv"
df.to_csv(out_path, index=False)
print(f"Wrote {out_path}  ({len(df)} rows, {len(df.columns)} cols)")"""))

cells.append(nbf.v4.new_markdown_cell("""## Next

- `02_metrics.ipynb` — compute the full uniform metric set (inflation, dormancy proxies, concentration)
- Wire in Dune queries for flagship on-chain metrics (dormancy, burns, buybacks)
- `03_charts.ipynb` — Plotly visualizations for the deck and dashboard"""))

nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    },
    "language_info": {"name": "python"},
}

OUT.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, OUT)
print(f"Wrote {OUT}")
