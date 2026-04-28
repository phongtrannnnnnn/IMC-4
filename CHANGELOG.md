# IMC Prosperity 4 — Changelog

> Tracking all algorithmic and manual trading decisions across rounds.

---

## Round 2 (Phase 1 Qualifier)

**Products:** ASH_COATED_OSMIUM (pos limit 80), INTARIAN_PEPPER_ROOT (pos limit 80)  
**Data:** 3 days (day -1, 0, 1) — `ROUND_2.zip`  
**Baseline:** `uploaded_version.py` → **-36,538 XIRECs** on Round 2  
**Final:** `trader.py` → **+256,328 XIRECs** on Round 2

### Algorithmic Trading (`trader.py`)

#### Statistical Analysis
- **ACO**: Pure mean-reversion around 10,000 (autocorr = -0.49, std ≈ 4-5, spread ≈ 16, L1 vol ≈ 14)
- **IPR**: Deterministic linear trend at 0.001/timestamp (≈ +1,000/day, R² = 0.99997, residual std ≈ 1.6)
- **Cross-product**: Independent (correlation ≈ 0). No pairs/hedge ratio applicable.
- **Book depth**: L2 present 42.7% of the time, offset ~3 ticks from L1, vol ~24. No L3.
- **AR structure**: ACO lag-1 = -0.47 (only lag 1 matters, lag 2+ ≈ 0). IPR residual lag-1 = -0.49.

#### ACO Strategy — AR(1) Mean-Reversion Market Maker

| Version | Change | R2 Impact |
|---------|--------|-----------|
| v1 | Basic market making at fixed fair=10000, spread=4 | Baseline: ~3.5k/day |
| v2 | EMA-blended fair (0.5 anchor + 0.5 EMA-12) | +500/day |
| v3 | AR(1) prediction (coeff=-0.30, sweep-optimized from -0.47) | +1.5k/day |
| v4 | Book imbalance signal (±0.4 fair adjustment) | +200/day |
| v5 | Multi-level quoting (L1 at spread=3, L2 at spread=6) | +500/day |
| v6 | Sweep-optimized: spread=3, take=2.5, skew=0.10 | +7.3k total |
| v7 | EOD liquidation at ts > 985,000 | Prevents mark-to-market loss |

**Final ACO Parameters:**
```
ACO_ANCHOR = 10000          # long-run fair value
ACO_EMA_WEIGHT = 0.50       # 50% anchor + 50% EMA-12
ACO_AR_COEFF = -0.30        # AR(1) coefficient (sweep: -0.3 > -0.47)
ACO_SPREAD_HALF = 3         # half-spread (sweep: 3 > 2 > 1)
ACO_TAKE_THRESHOLD = 2.5    # aggressive take threshold (sweep: 2.5 > 1.5)
ACO_SKEW_COEFF = 0.10       # inventory skew per unit
ACO_BASE_SIZE = 22           # base quote size
ACO_COOLDOWN = 150           # ticks between takes
ACO_L2_OFFSET = 3            # L2 quote offset
ACO_L2_SIZE_FRAC = 0.6       # L2 size = 60% of L1
```

**ACO per-day P&L: ~7-8k/day**

#### IPR Strategy — Trend-Following Accumulator

| Version | Change | R2 Impact |
|---------|--------|-----------|
| v1 | Market making (same as ACO) | **-25k/day** (fighting the trend) |
| v2 | Trend model with slope=0.1081 (WRONG: per-index, not per-ts) | +64k/day (accidentally worked) |
| v3 | **Critical fix**: slope=0.001 (per-timestamp, 108× correction) | +17k/day |
| v4 | Removed EOD liquidation (hold for mark-to-market) | +78k/day |
| v5 | AR(1) on residuals (coeff=-0.49) | +200/day |
| v6 | Sweep-optimized: accum=2.5, spike_z=3.0 | +2.6k total |
| v7 | Multi-level passive buying (L1 at fair, L2 at fair-2) | +200/day |

**Core insight:** IPR has deterministic uptrend. Positions are marked-to-market at final mid price. Therefore: **HOLD MAX LONG the entire day. Never sell.**

