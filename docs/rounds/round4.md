# Round 4 - "The More The Merrier"

> Source: https://imc-prosperity.notion.site/Round-4-The-More-The-Merrier

## Overview

For this round, the **Frontier Trade Watch (FTW)** has disclosed information about the counterparties active in the market. Participant IDs have been added to the historical trade data in the Data Capsule. You will continue trading **Hydrogel Packs** (`HYDROGEL_PACK`), **Velvetfruit Extract** (`VELVETFRUIT_EXTRACT`), and **10 Velvetfruit Extract Vouchers** (`VELVETFRUIT_EXTRACT_VOUCHER`).

Additionally, a manual trading challenge is introduced involving the **Aether Crystal** and various exotic option contracts.

---

## Round Objective

Optimize your Python strategy to trade the existing products while incorporating newly disclosed counterparty information. In addition, manually trade Aether Crystal and a collection of vanilla and exotic options.

---

## Algorithmic Trading Challenge: "Hello, I'm Mark"

### New Mechanics: Counterparty Identification

The `Trade` class in `datamodel.py` now includes `buyer` and `seller` attributes containing the **names of the market participants**. In previous rounds, these fields were `None`.

```python
class Trade:
    def __init__(self, symbol: Symbol, price: int, quantity: int,
                 buyer: UserId = None, seller: UserId = None,
                 timestamp: int = 0):
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.buyer = buyer
        self.seller = seller
        self.timestamp = timestamp
```

> **Key Insight**: You can now identify WHO is trading — analyze counterparty behavior patterns (e.g., informed traders, noise traders, market makers) to improve your strategy.

### Products & Position Limits

| Product | Position Limit |
|---------|---------------|
| `HYDROGEL_PACK` | **200** |
| `VELVETFRUIT_EXTRACT` | **200** |
| `VELVETFRUIT_EXTRACT_VOUCHER` | **300** (each of 10 vouchers) |

> Products and position limits are unchanged from Round 3.

---

## Manual Trading Challenge: "Vanilla Just Isn't Exotic Enough"

Trade the **Aether Crystal** (`AETHER_CRYSTAL`) and a collection of vanilla and exotic options.

### Underlying Simulation Parameters

The Aether Crystal price is simulated using **Geometric Brownian Motion (GBM)** with the following parameters:

| Parameter | Value |
|-----------|-------|
| Risk-neutral drift | **0** |
| Annualized volatility | **251%** |
| Trading days per year | **252** |
| Steps per day | **4** |
| Contract size (PnL multiplier) | **3,000** |
| Total simulations | **100** |

### Exotic Option Types

#### 1. Chooser Option
- Expires in **3 weeks**
- After **2 weeks**, the buyer chooses whether it becomes a **call** or a **put** (whichever is in-the-money)
- Behaves as a standard option for the final week until expiry

#### 2. Binary Put Option
- **All-or-nothing** payoff
- If the underlying is **below the strike** at expiry, it pays the specified amount
- Otherwise, it expires **worthless**

#### 3. Knock-Out Put Option
- Behaves like a **regular put** unless the underlying trades below a specific **knockout barrier** at any point before expiry
- If the barrier is breached, the option immediately becomes **worthless**

### Submission

Submit orders for the Aether Crystal and its options directly in the **Manual Challenge Overview** window. Orders can be re-submitted until the end of the trading round; the last submitted orders are processed.

---

## Key Notes

- Same algorithmic products as Round 3 — no new tradable products added
- **NEW**: Counterparty IDs visible in trade data (`buyer` / `seller` fields)
- VEV voucher TTE continues decreasing: TTE = **4 days** at start of Round 4
- Manual challenge introduces **exotic options** requiring Monte Carlo or analytical pricing
- GBM parameters: 0 drift, 251% annualized vol — extremely high volatility environment
- Contract size of 3,000 makes manual challenge a significant P&L contributor
