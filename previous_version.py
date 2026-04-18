from datamodel import OrderDepth, TradingState, Order
from typing import List

class Trader:

    def run(self, state: TradingState):
        result = {}
        LIMIT = 80

        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []
            pos = state.position.get(product, 0)

            best_ask = min(order_depth.sell_orders) if order_depth.sell_orders else None
            best_bid = max(order_depth.buy_orders) if order_depth.buy_orders else None

            # ── INTARIAN_PEPPER_ROOT: buy & hold the drift ──────────────────
            if product == "INTARIAN_PEPPER_ROOT":
                ts = state.timestamp
                fair = 13000 + ts * 0.001

                liquidating = ts >= 99000  # hold as long as possible

                # Phase 1: accumulate aggressively — not liquidating
                if not liquidating and pos < LIMIT and best_ask is not None and best_ask <= fair + 8:
                    qty = min(LIMIT - pos, -order_depth.sell_orders[best_ask])
                    if qty > 0:
                        orders.append(Order(product, best_ask, qty))

                # Phase 2: passive exit at fair-3 — becomes best ask, fills fast
                # Active bidders are present 48/50 ticks at end of day
                if liquidating and pos > 0:
                    passive_ask = round(fair) - 3  # better than market bid by ~4
                    orders.append(Order(product, passive_ask, -pos))

            # ── ASH_COATED_OSMIUM: tight market make around 10000 ───────────
            elif product == "ASH_COATED_OSMIUM":
                fair = 10000
                spread = 4
                our_bid = fair - spread   # 9996
                our_ask = fair + spread   # 10004

                # Take mispriced orders
                if best_ask is not None and best_ask <= our_bid and pos < LIMIT:
                    qty = min(LIMIT - pos, -order_depth.sell_orders[best_ask])
                    if qty > 0:
                        orders.append(Order(product, best_ask, qty))

                if best_bid is not None and best_bid >= our_ask and pos > -LIMIT:
                    qty = min(LIMIT + pos, order_depth.buy_orders[best_bid])
                    if qty > 0:
                        orders.append(Order(product, best_bid, -qty))

                # Post passive quotes
                buy_capacity = LIMIT - pos
                sell_capacity = LIMIT + pos
                if buy_capacity > 0:
                    orders.append(Order(product, our_bid, min(buy_capacity, 15)))
                if sell_capacity > 0:
                    orders.append(Order(product, our_ask, -min(sell_capacity, 15)))

            result[product] = orders

        return result, 0, ""