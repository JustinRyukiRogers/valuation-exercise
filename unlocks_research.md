# Unlock Schedule Research Log
**Window: 2026-04-17 → 2026-07-16 (90 days)**
**Researched: 2026-04-17**

---

## OP (Optimism)
- **Circulating:** ~2.14B OP / 4.29B total
- **90d unlock estimate:** ~94M OP — three monthly cliff events of **~31.34M OP each** on Apr 30, May 31, Jun 30. (~4.4% of circ)
- **Split per event:** ~16.54M OP → Core Contributors, ~14.8M OP → Investors
- **Schedule type:** Hard on-chain monthly cliff. Coded into the vesting contract at genesis (May 2022). Runs through 2027.
- **Largest event in window:** All three cliffs are identical at ~31.34M OP
- **Vesting status:** Ongoing (continues through 2027 + 2% annual inflation thereafter)
- **Key sources:**
  - https://tokenomist.ai/optimism — "next unlock April 30, 2026: 31.34M OP ($3.84M); Core Contributors 16.54M, Investors 14.8M"
  - https://cryptorank.io/price/optimism/vesting — calendar view confirms monthly run rate; historical Jun 2024 unlock of 31.34M confirmed
  - https://cryptorank.io/news/feed/6f0d8-optimism-unlocks-over-31-million-op — confirms split (Core Contributors ~$30M, Investors ~$24M at prior prices)
- **Delta vs current unlocks.yaml:** yaml has 65M — **needs update to ~94M** (3 × 31.34M)

---

## LINK (Chainlink)
- **Circulating:** ~727M LINK / 1B total; ~273M in non-circulating treasury across 24 wallet contracts
- **90d unlock estimate:** April quarterly (~19M LINK) occurred **Apr 4**, just before window opens. Next expected: **July 2026 quarterly ~10–20M LINK** (~1.4–2.75% of circ). No hard on-chain date — treasury discretionary.
- **Schedule type:** No on-chain vesting contract. Treasury discretionary. Behavioural pattern: quarterly releases (Jan/Apr/Jul/Oct), ~10–20M LINK each. Formal vesting schedule ended 2024.
- **Destination of releases:** ~75-80% to Binance (market), ~20-25% to staking reward multisig
- **Largest event in window:** July quarterly estimate ~10–20M LINK (no exact date published)
- **Vesting status:** Formal schedule complete. ~273M LINK remain in treasury at Chainlink Labs' discretion
- **Key sources:**
  - https://coinpedia.org/news/chainlink-unlocks-19m-link-165m-moved-to-market/ — "nearly 19M LINK ($165M) moved from non-circulating wallets" ~Apr 4, 2026; quarterly cadence confirmed
  - https://cryptorank.io/news/feed/6c881-chainlink-link-unlock-binance-transfer — "14.37M LINK to Binance + 4.62M to multisig; scheduled quarterly release"
  - https://www.ainvest.com/news/chainlink-126m-quarterly-unlock-binance-flow-price-impact-2604/ — April 2026 event detail
  - https://tokenomist.ai/chainlink — "unlock schedule ended in 2024"; no upcoming cliff events listed; confirms ~727M circulating
- **Delta vs current unlocks.yaml:** yaml has 20M. Research suggests the in-window release is the July quarterly (~10–20M, estimate). The 20M yaml figure is a reasonable upper bound but is marked as an estimate.

---

## SOL (Solana)
- **Circulating:** ~575M SOL (no fixed max; inflationary)
- **90d unlock estimate from vesting:** **Zero** — original team/investor/foundation/validator vesting is fully complete per tokenomist.ai. Remaining supply additions:
  - Protocol inflation: ~22.5M SOL at 3.9% annual rate (~3.9% × 575M ÷ 4)
  - FTX/Alameda estate: ~194K–198K SOL/month unstaked for creditor payouts → **~580K SOL over 90 days**. Estate held ~3.572M SOL as of Apr 13, 2026.
- **Schedule type:** Inflation = automatic epoch-by-epoch. FTX estate = bankruptcy-driven monthly distributions (discretionary, non-vesting)
- **Vesting status:** **Complete** — "Solana is fully unlocked" per tokenomist.ai
- **Key sources:**
  - https://tokenomist.ai/solana — "Solana is fully unlocked. When is the next Solana unlock? Solana is fully unlocked."
  - https://solanacompass.com/tokenomics — "annual inflation rate is currently 3.898%, decreasing 15%/year"
  - https://www.cryptotimes.io/2026/04/13/alameda-moves-16-million-in-solana-sol-as-creditor-payout-nears/ — "estate holds ~3.572M SOL ($292M); ~194,400 SOL unstaked Apr 13 2026"
  - https://www.cryptotimes.io/2026/03/12/ftx-alameda-estate-unstakes-17m-in-solana-for-monthly-creditor-payout/ — confirms recurring monthly creditor pattern
