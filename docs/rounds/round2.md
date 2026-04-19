# Round 2 - "Growing Your Outpost"

> Source: https://imc-prosperity.notion.site/Round-2-Growing-Your-Outpost

## Overview

It is the second trading round and the **final opportunity** to reach the threshold goal of a net PnL of **200,000 XIRECs** or more before the leaderboard resets for Phase 2. These first two rounds act as **qualifiers** for the final mission.

Trading activity has accelerated significantly since your arrival. With you and the other outposts actively trading **Ash-Coated Osmium** and **Intarian Pepper Root**, the market has become increasingly competitive and dynamic.

## Round Objective

Optimize your Python program to trade `ASH_COATED_OSMIUM` and `INTARIAN_PEPPER_ROOT`, and include a **Market Access Fee (MAF)** bid in your program to gain access to additional market volume.

---

## Algorithmic Trading Challenge: "Limited Market Access"

In this round, you can bid for **25% more quotes** in the order book. The volumes and prices of these extra quotes fit perfectly into the distribution of the already available quotes.

### Products & Position Limits

| Product | Position Limit |
|---------|---------------|
| `ASH_COATED_OSMIUM` | **80** |
| `INTARIAN_PEPPER_ROOT` | **80** |

### The `bid()` Function

Traders must implement a `bid()` function in their `Trader` class that returns an integer representing their bid in XIRECs:

```python
class Trader:
    def bid(self) -> int:
        return 15  # Example bid

    def run(self, state: TradingState):
        # Trading logic here
        ...
```

### Market Access Fee (MAF) Mechanics

- The MAF is a **one-time fee** paid only if your bid is accepted
- The **top 50% of bids** across all participants are accepted (those higher than the median bid)
- **Accepted bidders**: Pay the price they bid and receive the 25% extra flow
- **Rejected bidders**: Pay nothing and receive no extra flow
- **Profit calculation (for accepted bids)**: `profit = profit from round 2 - bid for getting full market access`

### Testing vs. Final Simulation

- **During testing**: You interact with **80% of all generated quotes** (randomized), reflecting real-world conditions. The `bid()` function is ignored during testing
- **Final simulation**: The `bid()` function runs as a "blind auction" — your bid competes against all other participants

---

## Manual Trading Challenge: "Invest & Expand"

You are expanding your outpost into a market-making firm with a budget of **50,000 XIRECs**. You must allocate this budget across three growth pillars as percentages (0–100%, total not exceeding 100%).

### PnL Formula

```
PnL = (Research × Scale × Speed) − Budget_Used
```

### The Three Pillars

#### 1. Research (Trading Edge)

- Determines the strength of your trading edge
- Grows **logarithmically** from 0 (at 0% invested) to 200,000 (at 100% invested)
- **Formula**: `research(x) = 200,000 * np.log(1 + x) / np.log(1 + 100)`

#### 2. Scale (Market Breadth)

- Determines how broadly you deploy your strategy across markets
- Grows **linearly** from 0 (at 0% invested) to 7 (at 100% invested)

#### 3. Speed (Trade Hit Rate)

- Determines how often you win the trades you target
- **Rank-based** across all players:
  - Highest speed investment receives a **0.9** multiplier
  - Lowest receives **0.1** multiplier
  - Everyone in between is scaled linearly by rank
  - Equal investments share the same rank
- **Example**: If people invested `[70, 70, 70, 50, 40, 40, 30]`, their ranks are `[1, 1, 1, 4, 5, 5, 7]`. The first three get 0.9, the last gets 0.1, and others are scaled in between.

### Submission

Distributions are submitted via the **Manual Challenge Overview** window. You can re-submit until the end of the round; the last submission is locked in and processed.

---

## Key Notes

- Rounds 1 & 2 are **Phase 1 qualifiers** — the leaderboard **resets** for Phase 2 (Rounds 3, 4, 5)
- You must reach **200,000 XIRECs** by the end of Round 2 to qualify for Phase 2
- Manual and algorithmic P&L are **independent** of each other
- The `bid()` function must return an `int`
