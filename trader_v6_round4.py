from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json
import math


class Trader:
    """
    Round 4 algorithm — HYDROGEL_PACK, VELVETFRUIT_EXTRACT, VEV vouchers.
    Max orders per product per tick: kept well under 50.

    HYDROGEL_PACK: Mean-reversion MM, spread ~16, autocorr=-0.12
    VELVETFRUIT_EXTRACT: Mean-reversion MM, spread ~5, autocorr=-0.16
    VEV vouchers: BS-priced market making on ATM strikes

    Counterparty intelligence:
      Mark 14: Informed on HP (+8 edge/trade) — follow
      Mark 38: Noise on HP (-8 edge/trade) — fade
      Mark 55: Noise on VE (-2.5 edge/trade) — fade
    """

    # ═══════════════════════════════════════════════════════════
    #  Position limits — update per round
    # ═══════════════════════════════════════════════════════════
    LIMITS = {
        "HYDROGEL_PACK": 200,
        "VELVETFRUIT_EXTRACT": 200,
        "VEV_4000": 300, "VEV_4500": 300, "VEV_5000": 300,
        "VEV_5100": 300, "VEV_5200": 300, "VEV_5300": 300,
        "VEV_5400": 300, "VEV_5500": 300, "VEV_6000": 300,
        "VEV_6500": 300,
    }

    # HYDROGEL_PACK parameters
    HP_AR_COEFF = -0.12
    HP_SPREAD_HALF = 7
    HP_TAKE_THRESHOLD = 5.0
    HP_SKEW_COEFF = 0.04
    HP_BASE_SIZE = 50
    HP_COOLDOWN = 100
    HP_L2_OFFSET = 4
    HP_L2_SIZE_FRAC = 0.5
    HP_CP_BIAS = 2.5

    # VELVETFRUIT_EXTRACT parameters
    VE_SPREAD_HALF = 3         # ±3 from fair (sweep: wider = more edge per fill)
    VE_SKEW_COEFF = 0.05       # inventory skew
    VE_QUOTE_SIZE = 3          # small size per level
    VE_EMA_SPAN = 15           # EMA(15) slightly faster than 20

    # VEV parameters
    VEV_DEEP_ITM = {4000}         # Use VE-oracle pricing (TV=0, wide spread)
    VEV_DEEP_HALF = 7             # ±7 inside the 21-tick market spread
    VEV_ATM = {5000, 5100, 5200, 5300}  # Mid-based MM
    VEV_ATM_TAKE = 3.0
    VEV_ATM_QUOTE = 2.0
    VEV_SIZE = 5                  # small per level
    VEV_MAX_POS = 50              # hard cap
    VEV_SKEW = 0.10               # inventory skew

    WINDOW = 50

    def bid(self) -> int:
        return 150

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        s = self._load_state(state.traderData)
        ts = state.timestamp

        cp = self._parse_cp(state.market_trades)

        # Get VE mid for BS pricing
        ve_mid = None
        if "VELVETFRUIT_EXTRACT" in state.order_depths:
            od = state.order_depths["VELVETFRUIT_EXTRACT"]
            if od.sell_orders and od.buy_orders:
                ve_mid = (max(od.buy_orders) + min(od.sell_orders)) / 2

        for product, od in state.order_depths.items():
            pos = state.position.get(product, 0)
            lim = self.LIMITS.get(product, 50)  # default 50 if unknown
            if not od.sell_orders or not od.buy_orders:
                result[product] = []
                continue

            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            mid = (best_bid + best_ask) / 2

            if product == "HYDROGEL_PACK":
                result[product] = self._hp(od, pos, mid, ts, s, cp, lim)
            elif product == "VELVETFRUIT_EXTRACT":
                result[product] = self._ve(od, pos, mid, ts, s, cp, lim)
            elif product.startswith("VEV_") and ve_mid is not None:
                strike = int(product.split("_")[1])
                result[product] = self._vev(product, od, pos, mid, ts, s, ve_mid, strike, lim)
            else:
                result[product] = []

        return result, 0, json.dumps(s)

    # ═══════════════════════════════════════════════════════════
    #  HYDROGEL_PACK
    # ═══════════════════════════════════════════════════════════

    def _hp(self, od, pos, mid, ts, s, cp, lim):
        orders = []
        P = "HYDROGEL_PACK"
        LIM = lim

        # EMA fair value
        p = s.setdefault("hp_p", [])
        p.append(mid)
        if len(p) > self.WINDOW:
            p[:] = p[-self.WINDOW:]

        fair = self._ema(p, 12) if len(p) >= 5 else mid
        if len(p) >= 2:
            fair += self.HP_AR_COEFF * (p[-1] - p[-2])
        fair += cp.get("hp", 0.0)

        # Book imbalance
        tb = sum(od.buy_orders.values())
        ta = -sum(od.sell_orders.values())
        if tb + ta > 0:
            fair += (tb / (tb + ta) - 0.5) * 0.8

        skew = -pos * self.HP_SKEW_COEFF
        bp = int(fair - self.HP_SPREAD_HALF + skew)
        sp = int(fair + self.HP_SPREAD_HALF + skew)

        # Take best mispriced level only (1 order max)
        lt = s.get("hp_lt", 0)
        if ts - lt >= self.HP_COOLDOWN:
            ba = min(od.sell_orders)
            if ba < fair - self.HP_TAKE_THRESHOLD and pos < LIM:
                qty = min(-od.sell_orders[ba], LIM - pos)
                if qty > 0:
                    orders.append(Order(P, ba, qty))
                    pos += qty
                    s["hp_lt"] = ts

            bb = max(od.buy_orders)
            if bb > fair + self.HP_TAKE_THRESHOLD and pos > -LIM:
                qty = min(od.buy_orders[bb], LIM + pos)
                if qty > 0:
                    orders.append(Order(P, bb, -qty))
                    pos -= qty
                    s["hp_lt"] = ts

        # Inventory flatten
        if abs(pos) > 120:
            fq = min(abs(pos) - 60, 20)
            if fq > 0:
                if pos > 0:
                    orders.append(Order(P, int(fair + 1), -fq))
                else:
                    orders.append(Order(P, int(fair - 1), fq))

        # L1 + L2 quotes (4 orders max)
        inv_f = max(0.3, 1.0 - max(0, abs(pos) - 80) * 0.008)
        l1 = max(5, int(self.HP_BASE_SIZE * inv_f))
        l2 = max(3, int(l1 * self.HP_L2_SIZE_FRAC))
        bc = LIM - pos
        sc = LIM + pos

        lb = min(l1, bc)
        ls = min(l1, sc)
        if lb > 0:
            orders.append(Order(P, bp, lb))
            bc -= lb
        if ls > 0:
            orders.append(Order(P, sp, -ls))
            sc -= ls

        lb2 = min(l2, bc)
        ls2 = min(l2, sc)
        if lb2 > 0:
            orders.append(Order(P, bp - self.HP_L2_OFFSET, lb2))
        if ls2 > 0:
            orders.append(Order(P, sp + self.HP_L2_OFFSET, -ls2))

        # EOD
        if ts > 985000 and abs(pos) > 5:
            if pos > 0:
                orders.append(Order(P, int(fair - 1), -pos))
            else:
                orders.append(Order(P, int(fair + 1), -pos))

        return orders

    # ═══════════════════════════════════════════════════════════
    #  VELVETFRUIT_EXTRACT
    # ═══════════════════════════════════════════════════════════

    def _ve(self, od, pos, mid, ts, s, cp, lim):
        """
        VE: EMA-based spread quoting.
        Quotes at EMA(20) ± 2 with inventory skew.
        Small size (3) per level to minimize adverse selection.
        """
        orders = []
        P = "VELVETFRUIT_EXTRACT"
        LIM = lim

        # Track prices for EMA + VEV vol
        p = s.setdefault("ve_p", [])
        p.append(mid)
        if len(p) > self.WINDOW:
            p[:] = p[-self.WINDOW:]

        # EMA fair value
        fair = self._ema(p, self.VE_EMA_SPAN) if len(p) >= 5 else mid

        # Inventory skew
        skew = -pos * self.VE_SKEW_COEFF
        bp = int(fair - self.VE_SPREAD_HALF + skew)
        sp = int(fair + self.VE_SPREAD_HALF + skew) + 1

        # Quote both sides
        bc = LIM - pos
        sc = LIM + pos
        sz = self.VE_QUOTE_SIZE

        lb = min(sz, bc)
        ls = min(sz, sc)
        if lb > 0:
            orders.append(Order(P, bp, lb))
        if ls > 0:
            orders.append(Order(P, sp, -ls))

        # EOD flatten
        if ts > 985000 and abs(pos) > 3:
            if pos > 0:
                orders.append(Order(P, int(fair), -pos))
            else:
                orders.append(Order(P, int(fair), -pos))

        return orders

    # ═══════════════════════════════════════════════════════════
    #  VEV VOUCHERS — Black-Scholes Market Making
    # ═══════════════════════════════════════════════════════════

    def _vev(self, product, od, pos, mid, ts, s, ve_mid, strike, lim):
        """
        VEV strategy split by moneyness:
        - Deep ITM (4000): VE-oracle market making on the wide 21-tick spread.
          Fair = VE_mid - strike (time value ≈ 0). Post inside the market spread.
        - ATM (5000-5300): Simple mid-based market making.
        """
        orders = []
        MAX = min(self.VEV_MAX_POS, lim)

        if strike in self.VEV_DEEP_ITM:
            # ── Deep ITM: VE-oracle pricing ──
            fair = ve_mid - strike  # intrinsic value (TV ≈ 0)
            if fair < 1.0:
                return orders

            skew = -pos * self.VEV_SKEW
            our_bid = int(fair - self.VEV_DEEP_HALF + skew)
            our_ask = int(fair + self.VEV_DEEP_HALF + skew) + 1

            # Post quotes inside the wide market spread
            bc = MAX - pos
            sc = MAX + pos
            sz = self.VEV_SIZE
            lb = min(sz, bc)
            ls = min(sz, sc)
            if lb > 0 and our_bid >= 1:
                orders.append(Order(product, our_bid, lb))
            if ls > 0:
                orders.append(Order(product, our_ask, -ls))

            # Also take if book crosses our fair significantly
            ba = min(od.sell_orders)
            if fair - ba > self.VEV_DEEP_HALF and pos < MAX:
                qty = min(-od.sell_orders[ba], MAX - pos, sz)
                if qty > 0:
                    orders.append(Order(product, ba, qty))

            bb = max(od.buy_orders)
            if bb - fair > self.VEV_DEEP_HALF and pos > -MAX:
                qty = min(od.buy_orders[bb], MAX + pos, sz)
                if qty > 0:
                    orders.append(Order(product, bb, -qty))

        elif strike in self.VEV_ATM:
            # ── ATM: simple mid-based MM ──
            if mid < 2.0:
                return orders

            fair = mid

            # Take mispricings
            ba = min(od.sell_orders)
            if fair - ba > self.VEV_ATM_TAKE and pos < MAX:
                qty = min(-od.sell_orders[ba], MAX - pos, self.VEV_SIZE)
                if qty > 0:
                    orders.append(Order(product, ba, qty))
                    pos += qty

            bb = max(od.buy_orders)
            if bb - fair > self.VEV_ATM_TAKE and pos > -MAX:
                qty = min(od.buy_orders[bb], MAX + pos, self.VEV_SIZE)
                if qty > 0:
                    orders.append(Order(product, bb, -qty))
                    pos -= qty

            # Quote around mid
            skew = -pos * self.VEV_SKEW
            qb = int(fair - self.VEV_ATM_QUOTE + skew)
            qa = max(qb + 1, int(fair + self.VEV_ATM_QUOTE + skew) + 1)
            inv_f = max(0.2, 1.0 - abs(pos) / MAX)
            sz = max(2, int(self.VEV_SIZE * inv_f))

            bq = min(sz, MAX - pos)
            sq = min(sz, MAX + pos)
            if bq > 0 and qb >= 1:
                orders.append(Order(product, qb, bq))
            if sq > 0:
                orders.append(Order(product, qa, -sq))
        else:
            return orders

        # EOD flatten
        if ts > 985000 and abs(pos) > 3:
            fair_eod = (ve_mid - strike) if strike in self.VEV_DEEP_ITM else mid
            if pos > 0:
                orders.append(Order(product, max(1, int(fair_eod - 1)), -pos))
            else:
                orders.append(Order(product, int(fair_eod + 1), -pos))

        return orders

    # ═══════════════════════════════════════════════════════════
    #  Counterparty Parsing
    # ═══════════════════════════════════════════════════════════

    def _parse_cp(self, mt):
        sig = {"hp": 0.0, "ve": 0.0}
        if not mt:
            return sig

        for t in mt.get("HYDROGEL_PACK", []):
            b = getattr(t, 'buyer', None) or ""
            sl = getattr(t, 'seller', None) or ""
            if "Mark 14" in b:
                sig["hp"] += self.HP_CP_BIAS
            elif "Mark 14" in sl:
                sig["hp"] -= self.HP_CP_BIAS
            if "Mark 38" in b:
                sig["hp"] -= self.HP_CP_BIAS * 0.3
            elif "Mark 38" in sl:
                sig["hp"] += self.HP_CP_BIAS * 0.3

        for t in mt.get("VELVETFRUIT_EXTRACT", []):
            b = getattr(t, 'buyer', None) or ""
            sl = getattr(t, 'seller', None) or ""
            if "Mark 55" in b:
                sig["ve"] -= 1.5
            elif "Mark 55" in sl:
                sig["ve"] += 1.5

        sig["hp"] = max(-8.0, min(8.0, sig["hp"]))
        sig["ve"] = max(-5.0, min(5.0, sig["ve"]))
        return sig

    # ═══════════════════════════════════════════════════════════
    #  Black-Scholes
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _bs_call(S, K, T, sigma, r=0.0):
        if T <= 0 or sigma <= 0 or S <= 0:
            return max(0.0, S - K)
        sqT = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqT)
        d2 = d1 - sigma * sqT
        return max(0.0, S * Trader._ncdf(d1) - K * math.exp(-r * T) * Trader._ncdf(d2))

    @staticmethod
    def _ncdf(x):
        if x >= 0:
            t = 1.0 / (1.0 + 0.2316419 * x)
            p = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 +
                t * (-1.821255978 + t * 1.330274429))))
            return 1.0 - 0.3989422804 * math.exp(-0.5 * x * x) * p
        return 1.0 - Trader._ncdf(-x)

    # ═══════════════════════════════════════════════════════════
    #  Utilities
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _ema(prices, span=10):
        a = 2.0 / (span + 1)
        e = prices[0]
        for p in prices[1:]:
            e = a * p + (1 - a) * e
        return e

    @staticmethod
    def _std(data):
        if len(data) < 2:
            return 1.0
        m = sum(data) / len(data)
        v = sum((x - m)**2 for x in data) / (len(data) - 1)
        return max(math.sqrt(v), 0.01)

    @staticmethod
    def _load_state(td):
        if td:
            try:
                return json.loads(td)
            except (json.JSONDecodeError, TypeError):
                pass
        return {}
