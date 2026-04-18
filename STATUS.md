# Project Status

Tracks implementation state of every metric and deliverable.
Update this file whenever a metric is wired up, a Dune query is authored, or a flag is retired.

**Legend:** ✅ complete · 🟠 partial · ⚪ not started · 🚫 dropped (out of scope)

---

## Canonical Metrics (per PLAN.md)

### Section 1 — Valuation & Supply

| Metric | Status | Notes |
|---|---|---|
| Market Cap | ✅ | CoinGecko |
| FDV | ✅ | ETH/SOL flagged `uncapped: true`; FDV and FDV/MC rendered as N/A |
| FDV / MC | ✅ | Capped peers only |
| ~~Circulating Supply %~~ | 🚫 dropped | Information content already in FDV/MC |

### Section 2 — Revenue & Fees

| Metric | Status | Notes |
|---|---|---|
| Annualized Total Fees | ✅ | DeFiLlama 30d × 12 |
| MC / Total Fees (P/F) | ✅ | `mcap_over_fees` in CSV |
| Retained Revenue | ✅ | DeFiLlama `dailyRevenue` as-is for all peers; LINK/UNI not zeroed out |
| MC / Retained Revenue (P/RR) | ✅ | `mcap_over_revenue` in CSV |
| Value Accrual Mechanism | ✅ | Categorical in `peer_set.yaml`: burn / buyback / staking / fee_share / none |
| ~~Forward Revenue Forecasts~~ | 🚫 dropped | Out of scope |

### Section 3 — Supply Dynamics

| Metric | Status | Notes |
|---|---|---|
| 90d At-Risk Unlocks | ✅ | `unlocks.yaml` event-level schedule. OP: 3 × 31.34M cliff = 94M (4.4% circ). LINK: 15M estimated Q3 treasury release. Forward supply curve in `data/metrics/forward_supply_curve.csv` |
| Burns + Buybacks | ✅ | ETH: CoinDesk burn series. SOL: Dune Q1 base-fee burn. AAVE: Dune Q3 ($453M/365d, $3.6M/30d). LINK: Reserve buyback ($62.5M/yr, 130K LINK/wk). UNI: Dune Q6 Firepit burn (~10.5M UNI/yr). LDO/CRV/OP: N/A |
| Net Dilution (annualized) | ✅ | Derived from forward panel day-90 × (365/90). See `net_dilution_annualized` in peer_table.csv |
| Rewards-Adjusted Dilution | ✅ | `net_dilution_annualized − incentive_yield_annualized` |
| ~~Gross/Net Inflation (standalone)~~ | 🚫 dropped | Folded into 90d At-Risk Unlocks |
| ~~Net Idle System Sell Pressure~~ | 🚫 dropped | Subsumed by 90d At-Risk Unlocks + Burns/Buybacks |

### Section 4 — Dormancy

| Metric | Status | Notes |
|---|---|---|
| 180d Dormant Supply % | ✅ | EVM: Dune outbound-transfer signal (dust-attack resistant). SOL: Dune balance-row. ETH: Dune Q7332769 native-balance reconstruction (84.8M active ETH, 29.7% dormant) |
| ~~1yr+ Dormancy~~ | 🚫 dropped | One 180d window sufficient |
| ~~Exchange Balance / Flow~~ | 🚫 dropped | CEX attribution inconsistent across peer set at free tier |
| ~~Top 10 / Top 100 Holder Concentration~~ | 🚫 dropped | Etherscan Pro required; no comparable SOL equivalent |
| ~~Supply Velocity~~ | 🚫 dropped | Wash-trade contaminated |

### Section 5 — Incentives

| Metric | Status | Notes |
|---|---|---|
| ~~Token Incentive Expense~~ | 🚫 dropped | Superseded by Incentive Capture Yield |
| Incentive Capture Yield | ✅ | `incentive_yield.yaml` per peer; LINK 4.35% (Staking v0.2), ETH 2.7% (validator), SOL 6.5% (delegated staking), CRV 8.71% (veCRV), AAVE −2.6% (net buyback yield) |
| ~~Incentive/Revenue Ratio~~ | 🚫 dropped | Derivable from the above two rows |
| ~~Economic Earnings / P/E~~ | 🚫 dropped | Double-count issues on ETH/SOL; unreliable cross-peer |
| ~~Real Yield~~ | 🚫 dropped | Too sparse across peer set |
| ~~Staking Penetration~~ | 🚫 dropped | CoinDesk coverage gaps; informational footnote only |