- **Note:** SIMD-0411 proposal (double disinflation rate) under community discussion; if passed would reduce 90d inflation figure
- **Delta vs current unlocks.yaml:** yaml has 2.5M SOL as vesting residual. **Needs correction to 0** — vesting is confirmed complete. FTX estate (~580K SOL) is the only non-inflation drip, and it is declining.

---

## LDO (Lido DAO)
- **Circulating:** ~849M LDO / 1B total; ~151M in DAO treasury
- **90d unlock estimate:** **Zero** — vesting complete, no scheduled releases
- **Schedule type:** Complete for all buckets. Treasury is governance-discretionary only
- **Vesting status:** **Complete** — "Lido DAO is fully unlocked; the unlock schedule ended in 2024"
- **Notable:** Active $20M LDO buyback program approved ~Mar 30, 2026 — **deflationary**, not dilutive. $1.81M LDO transferred to buyback multisig as of Apr 16. Also ongoing GOOSE-3 governance $60M operations budget for 2026 — if approved, some treasury LDO could be spent.
- **Key sources:**
  - https://tokenomist.ai/lido-dao — "Lido DAO is fully unlocked. The unlock schedule ended in 2024"
  - https://help.lido.fi/en/articles/5231885-what-is-the-token-release-schedule-for-ldo — official Lido: "no concrete emission/release schedule for LDO tokens in treasury; emissions voted on by DAO"
  - https://www.coindesk.com/markets/2026/03/30/lido-dao-proposes-usd20-million-ldo-buyback-to-boost-price-after-95-slide — $20M buyback context
- **Delta vs current unlocks.yaml:** Matches (0 scheduled). Buyback detail is new — worth noting as a supply footnote.

---

## UNI (Uniswap)
- **Circulating:** ~634M UNI (CoinGecko figure pre-UNIfication accounting adjustments; 100M treasury burned Dec 28, 2025; total supply moved from 1B → ~900M)
- **90d unlock estimate:** **~5M UNI** — the Q3 2026 tranche of the new annual growth budget (~Jul 1)
- **New vesting context (UNIfication, Jan 1 2026):** 20M UNI/year growth budget approved, distributed quarterly via on-chain vesting contract to Uniswap Labs as service provider. Q1 = Jan 1, Q2 = ~Apr 1, Q3 = **~Jul 1 (in window)**, Q4 = ~Oct 1. Each tranche = **5M UNI**.
- **Offset:** Firepit protocol fee burn active on ETH + 8 other chains; ~4M UNI/year burned (~1M/quarter). Net = ~4M UNI over 90 days.
- **Vesting status:** Original 2020–2024 four-year schedule = **complete**. New UNIfication growth budget = **ongoing** (started Jan 1, 2026; runs indefinitely)
- **Key sources:**
  - https://blog.uniswap.org/unification — "annual growth budget of 20M UNI, distributed quarterly using a vesting contract starting January 1, 2026"
  - https://www.coindesk.com/business/2025/12/26/uniswap-s-token-burn-protocol-fee-proposal-backed-overwhelmingly-by-voters — 100M UNI burn Dec 28 2025; fee switch activated
  - https://99bitcoins.com/news/altcoins/uniswap-unification-bullish-but-is-this-20m-uni-per-year-allocation-a-tax/ — confirms 5M UNI/quarter to Labs under DUNI agreement
  - https://tokenomist.ai/uniswap — "unlock schedule ended in 2024" (referring to original 2020 schedule; notes UNIfication creates new 20M/yr stream)
- **Delta vs current unlocks.yaml:** yaml has 0. **Needs update to ~5M UNI** (Q3 growth budget tranche). Also: the 100M token burn and fee-switch activation are both significant developments not reflected in the current yaml.

---

## CRV (Curve)
- **Circulating:** ~1.47–1.5B CRV / 3.03B total (fixed)
- **90d unlock estimate:** **~28.3M CRV** from continuous gauge emissions (115.5M/year ÷ 4 = ~28.9M/quarter). ~1.9% of circ.
- **Schedule type:** Hardcoded linear emission per block. No cliffs. Reduces ~15.9% each August. Next cut: August 2026 (just outside window).
- **Vesting status:** Team/investor/employee vesting = **complete as of August 12, 2024**. "After August 12th, 2024 all CRV added to circulating supply is distributed to the community through gauges." Community gauge emissions = **ongoing indefinitely** (~200-year tail hardcoded at genesis).
- **Key sources:**
  - https://resources.curve.finance/crv-token/supply-distribution/ — official docs on post-Aug 2024 emissions being 100% community gauge rewards
  - https://bitcoinethereumnews.com/tech/crv-price-surges-as-curve-finance-cuts-token-emissions-by-15-9/ — "dropping from 137.4M to 115.5M tokens yearly" after Aug 2025 reduction
  - https://news.curve.finance/crv-emission-rate-gets-a-cut-as-programmed/ — official Curve blog confirms permissionless annual cuts
