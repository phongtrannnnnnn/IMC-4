# Round 1 - "Trading Groundwork"

> Source: https://imc-prosperity.notion.site/round-1-trading-groundwork

## Overview

You have reached Intara. You establish a Trade Outpost on the dry and arid landscape, overlooking endless dusty plateaus, jagged rock formations, and ancient impact craters. This outpost will serve as your trading hub for the duration of your mission on Intara.

**Goal:** Earn a net profit of **200,000 XIRECs** or more before the beginning of the third trading day. Only then will your outpost be acknowledged by the *eXtended Interplanetary Resource Exchange Network* (XIREN) as an official trading node.

Trading days on Intara last **72 hours**, giving you ample time to develop a solid strategy for both algorithmic and manual trading challenges.

## Round Objective

Translate your first trading strategy into a Python program that trades `ASH_COATED_OSMIUM` and `INTARIAN_PEPPER_ROOT` on your behalf. In addition to deploying your first official trading algorithm, participate in the Exchange Auction to generate additional profit.

---

## Algorithmic Trading Challenge: "First Intarian Goods"

### Products & Position Limits

| Product | Position Limit | Behavior |
|---------|---------------|----------|
| `INTARIAN_PEPPER_ROOT` | **80** | A steady value, slow-growing root — comparable to EMERALDS in the tutorial |
| `ASH_COATED_OSMIUM` | **80** | Volatile, ash-coated osmium nugget — may follow a **hidden pattern** in its unpredictability |

---

## Manual Trading Challenge: "An Intarian Welcome"

The Intarian people are organizing a celebratory **Exchange Auction** to welcome you to their planet. This auction provides an opportunity to generate additional profit alongside your algorithmic earnings.

### Mechanism: Opening Auctions

You submit orders **last**. No other bids or asks will arrive after you place your order.

### Auction Rules

1. You submit a **single limit order** (price, quantity). When the auction ends, the exchange selects a single **clearing price** that:
   - **Maximizes total traded volume**, then
   - Breaks ties by choosing the **higher price**
2. All bids with price ≥ clearing price and asks with price ≤ clearing price execute at the clearing price
3. Allocation is **price priority**, then **time priority**. Since you are last to submit, you are last in line at any price level you join

### Products & Guaranteed Buyback

You will **not** trade these products in continuous trading. Instead, right after the auction the Merchant Guild will buy any inventory you trade at a fixed price:

| Product | Buyback Price | Fees |
|---------|---------------|------|
| `DRYLAND_FLAX` | **30** per unit | No fees |
| `EMBER_MUSHROOM` | **20** per unit | Fee of **0.10** per unit traded |

### How to Submit

Choose a bid price and quantity for each product to maximize your profit. Enter your orders directly in the **Manual Challenge Overview** window and click the "Submit" button. You can re-submit new orders until the end of the trading round. When the round ends, the last submitted orders will be executed.

---

## Key Notes

- This round's P&L counts toward your leaderboard score
- Manual and algorithmic P&L are **independent** — manual results do not affect algorithmic performance
- Your algorithm must return orders for all active products
- Position limits are enforced per-product — orders exceeding the limit are rejected entirely
