# Chainlink Take-Home: Project Valuation Dashboard — Implementation Plan

## Overview

**Objective:** Build a defensible, standardized valuation framework for Web3 tokens that enables Chainlink Labs to reason about how comparable projects are valued and what that implies for LINK's own economic positioning.

**Deliverables:**
1. A **document** describing the dashboard — data sources, pipeline, metrics, assumptions, layout, and conclusions
2. A **Jupyter Notebook** for data ingestion, metric calculation, and chart generation
3. A **hosted Vercel dashboard** (Next.js, free tier) with auto-refreshing data
4. A **presentation** walking through the doc and dashboard (10 min + 20 min Q&A)

---

## Peer Group

The Chainlink team confirmed: no required token set, and generalized metrics are preferred over sector-specific ones given data availability constraints (robust data exists primarily for L1s at a sector level, but we can achieve good coverage for the projects below individually).

**Selected Peer Group (8 tokens):**

| Token | Project | Category | Rationale |
|---|---|---|---|
| ETH | Ethereum | L1 Blockchain | Largest L1; cleanest fee/revenue data |
| SOL | Solana | L1 Blockchain | High-throughput L1 competitor |
| OP | Optimism | L2 | Emerging L2 with OP token incentive model |
| LINK | Chainlink | Oracle / Infrastructure | Subject |
| AAVE | Aave | Lending Protocol | Largest lending protocol; strong revenue data |
| UNI | Uniswap | DEX | Largest DEX; high fee volume |
| CRV | Curve | DEX / Stablecoin | Unique tokenomics (ve-model); good for incentive analysis |
| LDO | Lido | Liquid Staking | High revenue, high token incentive costs |

**Why this mix:** Provides enough breadth to benchmark LINK across infrastructure, DeFi, and L1 peers while keeping the comp set defensible. The grouping also lets us highlight where LINK's value accrual mechanism diverges from peers.

---

## Metric Framework

Metrics are deliberately narrowed to the ones that survive a critical review across the full peer set. If a metric is weak on more than one or two peers (proxy data, wash-trade contamination, definitional ambiguity), it is dropped rather than footnoted — otherwise it adds more noise than signal when LINK is compared against the group.

### 1. Valuation & Supply

| Metric | Definition | Notes |
|---|---|---|
| Market Cap | Circulating supply × price | Spot valuation |
| Fully Diluted Valuation (FDV) | Max supply × price | Tokens with no hard cap (ETH, SOL) are labelled **Uncapped** — FDV is reported as N/A, and FDV/MC is not computed. Do not silently equate FDV to MC for uncapped tokens. |
| FDV / Market Cap | Supply overhang ratio | Capped-supply tokens only. Flags dilution risk from future emissions. |

### 2. Revenue & Fees

The key asymmetry here is separating *total ecosystem fees* (paid by users) from *protocol-retained revenue* (kept by the treasury or distributed to token holders). Both are reported as-is from DeFiLlama — no per-project override, including for LINK and UNI. The token's claim on that revenue is a separate question captured by **Value Accrual Mechanism**.

