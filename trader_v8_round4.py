"""
Round 4 Trader v7 — Hybrid Strategy
====================================
Combines v6 proven strategies with 518982 insights about the official platform:

HP:  Quote 1 tick inside best bid/ask to beat Mark 14 for Mark 38's flow.
     Taker: lift obvious mispricings vs EWM fair.
VE:  EMA(15) ±3 passive quoting with inventory skew (proven +4k in backtest).
VEV Deep ITM (4000): VE-oracle MM inside 21-tick spread (proven +6.5k).
VEV ATM (5000-5300): BS fair (sigma=0.0122, inferred TTE) sell at BS-1.
     Mark 01 buys options every tick — we undercut Mark 22 to win flow.
     Large size (40) for pro-rata fills.

Counterparty profiles:
  Mark 01  — Buys OTM/ATM options every tick. Our revenue source for VEV ATM.
  Mark 14  — HP maker incumbent. We beat by quoting 1 tick inside.
  Mark 22  — Sells options at BS-1 average. We undercut with BS-1.1.
  Mark 38  — HP taker: always hits best bid/ask. Our revenue source for HP.
  Mark 55  — Losing VE momentum bot, 85% of all VE trades. Our fill source.
"""

from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict, Optional, Tuple
import json
import math

# ─────────────────────────────────────────────────────────────────────────────
# Black-Scholes (pure Python — calibrated sigma=0.0122 daily vol)
# ─────────────────────────────────────────────────────────────────────────────

def _erf(x: float) -> float:
    t = 1.0 / (1.0 + 0.3275911 * abs(x))
    p = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741
            + t * (-1.453152027 + t * 1.061405429))))
    r = 1.0 - p * math.exp(-x * x)
    return r if x >= 0 else -r

def _N(x: float) -> float:
    return 0.5 * (1.0 + _erf(x / math.sqrt(2.0)))

def bs_call(S: float, K: float, T: float, sigma: float) -> float:
    """BS call price. T in days, sigma = daily vol."""
    if T <= 0.0 or S <= 0.0 or K <= 0.0 or sigma <= 0.0:
        return max(S - K, 0.0)
    vt = sigma * math.sqrt(T)
    d1 = math.log(S / K) / vt + 0.5 * vt
    return S * _N(d1) - K * _N(d1 - vt)