**Final IPR Parameters:**
```
IPR_SLOPE = 0.001           # price per timestamp (1000/day)
IPR_RESIDUAL_STD = 1.6      # residual std
IPR_AR_COEFF = -0.49        # AR(1) on residuals
IPR_ACCUM_THRESHOLD = 2.5   # buy up to fair + 2.5 (sweep-optimized)
IPR_SPIKE_EXIT_Z = 3.0      # sell on z > 3.0 only (sweep-optimized)
IPR_COOLDOWN = 500           # ticks between sells
IPR_MIN_HOLD = 30            # never go below 30 long
```

**IPR per-day P&L: ~77-78k/day**

#### Market Access Fee (MAF)
- `bid() → 150` XIRECs
- Top 50% of bids get 25% extra order book quotes

#### Techniques Tested but Rejected

| Technique | Source | Result | Reason |
|-----------|--------|--------|--------|
| Microprice / VWAP fair | Alpha Animals (9th, P3) | -0.34% | ACO book is symmetric |
| Filtered mid (vol ≥ 10) | Alpha Animals | +0.019 mean diff | No signal |
| Penny improvement | Frankfurt Hedgehogs (2nd, P3) | -192 | Reduces spread edge in 16-tick market |
| Clear position at fair | Alpha Animals | -348 | Gives up spread edge |
| Full position sizing (base=40-80) | Multiple teams | -20k | Too much inventory risk for mean-reversion |
| Heavier EMA weight (0.6-1.0) | Tested | -112 to -2,816 | Overfits to noise, loses anchor |

#### Parameter Sweep Results (100+ combos tested)

**ACO sweep winner:** `take=2.5, spread=3, skew=0.10` (+7,321 vs baseline)  
**ACO AR sweep:** `ar=-0.3, ema_w=0.5` (+4,527 vs baseline)  
**IPR sweep winner:** `accum=2.5, spike_z=3.0` (+2,590 vs baseline)

#### Final Performance

| Metric | Round 2 | Round 1 |
|--------|---------|---------|
| **Total P&L** | **+256,328** | **+256,484** |
| **Sharpe** | **100.13** | **154.16** |
| **Sortino** | **∞** | **∞** |
| **All days positive** | ✅ 3/3 | ✅ 3/3 |
| **Conservative fills** | **255,967** | — |
| **Per-day range** | 84.5k — 86.2k | 84.6k — 85.9k |

---

### Manual Trading — Resource Allocation Challenge

#### Curve Analysis

**Research Curve** — Logarithmic (diminishing returns):
$$R(x_R) = 200{,}000 \cdot \frac{\ln(1 + x_R)}{\ln(101)}$$

Verified data points:
| $x_R$ | $R(x_R)$ | % of max |
|--------|-----------|----------|
| 1 | 30,038 | 15% |
| 3 | 60,076 | 30% |
| 10 | 103,915 | **52%** |
| 15 | 120,152 | 60% |
| 20 | 131,937 | **66%** |
| 100 | 200,000 | 100% |

> [!IMPORTANT]
> At $x_R = 10$, you capture 52% of max Research. The remaining 90% of budget yields only 48% more. **Cap Research at 15-20%.**

**Scale Curve** — Strictly linear:
$$S(x_S) = 0.07 \cdot x_S$$

#### Profit Function (hypothesized)
$$P(x_R, x_S, x_V) = R(x_R) \cdot S(x_S) \cdot V(x_V)$$

Subject to: $x_R + x_S + x_V = 100$

#### Speed Variable Hypotheses

| Hypothesis | $V(x_V)$ Form | Optimal Split (R/S/V) |
|------------|----------------|----------------------|
| **A: Linear** (symmetric multiplier) | $c \cdot x_V$ | 15 / 42 / 43 |
| **B: Logarithmic** (HW diminishing returns) | $\ln(1 + x_V)$ | 15 / 70 / 15 |
| **C: Sigmoid** (winner-takes-all threshold) | $\frac{1}{1 + e^{-k(x_V - \theta)}}$ | Unoptimizable blind |

#### Analytical Solution (Scenario A — Speed is Linear)

Using Lagrange multipliers with $s = v$ (by symmetry):
$$s = (1+r)\ln(1+r), \quad r + 2s = 100 \implies r \approx 14.5$$

#### Recommended Allocation: Robust Hedge

> [!TIP]
> **Research: 15 | Scale: 50 | Speed: 35**