---

## Supply Dynamics Handler Status

| Symbol | Handler | `needs_custom` flags | Dune query |
|---|---|---|---|
| ETH | `eth_supply_dynamics` | — | — (beacon-chain formula) |
| SOL | `sol_supply_dynamics` | ~~`burn_rate_annualized`~~ → ✅ | Q1 — ID 7328502 |
| LINK | `link_supply_dynamics` | — | Q2 — ID 7328638 (informs unlocks.yaml, not inflation) |
| AAVE | `aave_supply_dynamics` | ~~`aave_buyback_spend_usd`~~ → ✅ | Q3 — ID 7328824 |
| UNI | `uni_supply_dynamics` | — | Q6 — ID 6430914 (Firepit burn, 110d data) |
| CRV | `crv_supply_dynamics_noop` | — | — |
| LDO | `ldo_supply_dynamics` | — | — |
| OP | `op_supply_dynamics` | `effective_dilution_from_unlocks` (resolved via unlocks.yaml) | manual |

---

## Dune Queries

| Key | Dune ID | Status | Purpose |
|---|---|---|---|
| `sol_base_fee_burn` | 7328502 | ✅ | SOL `burn_rate_annualized`, `net_inflation_annualized` |
| `link_treasury_outflow` | 7328638 | ✅ | Informs LINK `unlocks.yaml` entry (~41.5M/yr, ~10.4M/90d) |
| `aave_buyback_spend` | 7328824 | ✅ | AAVE buyback: $453M/365d, $3.6M/30d |
| `uni_firepit_burn` | 6430914 | ✅ | UNI Firepit: 3.16M burned / 110d → ~10.5M/yr projected |
| `sol_dormancy` | 7328755 | ✅ | SOL active balance 180d |
| `evm_dormancy_ethereum` | 7328758 | ✅ | LINK/AAVE/UNI/LDO/CRV active balance 180d |
| `evm_dormancy_optimism` | 7328772 | ✅ | OP active balance 180d (47% dormant) |
| `eth_dormancy` | 7332769 | ✅ | ETH native-balance reconstruction 180d (29.7% dormant) |

---

## Infrastructure & Deliverables

| Item | Status | Notes |
|---|---|---|
| `01_ingest.ipynb` | ✅ | Fresh `peer_snapshot.csv` for 8-token set |
| `02_metrics.ipynb` | ✅ | Exports `peer_table.csv` + `forward_supply_curve.csv` |
| `03_charts.ipynb` | 🟠 | First pass charts done (valuation, fees, supply, dormancy, price). PNG export needs `kaleido` |
| `04_analysis.ipynb` | ⚪ | Not started |
| Static dashboard (`dashboard/`) | ✅ | 6 pages (Overview, Valuation, Supply, Dormancy, Incentives, Methodology) generated by `scripts/build_dashboard.py`. Pure HTML + Tailwind CDN, iframes existing Plotly charts. Deploys to Vercel as static hosting (zero-config via `vercel.json`) — no Node/Next.js needed |
| Methodology document | ⚪ | Not started |
| Presentation | ⚪ | Not started |

---

## Known Methodology Footnotes

