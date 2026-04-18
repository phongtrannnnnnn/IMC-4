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

            if best_bid is None or best_ask is None:
                result[product] = orders
                continue

            mid = (best_bid + best_ask) / 2

            if product == "INTARIAN_PEPPER_ROOT":

                fair = mid

               
                skew = -pos * 0.05

                buy_price = int(fair - 2 + skew)
                sell_price = int(fair + 2 + skew)

               
                if best_ask < fair - 3 and pos < LIMIT:
                    qty = min(LIMIT - pos, -order_depth.sell_orders[best_ask])
                    orders.append(Order(product, best_ask, qty))

                if best_bid > fair + 3 and pos > -LIMIT:
                    qty = min(LIMIT + pos, order_depth.buy_orders[best_bid])
                    orders.append(Order(product, best_bid, -qty))

              
                buy_size = min(40, LIMIT - pos)
                sell_size = min(40, LIMIT + pos)

                if buy_size > 0:
                    orders.append(Order(product, buy_price, buy_size))

                if sell_size > 0:
                    orders.append(Order(product, sell_price, -sell_size))

            elif product == "ASH_COATED_OSMIUM":

             
                bid_vol = sum(order_depth.buy_orders.values())
                ask_vol = -sum(order_depth.sell_orders.values())

                if bid_vol + ask_vol == 0:
                    imbalance = 0.5
                else:
                    imbalance = bid_vol / (bid_vol + ask_vol)

             
                fair = mid

                if imbalance > 0.6:
                    fair += 2
                elif imbalance < 0.4:
                    fair -= 2

               
                skew = -pos * 0.05

                buy_price = int(fair - 2 + skew)
                sell_price = int(fair + 2 + skew)

            
                if best_ask < fair - 2 and pos < LIMIT:
                    qty = min(LIMIT - pos, -order_depth.sell_orders[best_ask])
                    orders.append(Order(product, best_ask, qty))

                if best_bid > fair + 2 and pos > -LIMIT:
                    qty = min(LIMIT + pos, order_depth.buy_orders[best_bid])
                    orders.append(Order(product, best_bid, -qty))

               
                buy_size = min(35, LIMIT - pos)
                sell_size = min(35, LIMIT + pos)

                if buy_size > 0:
                    orders.append(Order(product, buy_price, buy_size))

                if sell_size > 0:
                    orders.append(Order(product, sell_price, -sell_size))

            result[product] = orders

        return result, 0, ""