| Variable | Allocation | Rationale |
|----------|-----------|-----------|
| Research | **15%** | Locks in 120,152 base (60% of max). Avoid log decay. |
| Scale | **50%** | $3.5\times$ linear multiplier. Guaranteed marginal utility. |
| Speed | **35%** | Large enough for linear; safe if logarithmic. |

This hedges between Scenario A (linear speed) and Scenario B (log speed) without catastrophic loss in either case.

---

## Round 4 (Phase 2 — GOAT)

**Products:** Same as Round 3 (HYDROGEL_PACK, VELVETFRUIT_EXTRACT, VEV ×10)  
**Position Limits:** 200 / 200 / 300 per voucher  
**Duration:** April 26 – April 28 (48 hours)  
**VEV TTE:** 4 days at start of Round 4

### Algorithmic: "Hello, I'm Mark"

**New mechanic:** Counterparty IDs disclosed. `Trade.buyer` and `Trade.seller` fields now contain participant names (previously `None`).

> [!IMPORTANT]
> Local backtester diverges significantly from official platform. All P&L below is from **official platform uploads**. The backtester remains useful only for syntax/import validation.

#### Counterparty Intelligence

7 unique participants confirmed in v12 trade history:

| Participant | Primary Product | Volume | Role |
|-------------|----------------|--------|------|
| **Mark 01** | VEV options | 823 lots bought | Main revenue source — buys our option sells |
| **Mark 14** | VEV_5000, HP | 898 lots bought | Largest buyer overall (245 on VEV_5000) |
| **Mark 22** | VEV various | 365 lots | Mixed — buys & sells |
| **Mark 38** | HP | 166 lots | Noise on HP (fade-able) |
| **Mark 55** | VE | 208 lots | Losing momentum bot on VE |
| **Mark 67** | VE | 38 lots | Momentum buyer (small volume) |
| **Mark 49** | VE | 26 lots | Seller |

#### Strategy Evolution — v6 → v12 (Final)

| Version | Total P&L | Max DD | Key Change |
|---------|-----------|--------|------------|
| v6 (baseline) | +25,220 | 16,085 | Mid-based VEV quoting, EMA+AR HP |
| v7 | +25,220 | 16,085 | Same code re-uploaded |
| v8 | ~25,200 | ~16,500 | Minor HP parameter tuning |
| v9 | ~25,200 | ~16,500 | VEV velocity protection added |
| v10 | +26,411 | 16,984 | **Inside-best HP, Mark 01 detection, TTE-based EOD** |
| v11 | +25,814 | 15,475 | Delta-hedge VE (price skew) — **VE lost -647** |
| **v12** | **+26,309** | **16,826** | **Size-only VE hedge — fixed v11's VE loss** |
| v13 | +23,936 | 13,327 | Mark 67/55 VE signals — **VE lost -2,310 (reverted)** |

**v12 = Final production version (+26,309)**

#### Per-Product P&L Breakdown (v12 vs 518982 competitor)

| Product | v12 | 518982 | Gap | Notes |
|---------|-----|--------|-----|-------|
| HP | +883 | +883 | 0 | ✅ Matched — inside-best quoting |
| VE | -152 | -9,754 | +9,602 | ✅ We're far better on VE |
| VEV_4000 | +162 | -1,148 | +1,310 | ✅ We're better — deep ITM MM |
| VEV_5000 | +2,516 | +5,469 | **-2,953** | ❌ Main alpha leak |
| VEV_5100 | +9,417 | +9,617 | -200 | ~Matched |
| VEV_5200 | +7,905 | +7,946 | -41 | ~Matched |
| VEV_5300 | +4,850 | +4,836 | +14 | ✅ |
| VEV_5500 | +728 | +728 | 0 | ✅ |
| **TOTAL** | **+26,309** | **+16,441** | **+9,868** | **We beat 518982 by +60%** |

> v12 captures **89% of theoretical maximum** (+29,637 = best-of-each-product across all versions)

#### Architecture (v12)

```
HYDROGEL_PACK:    Inside-best quoting (bb+1, ba-1) + inventory skew + Mark 38 burst
VELVETFRUIT_EXTRACT: Size-biased delta hedge (no price skew) + passive MM
VEV Deep ITM:     VE-oracle MM (fair = VE - strike, spread ±7)
VEV ATM/NTM:      BS-priced taker+maker, adaptive opt_sell edge, Mark 01 detection
```