- **OP locked > 100% of circ**: CoinDesk's `locked` denominator for pre-minted-supply tokens includes treasury, so it exceeds circulating supply. Document; do not "fix" the underlying data.
- **SOL burn approx vs precise**: The `sol_burn_rate_annualized_approx` column in Dune Q1 overstates burns ~3.8× (83,968 SOL/30d approx vs 22,225 SOL/30d base_fee, as of 2026-04-17) because priority fees now dominate transaction fees and are not burned. Use `sol_burn_rate_annualized_base_fee` (0.047% annualized, ~22K SOL/month) as the canonical figure. The earlier "9×" estimate is stale.
- **ETH net inflation**: Currently slightly negative (−0.01%) — EIP-1559 burn exceeds issuance. Worth calling out in the analysis.
- **LINK / UNI retained revenue**: DeFiLlama `dailyRevenue` reported as-is (LINK ~$55.5M/yr, UNI ~$41.4M/yr). Not zeroed out — revenue is real activity. The **Value Accrual Mechanism** column (`staking` for LINK, `none` for UNI) carries the "token doesn't claim this" story.
- **FDV for uncapped tokens**: ETH and SOL have no hard max supply. CoinGecko silently sets FDV = MC, which reads as "no dilution risk" — the opposite of the truth. `uncapped: true` in `peer_set.yaml` drives ingest to null FDV and FDV/MC; dashboard renders explicit "Uncapped" label.
- **Dormancy denominator is total_supply, not circ_supply**: Dune queries count all token activity including locked/vested tokens. Using circ_supply understated dormancy for tokens with significant non-circulating supply and caused CRV to show 0% (Dune active supply of 1.624B exceeded CoinGecko circ of 1.499B due to veCRV contract activity). Switching to total_supply gives CRV 31.5%, LINK 62.8%, OP 57.6%, LDO 58.5%. ETH/SOL are unaffected (total == circ for uncapped tokens).
- **Dormancy uses outbound-sender signal (EVM)**: EVM queries (7328758, 7328772) define "active" as addresses that have *sent* the token in the last 180d. Balance row updates were the initial approach but are vulnerable to dust attacks — e.g. `0x9edc...5890` sent trivial UNI to every holder, collapsing the signal.
- **SOL dormancy keeps `block_time` signal**: Dust-attack risk is economically unviable (~$440K+ to spam 500M+ accounts at rent-exempt minimums). Outbound-transfer scan not warranted.
- **ETH dormancy via native-balance reconstruction**: No curated mainnet ETH balance table exists on Dune. Dune Q7332769 reconstructs balance from genesis + withdrawals + tx/trace flows − gas. ~16.5M ETH comes out negative from edge cases (selfdestruct/suicide traces, pre-Byzantium ommers); floored to zero. Value cap of 1e30 wei filters UINT256 garbage from malicious contracts. Sanity-check: 29.7% dormancy tracks CoinDesk `staked_supply_pct` (31.3%).
- **CRV inflation overridden to 5.02%**: CoinDesk's trailing `issued` series reflected the old ~9.25% schedule. CRV emissions follow a time-decay schedule hardcoded in the token contract; the most recent reduction brought the annualized rate to ~5.02% as of early 2026 (source: https://metamask.io/price/curve-dao-token). Next reduction is Aug 2026. Handler updated to `crv_supply_dynamics` (was `crv_supply_dynamics_noop`).
- **AAVE buyback rate is front-loaded**: 365d figure ($453M) implies ~$37.7M/month, but trailing 30d is only $3.6M. Buybacks concentrated immediately post-AIP-434 (Apr–Jul 2025). Use 30d as the near-term signal; 365d overstates current run-rate.
- **LINK net dilution calculation**: `net_dilution_annualized` (7.5%) is built from the 90-day forward panel scaled by 365/90. At day 90: 15M treasury unlock = +2.06%; Reserve buyback (12 weekly events × 0.0176%) = −0.21%; net 1.85% × 4.056 = 7.51%. Staking v0.2 yield (4.35%) brings `rewards_adjusted_dilution` to +3.16%.
- **LINK treasury unlock is discretionary**: No on-chain vesting contract. 15M LINK modeled for mid-July based on observed quarterly cadence (10–20M/quarter, ~75–80% to Binance). Amount and timing are estimates — could be accelerated, delayed, or skipped.
- **UNI Firepit burn data window**: 110 days of on-chain data as of 2026-04-17; 3.16M UNI burned → ~10.5M/yr projected. Original UNIfication blog estimate (4M/yr) proved 2.6× too low. `burn_rate_annualized` was corrected from 1.44% → 1.66% after fixing the denominator from CoinDesk circulating (~728M, stale pre-burn) to CoinGecko circ_supply (634M, post-Dec 2025 100M treasury burn).
- **Forward Revenue Forecasts**: Out of scope for the metrics layer. Use "annualized revenue × 90d growth trend" as a narrative model in `04_analysis.ipynb` instead.