| Metric | Definition | Notes |
|---|---|---|
| Annualized Total Fees | 30d fees × 12 | User-paid fees — covers operators, LPs, treasury |
| Market Cap / Total Fees (P/F) | MC / Annualized Fees | Price-to-fees multiple |
| Retained Revenue | 30d protocol revenue × 12 | DeFiLlama `dailyRevenue`, accepted as-is for every peer |
| Market Cap / Retained Revenue (P/RR) | MC / Annualized Retained Revenue | Price-to-retained-revenue multiple |
| Value Accrual Mechanism | Categorical: Burn / Buyback / Staking Yield / Fee Share / None | Qualitative. This is what turns retained revenue into a claim on the token (or doesn't). |

### 3. Supply Dynamics

One consolidated forward-looking supply-pressure metric plus the realized offset. Gross inflation, net inflation, effective dilution, and reserve buybacks are **folded into** these two rows rather than reported separately — they were either double-counting the same emission stream or producing negative/zero values that added no signal.

| Metric | Definition | Notes / Source |
|---|---|---|
| 90d At-Risk Unlocks | Forward 90d token supply entering circulation that can plausibly be sold: team/investor/ecosystem unlocks + scheduled emissions + treasury outflow rate, net of emissions returning directly to locked staking. Reported as both absolute tokens and % of circulating supply. | Manual `unlocks.yaml` per peer, sourced from tokenomics docs, Token Unlocks, governance forum posts, and on-chain vesting contract reads. **Replaces** gross inflation, net inflation, effective dilution, and standalone treasury-outflow metrics — all of them feed into this row. |
| Burns + Buybacks | Annualized value destroyed or repurchased by the protocol | ETH: CoinDesk burn series. SOL: Dune Q1 base-fee burn (`sol_burn_rate_annualized_base_fee`). AAVE: Dune Q3 TWAP executor spend (use 30d rate, not 365d — buybacks are front-loaded post AIP-434). Other peers: N/A. |

### 4. Dormancy

One dormancy window, consistent signal per chain family.

| Metric | Definition | Data Source |
|---|---|---|
| 180d Dormant Supply % | 1 − (supply held by addresses with qualifying activity in the last 180d) / circ supply | **EVM (LINK/AAVE/UNI/LDO/CRV/OP):** Dune — outbound transfer signal via `tokens.transfers` / `tokens_optimism.transfers` (dust-attack resistant). **Solana:** Dune — `block_time` on latest-balance snapshot (rent requirements make dust attacks economically unviable, ~$440K+ to spam 500M+ accounts). **ETH:** dedicated Dune query against mainnet balance/transfer tables — **replaces** the CoinDesk staked-supply proxy used in the prior iteration. |

### 5. Incentives

| Metric | Definition | Notes |
|---|---|---|
| Token Incentive Expense | Annualized token emissions routed to incentives (liquidity mining, staking rewards paid in new supply), valued in USD at spot | Treated as operating expense (stock-based-comp analogue). For peers where gross inflation is effectively zero (ETH post-merge, UNI, LDO, AAVE, OP pre-unlock), the figure is $0 — that is itself the finding. CRV and SOL are the active cases. |

---

### Metrics removed from the prior iteration

These were in the earlier plan but are dropped because the data is too weak, too proxy-heavy, or too redundant to stand up next to LINK in a side-by-side comparison:

| Removed metric | Reason |
|---|---|
| Circulating Supply % | Information content already in FDV/MC |
| Forward Revenue Forecasts | Out of scope for the metrics layer; would be a narrative model, not a comparable |
| Gross Inflation, Net Inflation, Effective Dilution (standalone) | Folded into **90d At-Risk Unlocks** — reporting them separately double-counts the same emission stream |
| Net Idle System Sell Pressure | Same — subsumed by 90d At-Risk Unlocks + Burns/Buybacks |
| 1yr+ Dormancy, 6-month Dormancy | One 180d window is sufficient; two windows produce near-identical ordering |
| Exchange Balance, Exchange Balance % Circ, 30d Exchange Flow | CEX attribution is probabilistic and coverage is inconsistent across the 8 peers. Dune `cex.addresses` is Ethereum-biased; no comparable Solana/OP list at free-tier quality. |
| Top 10 / Top 100 Holder Concentration | Etherscan Pro tier required for mainnet; no comparable Solana equivalent |
| Supply Velocity | 30d trading volume is wash-trade contaminated, especially for mid-caps. Adds more noise than signal. |
| Reserve Buybacks (standalone) | Folded into Burns + Buybacks |
| Real Yield | Only applies to ETH / AAVE / SOL. Too sparse to be comparable across the peer set. |
| Staking Penetration | CoinDesk coverage gaps (LINK/UNI/CRV/LDO/SOL missing or proxy-only). Informational footnote, not a row. |
| Incentive/Revenue Ratio | Derivable from Token Incentive Expense and Retained Revenue; keeping it as a separate metric invites the reader to average two already-comparable rows. |
| Economic Earnings, Economic P/E | Double-count issues on chains where a portion of "emissions" are validator rewards (ETH/SOL); unreliable for cross-peer comparison |

---

## Data Pipeline

### Sources

After auditing free tier coverage, our usable source list is:

| Source | Data Provided | Key Required | Notes |
|---|---|---|---|
| **DeFiLlama** | TVL, protocol fees, protocol revenue, chain TVL | No | Confirmed free: `/protocol/{slug}`, `/summary/fees/{slug}`, `/chains`, `/protocols`. Same endpoint serves protocols and chains, so L1s like ETH/SOL fit through the same code path. Paywalled (don't use): `/emissions`, `/treasuries`. |
| **CoinGecko** (Demo tier) | Price, MC, FDV, supply + 365d historical market_chart | Yes (free Demo) | Implied historical supply derived as `market_cap / price`. |
| **CoinDesk Data** | Historical supply with **breakdown** (staked / locked / burned / issued / future / circulating) + OHLCV | Yes (free) | https://developers.coindesk.com/documentation/data-api/onchain_v2_historical_supply_days — this is a major win: gives us **net inflation, staked supply, and burns directly**, replacing several metrics we would have needed Glassnode/Dune for. |
| **Dune Analytics** | Custom on-chain SQL queries (dormancy, holder counts, contract-level events) | Yes (free 2,500 q/mo) | Used for flagship deep-dives where CoinDesk doesn't cover (e.g. true age-based dormancy on smaller tokens, project-specific buyback events). |
| **Etherscan** (and family) | Top holder concentration, transfer logs, contract reads | Yes (free) | EVM only. Per-chain keys for L2s. |

**Audited and dropped — no usable free tier:**

| Source | Reason |
|---|---|
| ~~Glassnode~~ | Free tier provides no API access. Web UI shows basic metrics but the API requires paid plan. |
| ~~CryptoQuant~~ | Exchange balance + net flow endpoints are paid only. Free API is OHLCV (already covered by CoinGecko/CoinDesk). |
| ~~Token.unlocks.app~~ | No free API tier. |
| ~~Flipside Crypto~~ | No retail/individual free tier for API access. |

### Implications of the revised source list

The **biggest shift from the original plan** is that CoinDesk's `/onchain/v2/historical/supply/days` endpoint covers most of what we'd planned to get from Glassnode and several Dune queries:

- **Net inflation** → `issued - burned` from CoinDesk historical supply
- **Burns** → CoinDesk `burned` series
- **Staking penetration** → CoinDesk `staked` series
- **Locked supply** → CoinDesk `locked` series (proxy for vesting / dormancy)
- **Future supply** → CoinDesk `future` series (similar to unlock pressure)

What's still on Dune:
- True age-based dormancy (CoinDesk doesn't have HODL waves)
- Project-specific events (e.g. MKR/SKY Smart Burn Engine activity, Aave buyback events)

What's still manual:
- 90-day forward unlock schedule with insider-vs-ecosystem split (curated `unlocks.yaml`)
- Value accrual mechanism classification (in `peer_set.yaml`)



### Pipeline Architecture

```
[APIs] → [Ingest Notebook] → [Normalized CSVs] → [Metrics Notebook] → [Charts Notebook]
                                                                              ↓
                                                                    [Vercel Dashboard]
                                                                    (fetches APIs directly
                                                                     with ISR caching)
```

### Notebook Structure

| Notebook | Purpose |
|---|---|
| `01_ingest.ipynb` | Fetch raw data from all sources; normalize to common schema; write to `/data/raw/` |
| `02_metrics.ipynb` | Compute all metrics per project; produce `/data/metrics/peer_table.csv` |
| `03_charts.ipynb` | Generate all Plotly visualizations; export to `/data/charts/` as interactive HTML |
| `04_analysis.ipynb` | Written commentary, key findings, LINK positioning analysis |

---

## Dashboard Layout (Vercel / Next.js)

**Tech stack:** Next.js (App Router) + Tremor or Recharts + Tailwind CSS

**Page structure:**

```
/ (Home)
├── Summary header: LINK highlighted among peers (market cap, FDV/MC, P/RR, 90d at-risk unlock %)
├── /valuation      — MC + FDV bars (uncapped flagged); P/F and P/RR multiples; value-accrual chips
├── /supply         — 90d at-risk unlock % bar; burns + buybacks annualized; per-peer unlock breakdown
├── /dormancy       — 180d dormant supply % bar; per-peer active vs. dormant split
├── /incentives     — Token Incentive Expense ($USD) bar; LINK vs. peers overlay
└── /methodology    — Metric definitions, data sources, and the removed-metrics rationale
```

**Refresh strategy:** Vercel ISR (Incremental Static Regeneration) with 24-hour revalidation on API routes fetching DeFiLlama and CoinGecko. No database required — all data fetched and cached at build/revalidation time. Fits within Vercel free tier limits.

---

## Key Assumptions to Document

1. **Retained Revenue is activity revenue, not token-claim revenue.** DeFiLlama `dailyRevenue` is reported as-is for every peer, including LINK and UNI. Whether that revenue accrues to the *token* is captured separately by **Value Accrual Mechanism** — UNI's fee switch is off and LINK's protocol-retained share is separate from node-operator fees, but this is a value-accrual gap, not a revenue gap. The prior iteration had an override reducing LINK/UNI retained revenue to $0, which was wrong: it conflated two questions.

2. **Annualization method:** 30-day trailing × 12 for fees and revenue. AAVE buyback spend uses the 30d rate (not 365d) because AIP-434 launched 2025-04-17 and buybacks were front-loaded.

3. **FDV uncapped handling:** ETH and SOL have no hard max supply. FDV is reported as **Uncapped (N/A)** and FDV/MC is not computed. Equating max_supply to circ_supply silently (the prior behavior) produced FDV=MC, which is misleading.

4. **90d At-Risk Unlocks is the consolidated supply-pressure metric.** It supersedes gross inflation, net inflation, effective dilution, and standalone reserve buybacks. Sourcing priority per peer: (1) on-chain vesting contract reads where available, (2) Token Unlocks schedule, (3) tokenomics docs and governance forum posts. Each entry in `unlocks.yaml` carries a source URL and an as-of date.

5. **Incentive expense:** Only on-chain, trackable emissions are counted. Off-chain grant programs and airdrops announced but not yet distributed are excluded.

6. **Dormancy (180d) uses outbound-transfer signal on EVM, balance-row-update signal on Solana.** EVM tables are vulnerable to dust-attack spam (observed on UNI — an airdrop-style spammer touched every holder, collapsing the signal), so the EVM queries count addresses that *sent* the token in the window. Solana keeps the balance-update signal because rent-exempt minimums make spamming 500M+ accounts economically unviable (~$440K+ at current SOL price). ETH uses a dedicated Dune query against mainnet tables — not the CoinDesk staked-supply proxy the prior iteration used.

---

## Presentation Structure (10 min)

1. **Framework (2 min)** — The slimmed metric set; which metrics were dropped and why; how the retained-revenue / value-accrual distinction handles the LINK asymmetry
2. **Peer Landscape (3 min)** — MC, FDV (with uncapped flagged), P/F and P/RR multiples; where LINK sits
3. **Supply & Dormancy (2 min)** — 90d at-risk unlocks; burns + buybacks; 180d dormancy
4. **Implications for LINK (3 min)** — The value-accrual gap: LINK has real activity revenue but no token-level claim on it; what the peer set suggests about closing that gap

---

## Open Questions / Data Risks

- [ ] **CoinDesk per-token coverage** — `/onchain/v2/historical/supply/days` covers BTC and ETH for sure; need to enumerate which of our peer set tokens have the full breakdown (`burned`, `staked`, `locked`, `future`). This drives whether net inflation and staking penetration are universal metrics or flagship-only.
- [ ] **DeFiLlama slug accuracy** — verify slugs for any peer-set additions; PYTH was wrong on first run (`pyth-network` 404'd), some tokens may use parent slug like `makerdao` vs `sky`.
- [ ] **Dune query budget** — 2,500 queries/month means we batch up custom queries (dormancy, burns, holder counts) and run them on a daily cron, not per-pageview from the dashboard.
- [ ] **Per-chain Etherscan keys** — single Etherscan key only covers Ethereum mainnet. If peer set includes ARB/OP/BASE-native tokens we'll need separate keys (free signups).
- [ ] **Manual unlocks freshness** — `unlocks.yaml` will go stale; document an update cadence and link to source URLs in each entry.