**Key parameters:**
- `SIGMA = 0.0122` (implied vol for BS pricing)
- `opt_sell = 1.1` (adaptive: 0.25–3.0 range, × 0.55 when Mark 01 active)
- `VEV_VEL_WARN = 5.0`, `VEV_VEL_STOP = 10.0` (velocity protection thresholds)
- `VE_SPREAD_HALF = 2`, `VE_QUOTE_SIZE = 5` (VE passive quoting)
- `pos_reserve = 30` (VEV capacity buffer)

#### Structural Risk: Short Gamma Drawdown

The ~16k drawdown (t=43k→73k) is **unavoidable** — identical across ALL versions including 518982:
- Aggregate option delta = **-758** (short calls across 5 ATM strikes)
- VE moves +20 points during spike → -758 × 20 = **-15,160 loss**
- Loss fully reverses when VE mean-reverts → final P&L positive
- VE limit = 200 units = can only hedge ~26% of delta exposure

#### Techniques Tested but Rejected (v6→v13)

| Technique | Version | Result | Lesson |
|-----------|---------|--------|--------|
| VE price-skew delta hedge | v11 | VE: -647 (vs -50) | Skewing ±2 ticks buys above fair → bleeds -597/day |
| VE size-only delta hedge | v12 ✅ | VE: -152 | Bias quote sizes, not prices — accumulates hedge at fair |
| Mark 67 momentum buy VE | v13 | VE: -2,310 | M67 only 38 lots/day. Buying at ask is expensive → false signals cost -75 each |
| Mark 55 fading on VE | v13 | Included in loss | M55 moves persist > 1 tick, fade at ±2 too tight |
| Tighter Mark 01 taker (0.40x) | v13 | VEV_5000: -59 | Too aggressive — buys before market justifies it |
| Lower pos_reserve (20) | v13 | Included in -59 | More exposure ≠ more profit with wrong edge |
| IV smile scalping (Frankfurt style) | Researched | Not implemented | Requires pre-fitted smile coefficients; risk of overfitting to 4 days of data |

#### External Research: Frankfurt Hedgehogs (2nd Global, Prosperity 3)

Their top strategy: **IV smile scalping** (100-150k/round)
- Fit quadratic vol smile: `IV = a·m² + b·m + c` where `m = ln(K/S)/√TTE`
- Pre-fitted coefficients: `[0.27362531, 0.01007566, 0.14876677]`
- Trade deviations of market price from smile-implied BS theo price
- Combined with EMA-based mean reversion on underlying
- Delta hedging was **not** primary PnL driver — IV scalping was

Their 518982 competitor's VE approach (4-layer delta hedge + Mark 67 momentum + Mark 67/49 spread + MM) lost **-9,754 on VE** — a net negative strategy.

#### Supported Libraries (from wiki)

| Library | Version | Used? |
|---------|---------|-------|
| `numpy` | 1.24.2 | Imported in v13 (available for future IV smile work) |
| `pandas` | 1.5.3 | Not used |
| `math` | stdlib | ✅ BS pricing |
| `json` | stdlib | ✅ State persistence |
| `typing` | stdlib | ✅ Type hints |
| `jsonpickle` | 3.0.1 | Not used |

#### Final Performance (v12 — Official Platform)

| Metric | Value |
|--------|-------|
| **Total P&L** | **+26,309 XIRECs** |
| **Max Drawdown** | 16,826 |
| **P&L / DD Ratio** | 1.56 |
| **vs Theoretical Max** | 89% captured |
| **vs Best Competitor (518982)** | **+60% better** |

| Product | P&L |
|---------|-----|
| VEV_5100 | +9,417 |
| VEV_5200 | +7,905 |
| VEV_5300 | +4,850 |
| VEV_5000 | +2,516 |
| HP | +883 |
| VEV_5500 | +728 |
| VEV_4000 | +162 |
| VE | -152 |

---

## Round 3 (Phase 2 — GOAT)

**Products:** HYDROGEL_PACK (200), VELVETFRUIT_EXTRACT (200), VEV ×10 (300 each)  
**Data:** 3 days (day 0, 1, 2) — `data/round3/`  
**Duration:** April 25 – April 26 (48 hours)  
**VEV TTE:** 5 days at start of Round 3 (8d at day 0, 7d at day 1, 6d at day 2 in historical data)

### Algorithmic: "Options Require Decisions"

