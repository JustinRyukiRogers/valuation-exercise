# Chainlink Take-Home: Web3 Valuation Dashboard

A cross-project valuation framework for Web3 tokens. See [PLAN.md](PLAN.md) for full methodology.

## Quick Start

```bash
# 1. Create virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Set up API keys (see .env.example for signup links)
cp .env.example .env
# then edit .env and fill in keys

# 3. Register the notebook kernel
python -m ipykernel install --user --name=chainlink-valuation --display-name "Chainlink Valuation"

# 4. Launch Jupyter
jupyter notebook notebooks/
```

## Project Structure

```
.
├── PLAN.md                       # Methodology and metric definitions
├── peer_set.yaml                 # Flexible peer-set config (edit to add/remove tokens)
├── .env.example / .env           # API key placeholders
├── requirements.txt
├── src/
│   ├── config.py                 # Loads env + peer_set.yaml
│   ├── cache.py                  # On-disk cache for API responses
│   ├── sources/                  # Data source clients
│   │   ├── defillama.py          # TVL, fees, revenue (no key)
│   │   ├── coingecko.py          # Price, MC, FDV, supply, historical
│   │   ├── coindesk.py           # Historical supply with breakdown (future)
│   │   ├── dune.py               # On-chain metrics, flagship deep-dives (future)
│   │   └── etherscan.py          # Holder concentration (future)
│   └── metrics/                  # Metric computation (future)
├── notebooks/
│   ├── 01_ingest.ipynb           # Fetch raw data from all sources
│   ├── 02_metrics.ipynb          # Compute uniform metrics per project (future)
│   ├── 03_charts.ipynb           # Plotly visualizations (future)
│   └── 04_analysis.ipynb         # Commentary and key findings (future)
└── data/
    ├── raw/                      # Normalized ingested data per source
    ├── metrics/                  # Computed metrics tables
    └── charts/                   # Exported chart HTMLs
```

## API Key Requirements

The pipeline is tiered — you can run it with only a subset of keys:

| Tier | Keys Needed | What You Get |
|---|---|---|
| **Tier 1** | CoinGecko Demo only | Valuation, fees, revenue, TVL, derived inflation |
| **Tier 2** | + CoinDesk | Net inflation, burns, staking %, locked %, future supply |
| **Tier 3** | + Etherscan | Top-holder concentration |
| **Tier 4** | + Dune | True age-based dormancy + flagship project-specific events (e.g. SKY Smart Burn Engine) |

Sign up links are in [.env.example](.env.example). All four are free tiers.

## Development

The peer set in [peer_set.yaml](peer_set.yaml) is intentionally flexible — add, remove, or reorder projects without touching code. The pipeline iterates this config at runtime.