- **Delta vs current unlocks.yaml:** yaml correctly has `counted_in_inflation: true`, 0 in the unlock field. Matches — CRV emissions are captured in gross_inflation via CoinDesk and should NOT be double-counted here.

---

## AAVE (Aave)
- **Circulating:** ~15.2M AAVE / 16M total; ~652K–800K in Ecosystem Reserve
- **90d unlock estimate:** **~20K–74K AAVE** from Safety Module emissions (governance-set). Proposed March 2026 to reduce stkAAVE emissions to 220 AAVE/day (vs prior 820 AAVE/day). At 220/day × 90d = **~19,800 AAVE** (0.13% of circ). If proposal not yet passed, ~73,800 AAVE (0.49% of circ).
- **Offset:** DAO buyback program repurchased 205,000+ AAVE since April 2025 — materially deflationary; buybacks exceed SM emissions at current run rates.
- **Vesting status:** **Complete**. "Aave is fully unlocked."
- **Key sources:**
  - https://tokenomist.ai/aave — "~15.19M AAVE (94.91%) unlocked; Aave is fully unlocked"
  - https://governance.aave.com/t/arfc-safety-module-reduce-emissions/24203 — Mar 2 2026 proposal: reduce stkAAVE daily emissions to 220 AAVE/day; "29,200 AAVE saved annually = ~0.18% of supply"
  - MEXC tokenomics data (secondary) — "16M total; 15,347,205 unlocked; 652,673 locked (Ecosystem Reserve)"
- **Delta vs current unlocks.yaml:** yaml has 0. Correct in spirit — SM emissions are tiny (~0.13–0.49% of circ) and net deflationary given buybacks. Fine to keep as 0 for the unlock table; add a footnote on SM emissions if needed.

---

## ETH (Ethereum)
- **Circulating:** ~120.5–121.5M ETH (no fixed cap)
- **90d supply change:** **+~146,700 ETH net** from validator issuance (~1,700 ETH/day) minus EIP-1559 burns (~50–70 ETH/day in current low-fee environment). Annualized net inflation ~+0.23%.
- **Vesting:** N/A — no team/investor vesting ever existed
- **Schedule type:** Continuous protocol issuance. No cliffs, no treasury, no vesting.
- **Notable:** "Ultrasound money" narrative reversed after Dencun (Mar 2024) reduced L1 fees and thus burns. Mildly inflationary as of 2026.
- **Key sources:**
  - https://ethereum.org/roadmap/merge/issuance/ — ~1,700 ETH/day to validators; ~14M ETH staked; 0.52% gross annual issuance
  - https://www.coindesk.com/markets/2026/01/06/ethereum-s-staking-queues-have-cleared-and-that-changes-the-eth-trade — staking queues near zero; ~28.5-30% of supply staked
  - https://bitcoinethereumnews.com/ethereum/ethereum-token-supply-in-2026-the-ultrasound-money-story-got-complicated/ — confirms net inflationary since Dencun
- **Delta vs current unlocks.yaml:** Matches (0 scheduled unlocks, `counted_in_inflation: true`).

---

## Summary: Delta from Current unlocks.yaml

| Token | Current yaml | Research finding | Action needed |
|-------|-------------|-----------------|---------------|
| OP | 65M OP | ~94M OP (3 × 31.34M) | **Update — higher by 45%** |
| LINK | 20M LINK | ~10–20M LINK (July quarterly, discretionary) | Acceptable range; note April event already passed |
| SOL | 2.5M SOL | 0 vesting; ~580K from FTX estate | **Update — vesting is complete** |
| LDO | 0 | 0 | Correct |
| UNI | 0 | ~5M UNI (Q3 growth budget ~Jul 1) | **Update — new UNIfication vesting stream** |
| CRV | 0 (counted_in_inflation) | ~28.3M from gauge emissions (already in inflation) | Correct |
| AAVE | 0 | ~20K–74K from SM emissions (offset by buybacks) | Correct (leave as 0; add footnote) |
| ETH | 0 (counted_in_inflation) | ~146.7K net from validator issuance | Correct |