**Product types:**
- **Delta-1:** `HYDROGEL_PACK`, `VELVETFRUIT_EXTRACT` — similar to R1/R2 products
- **Options:** 10 VEV vouchers with strikes: 4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500

**VEV voucher specs:**
- European call options on VELVETFRUIT_EXTRACT
- 7-day expiration from Round 1 (TTE decreases each round)
- Cannot be exercised early; auto-liquidated at hidden fair value at round end
- Inventory does NOT carry over between rounds

| Status | Notes |
|--------|-------|
| Strategy | TBD — requires Black-Scholes or Monte Carlo for VEV pricing |
| Historical data | 3 days available in `data/round3/` |

### Manual: "The Celestial Gardeners' Guild"

Buy Ornamental Bio-Pods from counterparties. Sell next day at fair price **920**.

- Counterparty reserve prices: **uniform** on [670, 920] at **increments of 5**
- Submit **2 bids** (b1 and b2)
- b1 > reserve → trade at b1
- b2 > reserve AND b2 > avg(all b2) → trade at b2
- b2 > reserve BUT b2 ≤ avg(all b2) → trade at b2 with penalty: `((920 - avg_b2) / (920 - b2))^3`

| Status | Notes |
|--------|-------|
| Strategy | TBD — game theory: need to estimate avg b2 from population |

---

## Round 1

**Products:** ASH_COATED_OSMIUM (pos limit 80), INTARIAN_PEPPER_ROOT (pos limit 80)  
**Data:** 3 days (day -2, -1, 0) — bundled in `prosperity4btest`

### Algorithmic Trading

Same products and dynamics as Round 2. The `trader.py` algorithm was developed on Round 2 data (priority) and validated on Round 1:

| Day | ACO | IPR | Total |
|-----|-----|-----|-------|
| Day -2 | +6,934 | +77,932 | **+84,866** |
| Day -1 | +7,622 | +78,290 | **+85,912** |
| Day 0 | +7,398 | +78,309 | **+85,707** |
| **Total** | **+21,954** | **+234,531** | **+256,484** |

---

## Environment & Tools

| Tool | Version | Purpose |
|------|---------|---------| 
| `prosperity4btest` | 1.0.1 | Backtester |
| Python | 3.13 | Runtime |
| Round 2 data | `ROUND_2.zip` | 3 days of prices + trades |
| Round 3 data | `data/round3/` | 3 days (day 0, 1, 2) |
| Round 4 data | `ROUND_4.zip` | 3 days (day 1, 2, 3) + counterparty IDs |

### Backtester Commands
```bash
# Round 4 (MUST use --limit flags)
prosperity4btest trader.py 4 --data /mnt/d/workspace/IMC-4/data --no-progress \
  --limit HYDROGEL_PACK:200 --limit VELVETFRUIT_EXTRACT:200 \
  --limit VEV_4000:300 --limit VEV_4500:300 --limit VEV_5000:300 \
  --limit VEV_5100:300 --limit VEV_5200:300 --limit VEV_5300:300 \
  --limit VEV_5400:300 --limit VEV_5500:300 --limit VEV_6000:300 \
  --limit VEV_6500:300

# Round 2 (old version)
prosperity4btest trader_v2_round2.py 2 --data /mnt/d/workspace/IMC-4/data --no-progress
```

---

## File Structure

```
IMC-4/
├── trader.py                 # Current algorithm (R4 v12 — production)
├── trader_v12_round4.py      # R4 v12 backup (best: +26,309)
├── trader_v13_round4.py      # R4 v13 backup (reverted: +23,936)
├── trader_v11_round4.py      # R4 v11 backup (+25,814)
├── trader_v6_round4.py       # R4 v6 baseline (+25,220)
├── trader_v2_round2.py       # R2 version backup (ACO + IPR)
├── uploaded_version.py       # Original baseline (R2)
├── datamodel.py              # Data model (synced with wiki)
├── CHANGELOG.md              # This file
├── data/round2/              # Extracted round 2 CSVs
├── data/round3/              # Round 3 data
├── data/round4/              # Round 4 data (with counterparty IDs)
├── docs/                     # Documentation + wiki
├── 518982.zip                # Competitor reference log
├── v7result.zip → v13result.zip  # Official platform result logs
└── __pycache__/              # Python cache (gitignored)
```