def bs_delta(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0.0 or S <= 0.0 or K <= 0.0 or sigma <= 0.0:
        return 1.0 if S >= K else 0.0
    vt = sigma * math.sqrt(T)
    d1 = math.log(S / K) / vt + 0.5 * vt
    return _N(d1)

def infer_tte(S: float, sigma: float, option_mids: Dict[int, float]) -> float:
    """Back-solve TTE from observed option mid prices via ternary search."""
    refs = [(K, C) for K, C in option_mids.items()
            if C > max(S - K, 0.0) + 0.5 and abs(K - S) < 500]
    if not refs:
        return 1.0
    def total_err(tte: float) -> float:
        return sum((bs_call(S, K, tte, sigma) - C) ** 2 for K, C in refs)
    lo, hi = 0.01, 9.0
    for _ in range(30):  # 30 iters gives precision ~0.001 days
        m1 = lo + (hi - lo) / 3.0
        m2 = hi - (hi - lo) / 3.0
        if total_err(m1) < total_err(m2):
            hi = m2
        else:
            lo = m1
    return max((lo + hi) / 2.0, 0.01)

def wmid(od: OrderDepth) -> Optional[float]:
    """Volume-weighted mid from best bid/ask."""
    if not od.buy_orders or not od.sell_orders:
        return None
    bb = max(od.buy_orders)
    ba = min(od.sell_orders)
    bv = abs(od.buy_orders[bb])
    av = abs(od.sell_orders[ba])
    tot = bv + av
    return (bb * av + ba * bv) / tot if tot > 0 else (bb + ba) / 2.0

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SIGMA: float = 0.0122  # calibrated daily vol (matches official platform pricing)

POS_LIMITS: Dict[str, int] = {
    "HYDROGEL_PACK": 200,
    "VELVETFRUIT_EXTRACT": 200,
    **{f"VEV_{k}": 300 for k in [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]},
}

VOUCHER_STRIKES: Dict[str, int] = {
    f"VEV_{k}": k for k in [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
}

# Deep ITM — use VE-oracle pricing (time value ≈ 0)
# VEV_5000 dynamically routed: oracle if delta>0.93, BS if ATM
VEV_DEEP_ITM = {4000}
VEV_DEEP_HALF = 7

# ATM — use BS pricing to sell to Mark 01
# VEV_5000 may be routed here or to deep depending on live delta
VEV_ATM = {5000, 5100, 5200, 5300}

# OTM with some value — also quote for Mark 01
# VEV_5400 excluded: loses on both official platform (-2k) and backtester (-25k)
VEV_NTM = {5500}

# ─────────────────────────────────────────────────────────────────────────────
# Trader
# ─────────────────────────────────────────────────────────────────────────────

class Trader:

    def bid(self) -> int:
        return 150

    def run(self, state: TradingState):
        # ── Load state ────────────────────────────────────────────
        try:
            s = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            s = {}

        hp_ewm: float = s.get("hp_ewm", 10000.0)
        vev_prev: float = s.get("vev_prev", 5250.0)

        # HP price history (for v6 EMA+AR)
        hp_p = s.setdefault("hp_p", [])

        result: Dict[str, List[Order]] = {}
        ts = state.timestamp

        # ── Fair values ───────────────────────────────────────────
        od_hp = state.order_depths.get("HYDROGEL_PACK")
        if od_hp and od_hp.buy_orders and od_hp.sell_orders:
            wm = wmid(od_hp)
            if wm is not None:
                hp_ewm = 0.97 * hp_ewm + 0.03 * wm
        hp_fair = hp_ewm

        od_ve = state.order_depths.get("VELVETFRUIT_EXTRACT")
        ve_raw = wmid(od_ve) if od_ve else None
        ve_fair = ve_raw if ve_raw is not None else vev_prev
        vev_prev = ve_fair

        # ── VE EMA fair (for our VE strategy) ─────────────────────
        ve_p = s.setdefault("ve_p", [])
        if ve_raw is not None:
            ve_p.append(ve_raw)
        if len(ve_p) > 50:
            ve_p[:] = ve_p[-50:]
        ve_ema = self._ema(ve_p, 15) if len(ve_p) >= 5 else ve_fair

        # ── Infer TTE from live option prices (cached) ──────────────
        cached_tte = s.get("tte", 4.0)
        if ts % 500 == 0:  # recompute every 500 ticks (~50s)
            option_mids: Dict[int, float] = {}
            for sym, K in VOUCHER_STRIKES.items():
                od_opt = state.order_depths.get(sym)
                if od_opt:
                    m = wmid(od_opt)
                    if m is not None and m > 0.0:
                        option_mids[K] = m
            tte = infer_tte(ve_fair, SIGMA, option_mids)
            s["tte"] = tte
        else:
            tte = cached_tte

        # ── Counterparty scan ─────────────────────────────────────
        cp = self._parse_cp(state.market_trades)

        # ── HP orders (v6 proven: EMA+AR, ±7 spread, L1+L2) ──────
        result["HYDROGEL_PACK"] = self._hp(
            state, hp_fair, cp, ts, s
        )

        # ── VE orders (v8: use raw wmid, EMA was near-zero on official) ─
        result["VELVETFRUIT_EXTRACT"] = self._ve(
            state, ve_fair, ve_fair, ts
        )

        # ── VEV orders ────────────────────────────────────────────
        total_delta = 0.0
        for sym, K in VOUCHER_STRIKES.items():
            od = state.order_depths.get(sym)
            pos = state.position.get(sym, 0)
            lim = POS_LIMITS[sym]

            if od is None or not od.buy_orders or not od.sell_orders:
                result[sym] = []
                total_delta += pos * bs_delta(ve_fair, K, tte, SIGMA)
                continue

            mid = (max(od.buy_orders) + min(od.sell_orders)) / 2

            delta = bs_delta(ve_fair, K, tte, SIGMA)

            # v8: dynamically route VEV_5000 based on live delta
            # When delta > 0.93 it behaves like deep ITM (TV≈0)
            use_deep = (K in VEV_DEEP_ITM) or (K == 5000 and delta > 0.93)

            if use_deep:
                result[sym] = self._vev_deep(sym, od, pos, ve_fair, K, lim, ts)
            elif K in VEV_ATM or K in VEV_NTM:
                result[sym] = self._vev_atm(
                    sym, od, pos, ve_fair, K, lim, tte, ts
                )
            else:
                result[sym] = []

            total_delta += pos * delta

        # ── Persist state ─────────────────────────────────────────
        return result, 0, json.dumps({
            "hp_ewm": hp_ewm,
            "vev_prev": vev_prev,
            "ve_p": ve_p,
            "tte": tte,
            "hp_p": hp_p,
            "hp_lt": s.get("hp_lt", 0),
        })

    # ═══════════════════════════════════════════════════════════════════════
    #  HYDROGEL_PACK — v6 proven: EMA(12)+AR(1)+OBI, ±7 spread, L1+L2
    # ═══════════════════════════════════════════════════════════════════════

    HP_AR_COEFF = -0.12
    HP_SPREAD_HALF = 7
    HP_TAKE_THRESHOLD = 5.0
    HP_SKEW_COEFF = 0.04
    HP_BASE_SIZE = 50
    HP_COOLDOWN = 100
    HP_L2_OFFSET = 4
    HP_L2_SIZE_FRAC = 0.5
    WINDOW = 50

    def _hp(self, state, fair, cp, ts, s):
        sym = "HYDROGEL_PACK"
        od = state.order_depths.get(sym)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []
        pos = state.position.get(sym, 0)
        LIM = POS_LIMITS[sym]
        orders: List[Order] = []

        mid = (max(od.buy_orders) + min(od.sell_orders)) / 2

        # EMA fair value + AR(1) trend + CP signal + book imbalance
        hp_p = s.setdefault("hp_p", [])
        hp_p.append(mid)
        if len(hp_p) > self.WINDOW:
            hp_p[:] = hp_p[-self.WINDOW:]

        fair = self._ema(hp_p, 12) if len(hp_p) >= 5 else mid
        if len(hp_p) >= 2:
            fair += self.HP_AR_COEFF * (hp_p[-1] - hp_p[-2])
        fair += cp.get("hp", 0.0)

        # Book imbalance
        tb = sum(od.buy_orders.values())
        ta = -sum(od.sell_orders.values())
        if tb + ta > 0:
            fair += (tb / (tb + ta) - 0.5) * 0.8

        skew = -pos * self.HP_SKEW_COEFF
        bp = int(fair - self.HP_SPREAD_HALF + skew)
        sp = int(fair + self.HP_SPREAD_HALF + skew)

        # Take best mispriced level only (with cooldown)
        lt = s.get("hp_lt", 0)
        if ts - lt >= self.HP_COOLDOWN:
            ba = min(od.sell_orders)
            if ba < fair - self.HP_TAKE_THRESHOLD and pos < LIM:
                qty = min(-od.sell_orders[ba], LIM - pos)
                if qty > 0:
                    orders.append(Order(sym, ba, qty))
                    pos += qty
                    s["hp_lt"] = ts

            bb = max(od.buy_orders)
            if bb > fair + self.HP_TAKE_THRESHOLD and pos > -LIM:
                qty = min(od.buy_orders[bb], LIM + pos)
                if qty > 0:
                    orders.append(Order(sym, bb, -qty))
                    pos -= qty
                    s["hp_lt"] = ts

        # Inventory flatten
        if abs(pos) > 120:
            fq = min(abs(pos) - 60, 20)
            if fq > 0:
                if pos > 0:
                    orders.append(Order(sym, int(fair + 1), -fq))
                else:
                    orders.append(Order(sym, int(fair - 1), fq))

        # L1 + L2 quotes
        inv_f = max(0.3, 1.0 - max(0, abs(pos) - 80) * 0.008)
        l1 = max(5, int(self.HP_BASE_SIZE * inv_f))
        l2 = max(3, int(l1 * self.HP_L2_SIZE_FRAC))
        bc = LIM - pos
        sc = LIM + pos

        lb = min(l1, bc)
        ls = min(l1, sc)
        if lb > 0:
            orders.append(Order(sym, bp, lb))
            bc -= lb
        if ls > 0:
            orders.append(Order(sym, sp, -ls))
            sc -= ls

        lb2 = min(l2, bc)
        ls2 = min(l2, sc)
        if lb2 > 0:
            orders.append(Order(sym, bp - self.HP_L2_OFFSET, lb2))
        if ls2 > 0:
            orders.append(Order(sym, sp + self.HP_L2_OFFSET, -ls2))

        # v8 EOD: gradual flatten starting at t=80k
        # Old: abrupt dump at t=98.5k cost -1,261 on official platform
        if ts > 80000:
            # Phase 1 (80k-90k): reduce quote size, stop taking
            if ts <= 90000:
                # Just reduce size by zeroing L2 (already done above)
                target = int(LIM * 0.3)  # aim for 30% of limit
                if abs(pos) > target:
                    fq = min(abs(pos) - target, 10)
                    if pos > 0:
                        orders.append(Order(sym, sp, -fq))
                    else:
                        orders.append(Order(sym, bp, fq))
            # Phase 2 (90k+): aggressive flatten
            elif abs(pos) > 5:
                fq = min(abs(pos), 15)
                if pos > 0:
                    orders.append(Order(sym, int(fair - 1), -fq))
                else:
                    orders.append(Order(sym, int(fair + 1), fq))

        return orders

    # ═══════════════════════════════════════════════════════════════════════
    #  VELVETFRUIT_EXTRACT — v8: raw wmid ±2 (EMA was -128 on official)
    # ═══════════════════════════════════════════════════════════════════════

    VE_SPREAD_HALF = 2  # v8: tighter spread on official (was 3)
    VE_SKEW_COEFF = 0.05
    VE_QUOTE_SIZE = 5   # v8: larger size on official (was 3)

    def _ve(self, state, ema_fair, raw_fair, ts):
        sym = "VELVETFRUIT_EXTRACT"
        od = state.order_depths.get(sym)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []
        pos = state.position.get(sym, 0)
        limit = POS_LIMITS[sym]
        orders: List[Order] = []

        fair = ema_fair
        skew = -pos * self.VE_SKEW_COEFF
        bp = int(fair - self.VE_SPREAD_HALF + skew)
        sp = int(fair + self.VE_SPREAD_HALF + skew) + 1

        bc = limit - pos
        sc = limit + pos
        sz = self.VE_QUOTE_SIZE

        lb = min(sz, bc)
        ls = min(sz, sc)
        if lb > 0:
            orders.append(Order(sym, bp, lb))
        if ls > 0:
            orders.append(Order(sym, sp, -ls))

        # EOD flatten
        if ts > 985000 and abs(pos) > 3:
            orders.append(Order(sym, int(fair), -pos))

        return orders

    # ═══════════════════════════════════════════════════════════════════════
    #  VEV Deep ITM (4000) — VE-oracle MM (proven +6.5k)
    # ═══════════════════════════════════════════════════════════════════════

    def _vev_deep(self, sym, od, pos, ve_fair, strike, lim, ts):
        orders: List[Order] = []
        MAX = min(50, lim)
        fair = ve_fair - strike
        if fair < 1.0:
            return orders

        skew = -pos * 0.10
        our_bid = int(fair - VEV_DEEP_HALF + skew)
        our_ask = int(fair + VEV_DEEP_HALF + skew) + 1

        sz = 5
        lb = min(sz, MAX - pos)
        ls = min(sz, MAX + pos)
        if lb > 0 and our_bid >= 1:
            orders.append(Order(sym, our_bid, lb))
        if ls > 0:
            orders.append(Order(sym, our_ask, -ls))

        # Take if book crosses fair significantly
        ba = min(od.sell_orders)
        if fair - ba > VEV_DEEP_HALF and pos < MAX:
            qty = min(-od.sell_orders[ba], MAX - pos, sz)
            if qty > 0:
                orders.append(Order(sym, ba, qty))

        bb = max(od.buy_orders)
        if bb - fair > VEV_DEEP_HALF and pos > -MAX:
            qty = min(od.buy_orders[bb], MAX + pos, sz)
            if qty > 0:
                orders.append(Order(sym, bb, -qty))

        # EOD
        if ts > 985000 and abs(pos) > 3:
            if pos > 0:
                orders.append(Order(sym, max(1, int(fair - 1)), -pos))
            else:
                orders.append(Order(sym, int(fair + 1), -pos))

        return orders

    # ═══════════════════════════════════════════════════════════════════════
    #  VEV ATM/NTM — BS-priced, sell to Mark 01 (from 518982 insights)
    # ═══════════════════════════════════════════════════════════════════════

    def _vev_atm(self, sym, od, pos, ve_fair, strike, lim, tte, ts):
        orders: List[Order] = []
        MAX = min(200, lim)
        pos_reserve = 60  # v8: wider reserve (was 30 → -270 maxed out)

        bs_fair = bs_call(ve_fair, strike, tte, SIGMA)
        delta = bs_delta(ve_fair, strike, tte, SIGMA)

        if bs_fair < 0.25:
            return orders  # worthless

        # ── Edge sizing by moneyness ──────────────────────────────
        if delta > 0.95:
            taker_edge = 1.5   # deep ITM: tight tracking
        elif delta < 0.03:
            taker_edge = 0.5   # deep OTM: minimal value
        else:
            taker_edge = 1.1   # ATM/NTM: undercut Mark 22 (avg BS-1.0)

        # ── Taker: sweep mispricings ──────────────────────────────
        buy_thresh = bs_fair - taker_edge
        sell_thresh = bs_fair + taker_edge

        rem_buy = max(0, lim - pos_reserve - pos)
        for ask in sorted(od.sell_orders.keys()):
            if ask < buy_thresh and rem_buy > 0:
                vol = min(rem_buy, abs(od.sell_orders[ask]))
                if vol > 0:
                    orders.append(Order(sym, ask, vol))
                    rem_buy -= vol
            else:
                break

        rem_sell = max(0, lim - pos_reserve + pos)
        for bid in sorted(od.buy_orders.keys(), reverse=True):
            if bid > sell_thresh and rem_sell > 0:
                vol = min(rem_sell, abs(od.buy_orders[bid]))
                if vol > 0:
                    orders.append(Order(sym, bid, -vol))
                    rem_sell -= vol
            else:
                break

        # ── Passive maker: sell at BS - 1.1 to win Mark 01 flow ──
        inv_skew = -taker_edge * 0.3 * (pos / lim)

        # Ask: undercut Mark 22 (who sells at BS-1.0)
        passive_ask = max(1, math.floor(bs_fair - 1.1 + inv_skew))
        # Bid: well below BS to catch panic sellers
        passive_bid = max(1, math.ceil(bs_fair - taker_edge * 2.0 - inv_skew))

        if passive_bid >= passive_ask:
            passive_bid = passive_ask - 1

        # Post large size (40) — on official platform, pro-rata fill means
        # larger size = more fills when tied with competitors
        max_sz = 40 if (0.05 <= delta <= 0.95) else 12
        ask_qty = min(max_sz, max(0, lim - pos_reserve + pos))
        bid_qty = min(max_sz, max(0, lim - pos_reserve - pos))

        if ask_qty > 0:
            orders.append(Order(sym, passive_ask, -ask_qty))
        if bid_qty > 0 and passive_bid >= 1:
            orders.append(Order(sym, passive_bid, bid_qty))

        # ── EOD flatten ───────────────────────────────────────────
        if ts > 985000 and abs(pos) > 3:
            if pos > 0:
                orders.append(Order(sym, max(1, int(bs_fair - 1)), -pos))
            else:
                orders.append(Order(sym, int(bs_fair + 1), -pos))

        return orders

    # ═══════════════════════════════════════════════════════════════════════
    #  Counterparty parsing
    # ═══════════════════════════════════════════════════════════════════════

    def _parse_cp(self, mt):
        sig = {"hp": 0.0}
        if not mt:
            return sig
        for t in mt.get("HYDROGEL_PACK", []):
            b = getattr(t, 'buyer', None) or ""
            sl = getattr(t, 'seller', None) or ""
            if "Mark 14" in b:
                sig["hp"] += 2.5
            elif "Mark 14" in sl:
                sig["hp"] -= 2.5
            if "Mark 38" in b:
                sig["hp"] -= 0.75
            elif "Mark 38" in sl:
                sig["hp"] += 0.75
        sig["hp"] = max(-8.0, min(8.0, sig["hp"]))
        return sig

    # ═══════════════════════════════════════════════════════════════════════
    #  Utilities
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _ema(prices, span=10):
        a = 2.0 / (span + 1)
        e = prices[0]
        for p in prices[1:]:
            e = a * p + (1 - a) * e
        return e
