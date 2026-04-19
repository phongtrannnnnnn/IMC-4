from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json
import math


class Trader:
    """
    Round 2 algorithm — optimized via parameter sweep + structural improvements.

    ASH_COATED_OSMIUM: AR(1) mean-reverting oscillator around 10,000
        autocorr(1) = -0.47, std ≈ 4-5, market spread ≈ 16, L1 vol ≈ 14, L2 ≈ 42%

    INTARIAN_PEPPER_ROOT: Deterministic linear trend 0.001/timestamp
        R² = 0.99997, residual std ≈ 1.6, residual autocorr(1) = -0.49
    """

    LIMIT = 80

    # ══════════════════════════════════════════════════════════
    #  ACO PARAMETERS — sweep-optimized
    # ══════════════════════════════════════════════════════════
    ACO_ANCHOR = 10000
    ACO_EMA_WEIGHT = 0.50        # ← sweep: 0.5 > 0.25 (+4.5k)
    ACO_AR_COEFF = -0.30         # ← sweep: -0.3 > -0.47 (+4.5k)
    ACO_SPREAD_HALF = 3          # ← sweep: 3 > 2 (+7.3k)
    ACO_TAKE_THRESHOLD = 2.5     # ← sweep: 2.5 > 1.5 (+7.3k)
    ACO_SKEW_COEFF = 0.10        # ← sweep: 0.10 best
    ACO_BASE_SIZE = 22
    ACO_COOLDOWN = 150
    ACO_PROFIT_EXIT = 3.0
    ACO_L2_OFFSET = 3            # L2 quote offset from L1 (data: avg 2.8)
    ACO_L2_SIZE_FRAC = 0.6       # L2 size as fraction of L1 size

    # ══════════════════════════════════════════════════════════
    #  IPR PARAMETERS — sweep-optimized
    # ══════════════════════════════════════════════════════════
    IPR_SLOPE = 0.001
    IPR_RESIDUAL_STD = 1.6
    IPR_AR_COEFF = -0.49
    IPR_ACCUM_THRESHOLD = 2.5    # ← sweep: 2.5 > 1.5 (+2.6k). Buy more aggressively
    IPR_SPIKE_EXIT_Z = 3.0       # ← sweep: 3.0 > 2.0 (+2.6k). Almost never sell
    IPR_COOLDOWN = 500
    IPR_MIN_HOLD = 30

    # ══════════════════════════════════════════════════════════
    #  ROLLING WINDOW
    # ══════════════════════════════════════════════════════════
    WINDOW = 50

    def bid(self) -> int:
        """Market Access Fee. Top 50% get 25% extra quotes."""
        return 150

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        s = self._load_state(state.traderData)
        ts = state.timestamp

        for product, order_depth in state.order_depths.items():
            pos = state.position.get(product, 0)
            best_ask = min(order_depth.sell_orders) if order_depth.sell_orders else None
            best_bid = max(order_depth.buy_orders) if order_depth.buy_orders else None

            if best_bid is None or best_ask is None:
                result[product] = []
                continue

            mid = (best_bid + best_ask) / 2

            if product == "ASH_COATED_OSMIUM":
                result[product] = self._trade_aco(order_depth, pos, mid, ts, s)
            elif product == "INTARIAN_PEPPER_ROOT":
                result[product] = self._trade_ipr(order_depth, pos, mid, ts, s)
            else:
                result[product] = []

        return result, 0, json.dumps(s)

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  ASH_COATED_OSMIUM — Sweep-Optimized Mean-Reversion            ║
    # ╚══════════════════════════════════════════════════════════════════╝

    def _trade_aco(self, od: OrderDepth, pos: int, mid: float,
                   ts: int, s: dict) -> List[Order]:
        orders: List[Order] = []
        P = "ASH_COATED_OSMIUM"

        # ── Rolling window + EMA ──
        prices = s.setdefault("aco_p", [])
        prices.append(mid)
        if len(prices) > self.WINDOW:
            prices[:] = prices[-self.WINDOW:]

        ema = self._ema(prices, 12) if len(prices) >= 5 else mid
        fair_base = (1 - self.ACO_EMA_WEIGHT) * self.ACO_ANCHOR + self.ACO_EMA_WEIGHT * ema

        # ── AR(1) next-tick prediction ──
        if len(prices) >= 2:
            last_change = prices[-1] - prices[-2]
            ar_predict = fair_base + self.ACO_AR_COEFF * last_change
        else:
            ar_predict = fair_base

        fair = ar_predict

        # ── Volatility ──
        rolling_std = self._std(prices[-20:]) if len(prices) >= 20 else 5.0
        rolling_std = max(rolling_std, 1.0)
        vol_ratio = rolling_std / 4.5

        # ── Z-score ──
        z = (mid - self.ACO_ANCHOR) / rolling_std

        # ── Book imbalance signal ──
        # Data shows: high bid imbalance → +0.27 avg return, low → -0.23
        total_bid = sum(od.buy_orders.values())
        total_ask = -sum(od.sell_orders.values())
        if total_bid + total_ask > 0:
            imbalance = total_bid / (total_bid + total_ask)
        else:
            imbalance = 0.5
        # Shift fair value toward imbalance direction
        imb_adj = (imbalance - 0.5) * 0.8  # ±0.4 max adjustment
        fair += imb_adj

        # ── Inventory skew ──
        skew = -pos * self.ACO_SKEW_COEFF

        # ── Dynamic spread ──
        spread_half = self.ACO_SPREAD_HALF  # 3 (sweep-optimized)
        if vol_ratio > 2.0:
            spread_half = 4
        elif vol_ratio < 0.6:
            spread_half = 2

        buy_price_l1 = int(fair - spread_half + skew)
        sell_price_l1 = int(fair + spread_half + skew)

        # ── Cooldown ──
        last_take = s.get("aco_lt", 0)
        can_take = (ts - last_take) >= self.ACO_COOLDOWN

        # ── 1. Aggressive takes ──
        if can_take:
            take_buy = fair - self.ACO_TAKE_THRESHOLD
            take_sell = fair + self.ACO_TAKE_THRESHOLD

            for ask_price in sorted(od.sell_orders.keys()):
                if ask_price < take_buy and pos < self.LIMIT:
                    vol = -od.sell_orders[ask_price]
                    qty = min(vol, self.LIMIT - pos)
                    if qty > 0:
                        orders.append(Order(P, ask_price, qty))
                        pos += qty
                        s["aco_lt"] = ts
                        self._track_entry(s, "aco", ask_price, qty)

            for bid_price in sorted(od.buy_orders.keys(), reverse=True):
                if bid_price > take_sell and pos > -self.LIMIT:
                    vol = od.buy_orders[bid_price]
                    qty = min(vol, self.LIMIT + pos)
                    if qty > 0:
                        orders.append(Order(P, bid_price, -qty))
                        pos -= qty
                        s["aco_lt"] = ts
                        self._track_entry(s, "aco", bid_price, -qty)

        # ── 2. Inventory management ──
        avg_entry = self._avg_entry(s, "aco")
        if avg_entry is not None:
            if pos > 0:
                ppu = mid - avg_entry
                if ppu > self.ACO_PROFIT_EXIT and pos > 10:
                    exit_qty = min(pos - 5, 20)
                    orders.append(Order(P, max(int(mid - 0.5), buy_price_l1), -exit_qty))
                elif abs(z) < 0.3 and pos > 30:
                    flatten_qty = min(pos - 15, 10)
                    if flatten_qty > 0:
                        orders.append(Order(P, int(fair), -flatten_qty))
            elif pos < 0:
                ppu = avg_entry - mid
                if ppu > self.ACO_PROFIT_EXIT and pos < -10:
                    exit_qty = min(-pos - 5, 20)
                    orders.append(Order(P, min(int(mid + 0.5), sell_price_l1), exit_qty))
                elif abs(z) < 0.3 and pos < -30:
                    flatten_qty = min(-pos - 15, 10)
                    if flatten_qty > 0:
                        orders.append(Order(P, int(fair), flatten_qty))

        # ── 3. Multi-level quoting ──
        abs_pos = abs(pos)
        vol_size_factor = max(0.5, min(1.5, 1.0 / vol_ratio))
        inv_size_factor = max(0.3, 1.0 - max(0, abs_pos - 30) * 0.02)
        l1_size = int(self.ACO_BASE_SIZE * vol_size_factor * inv_size_factor)
        l1_size = max(3, l1_size)
        l2_size = max(2, int(l1_size * self.ACO_L2_SIZE_FRAC))

        buy_cap = self.LIMIT - pos
        sell_cap = self.LIMIT + pos

        # L1 quotes
        l1_buy = min(l1_size, buy_cap)
        l1_sell = min(l1_size, sell_cap)
        if l1_buy > 0:
            orders.append(Order(P, buy_price_l1, l1_buy))
            buy_cap -= l1_buy
        if l1_sell > 0:
            orders.append(Order(P, sell_price_l1, -l1_sell))
            sell_cap -= l1_sell

        # L2 quotes — wider spread, catches big moves
        buy_price_l2 = buy_price_l1 - self.ACO_L2_OFFSET
        sell_price_l2 = sell_price_l1 + self.ACO_L2_OFFSET
        l2_buy = min(l2_size, buy_cap)
        l2_sell = min(l2_size, sell_cap)
        if l2_buy > 0:
            orders.append(Order(P, buy_price_l2, l2_buy))
        if l2_sell > 0:
            orders.append(Order(P, sell_price_l2, -l2_sell))

        # ── 4. EOD liquidation ──
        if ts > 985000 and abs(pos) > 3:
            if pos > 0:
                orders.append(Order(P, int(fair - 1), -pos))
            else:
                orders.append(Order(P, int(fair + 1), -pos))

        return orders

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  INTARIAN_PEPPER_ROOT — Sweep-Optimized Trend Accumulator      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    def _trade_ipr(self, od: OrderDepth, pos: int, mid: float,
                   ts: int, s: dict) -> List[Order]:
        orders: List[Order] = []
        P = "INTARIAN_PEPPER_ROOT"

        # ── Rolling window ──
        prices = s.setdefault("ipr_p", [])
        prices.append(mid)
        if len(prices) > self.WINDOW:
            prices[:] = prices[-self.WINDOW:]

        if "ipr_int" not in s:
            s["ipr_int"] = mid
            s["ipr_ts0"] = ts

        elapsed = ts - s["ipr_ts0"]
        fair_trend = s["ipr_int"] + self.IPR_SLOPE * elapsed

        # ── AR(1) on residuals ──
        residual = mid - fair_trend
        if len(prices) >= 2:
            prev_res = prices[-2] - (s["ipr_int"] + self.IPR_SLOPE * (elapsed - 100))
            ar_adj = self.IPR_AR_COEFF * (residual - prev_res)
        else:
            ar_adj = 0.0

        fair_ar = fair_trend + ar_adj
        z = residual / self.IPR_RESIDUAL_STD

        # ── Cooldown ──
        last_sell_ts = s.get("ipr_ls", 0)
        sell_cooldown = (ts - last_sell_ts) >= self.IPR_COOLDOWN

        # ── 1. Aggressive accumulation ──
        # sweep ALL asks at/below fair + 2.5 (sweep-optimized)
        if pos < self.LIMIT:
            buy_up_to = fair_ar + self.IPR_ACCUM_THRESHOLD
            for ask_price in sorted(od.sell_orders.keys()):
                if ask_price <= buy_up_to and pos < self.LIMIT:
                    vol = -od.sell_orders[ask_price]
                    qty = min(vol, self.LIMIT - pos)
                    if qty > 0:
                        orders.append(Order(P, ask_price, qty))
                        pos += qty
                        self._track_entry(s, "ipr", ask_price, qty)

        # ── 2. Multi-level passive buying ──
        buy_cap = self.LIMIT - pos
        if buy_cap > 0:
            # L1: at fair, aggressive size
            l1_size = min(buy_cap, 30 if pos < 40 else 20 if pos < 60 else 10)
            l1_price = int(fair_ar)
            orders.append(Order(P, l1_price, l1_size))
            buy_cap -= l1_size

            # L2: slightly below, catch dips
            if buy_cap > 0:
                l2_size = min(buy_cap, 15)
                l2_price = int(fair_ar - 2)
                orders.append(Order(P, l2_price, l2_size))

        # ── 3. Sell on extreme spikes only (z > 3.0, sweep-optimized) ──
        if z > self.IPR_SPIKE_EXIT_Z and pos > self.IPR_MIN_HOLD and sell_cooldown:
            sell_qty = min(pos - self.IPR_MIN_HOLD, 15)
            if sell_qty > 0:
                for bid_price in sorted(od.buy_orders.keys(), reverse=True):
                    if bid_price >= fair_trend + 1 and sell_qty > 0:
                        vol = od.buy_orders[bid_price]
                        qty = min(vol, sell_qty)
                        if qty > 0:
                            orders.append(Order(P, bid_price, -qty))
                            sell_qty -= qty
                            pos -= qty
                s["ipr_ls"] = ts

        # ── 4. Profit-taking on extreme gains ──
        avg_entry = self._avg_entry(s, "ipr")
        if avg_entry is not None and pos > 50 and sell_cooldown:
            if mid - avg_entry > 10:
                tp_qty = min(pos - 40, 10)
                if tp_qty > 0:
                    orders.append(Order(P, int(mid), -tp_qty))
                    s["ipr_ls"] = ts

        return orders

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  Utilities                                                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    @staticmethod
    def _ema(prices: list, span: int = 10) -> float:
        alpha = 2.0 / (span + 1)
        ema = prices[0]
        for p in prices[1:]:
            ema = alpha * p + (1 - alpha) * ema
        return ema

    @staticmethod
    def _std(data: list) -> float:
        if len(data) < 2:
            return 1.0
        mean = sum(data) / len(data)
        var = sum((x - mean) ** 2 for x in data) / (len(data) - 1)
        return max(math.sqrt(var), 0.01)

    @staticmethod
    def _best_executable(book: dict, side: str = "ask"):
        if not book:
            return None, 0
        total_vol = 0
        if side == "ask":
            best = min(book.keys())
            for price in sorted(book.keys()):
                total_vol += abs(book[price])
        else:
            best = max(book.keys())
            for price in sorted(book.keys(), reverse=True):
                total_vol += book[price]
        return best, total_vol

    @staticmethod
    def _track_entry(s: dict, prefix: str, price: int, signed_qty: int):
        s[f"{prefix}_cs"] = s.get(f"{prefix}_cs", 0.0) + price * signed_qty
        s[f"{prefix}_cq"] = s.get(f"{prefix}_cq", 0) + signed_qty

    @staticmethod
    def _avg_entry(s: dict, prefix: str):
        cs = s.get(f"{prefix}_cs", 0.0)
        cq = s.get(f"{prefix}_cq", 0)
        return cs / cq if cq != 0 else None

    @staticmethod
    def _load_state(td: str) -> dict:
        if td:
            try:
                return json.loads(td)
            except (json.JSONDecodeError, TypeError):
                pass
        return {}
