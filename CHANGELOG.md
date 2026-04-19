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
| Round 2 data | `ROUND_2.zip` → `data/round2/` | 3 days of prices + trades |

### Backtester Commands
```bash
# Round 2
prosperity4btest trader.py 2 --data /mnt/d/workspace/IMC-4/data --no-progress

# Round 1
prosperity4btest trader.py 1 --no-progress

# Conservative fills
prosperity4btest trader.py 2 --data /mnt/d/workspace/IMC-4/data --match-trades worse --no-progress
```

---

## File Structure

```
IMC-4/
├── trader.py                 # Final algorithm (SUBMIT THIS)
├── uploaded_version.py       # Original baseline
├── datamodel.py              # Data model (synced with wiki)
├── CHANGELOG.md              # This file
├── ROUND_2.zip               # Raw round 2 data
├── data/round2/              # Extracted round 2 CSVs
│   ├── prices_round_2_day_{-1,0,1}.csv
│   └── trades_round_2_day_{-1,0,1}.csv
└── docs/
    ├── imc_prosperity4_wiki.md
    ├── rounds/{tutorial,round1,round2}.md
    └── elearning/{trading_glossary,programming_resources}.md
```
