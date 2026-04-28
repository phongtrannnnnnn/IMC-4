"""
Round 4 Trader v13 — Combined optimizations
============================================
v12 baseline (26,309) + tighter VEV_5000 taker + Mark 67/55 VE signals.
"""

from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict, Optional, Tuple
import json
import math
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Black-Scholes
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
    refs = [(K, C) for K, C in option_mids.items()
            if C > max(S - K, 0.0) + 0.5 and abs(K - S) < 500]
    if not refs:
        return 1.0
    def total_err(tte: float) -> float:
        return sum((bs_call(S, K, tte, sigma) - C) ** 2 for K, C in refs)
    lo, hi = 0.01, 9.0
    for _ in range(30):
        m1 = lo + (hi - lo) / 3.0
        m2 = hi - (hi - lo) / 3.0
        if total_err(m1) < total_err(m2):
            hi = m2
        else:
            lo = m1
    return max((lo + hi) / 2.0, 0.01)

def wmid(od: OrderDepth) -> Optional[float]:
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

SIGMA: float = 0.0122

POS_LIMITS: Dict[str, int] = {
    "HYDROGEL_PACK": 200,
    "VELVETFRUIT_EXTRACT": 200,
    **{f"VEV_{k}": 300 for k in [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]},
}

VOUCHER_STRIKES: Dict[str, int] = {
    f"VEV_{k}": k for k in [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
}

VEV_DEEP_ITM = {4000}
VEV_DEEP_HALF = 7
VEV_ATM = {5000, 5100, 5200, 5300}
VEV_NTM = {5500}

# Adaptive opt_sell parameters (from 518982)
OPT_SELL_INIT: float = 1.1
OPT_SELL_MIN: float = 0.25
OPT_SELL_MAX: float = 3.0

# VEV velocity thresholds
VEV_VEL_WARN: float = 5.0   # widen edge
VEV_VEL_STOP: float = 10.0  # disable passive quoting

# HP adaptive edge
HP_EDGE_INIT: int = 7
HP_EDGE_MIN: int = 3
HP_EDGE_MAX: int = 8
HP_ALPHA: float = 0.03


def _fclamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _iclamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


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
        hp_edge: int = int(s.get("hp_edge", HP_EDGE_INIT))
        vev_prev: float = s.get("vev_prev", 5250.0)
        opt_sell: float = float(s.get("opt_sell", OPT_SELL_INIT))
        prev_vev_mid: float = s.get("prev_vev_mid", 0.0)

        result: Dict[str, List[Order]] = {}
        ts = state.timestamp

        # ── Fair values ───────────────────────────────────────────
        od_hp = state.order_depths.get("HYDROGEL_PACK")
        if od_hp and od_hp.buy_orders and od_hp.sell_orders:
            wm = wmid(od_hp)
            if wm is not None:
                hp_ewm = (1.0 - HP_ALPHA) * hp_ewm + HP_ALPHA * wm
        hp_fair = hp_ewm

        od_ve = state.order_depths.get("VELVETFRUIT_EXTRACT")
        ve_raw = wmid(od_ve) if od_ve else None
        ve_fair = ve_raw if ve_raw is not None else vev_prev
        vev_prev = ve_fair

        # ── Infer TTE (cached) ────────────────────────────────────
        cached_tte = s.get("tte", 4.0)
        if ts % 500 == 0:
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

        winding_down = (tte < 1.1)

        # ── VEV velocity (how fast VE mid is moving) ──────────────
        vev_velocity = abs(ve_fair - prev_vev_mid) if prev_vev_mid > 0 else 0.0
        prev_vev_mid = ve_fair

        # ── Counterparty scan ─────────────────────────────────────
        flags = self._scan_trades(state.market_trades)

        # ── Adapt edges based on fill rate & velocity ─────────────
        fill_log = s.setdefault("fill_log", {})
        # Track fills per product
        for prod, trades in (state.own_trades or {}).items():
            fl = fill_log.setdefault(prod, {"f": 0, "t": 0})
            fl["t"] += 1
            if trades:
                fl["f"] += 1

        hp_edge, opt_sell = self._adapt(
            hp_edge, opt_sell, vev_velocity, fill_log
        )

        # ── HP orders ─────────────────────────────────────────────
        result["HYDROGEL_PACK"] = self._hp(
            state, hp_fair, hp_edge, flags, winding_down
        )

        # ── VEV orders ────────────────────────────────────────────
        total_delta = 0.0
        snipe_mode = (vev_velocity >= VEV_VEL_STOP)
        allow_passive = not snipe_mode and not winding_down

        for sym, K in VOUCHER_STRIKES.items():
            od = state.order_depths.get(sym)
            pos = state.position.get(sym, 0)
            lim = POS_LIMITS[sym]

            if od is None or not od.buy_orders or not od.sell_orders:
                result[sym] = []
                total_delta += pos * bs_delta(ve_fair, K, tte, SIGMA)
                continue

            if K in VEV_DEEP_ITM:
                result[sym] = self._vev_deep(sym, od, pos, ve_fair, K, lim, ts)
            elif K in VEV_ATM or K in VEV_NTM:
                pos_reserve = 60 if winding_down else (20 if K == 5000 else 30)
                result[sym] = self._vev_atm(
                    sym, od, pos, ve_fair, K, lim, tte,
                    opt_sell, vev_velocity, allow_passive,
                    snipe_mode, flags.get("m01_active", False),
                    pos_reserve
                )
            else:
                result[sym] = []

            delta = bs_delta(ve_fair, K, tte, SIGMA)
            total_delta += pos * delta

        # ── VE orders (delta-hedge-aware) ─────────────────────────
        # Must come AFTER VEV loop so total_delta is computed.
        # total_delta is our aggregate option delta (negative when short calls).
        # We bias VE position to partially hedge: go LONG VE when short delta.
        result["VELVETFRUIT_EXTRACT"] = self._ve(
            state, ve_fair, total_delta, flags
        )

        # ── Persist state ─────────────────────────────────────────
        return result, 0, json.dumps({
            "hp_ewm": hp_ewm,
            "hp_edge": hp_edge,
            "vev_prev": vev_prev,
            "tte": tte,
            "opt_sell": opt_sell,
            "prev_vev_mid": prev_vev_mid,
            "fill_log": fill_log,
        })

    # ═══════════════════════════════════════════════════════════════════════
    #  Counterparty scan
    # ═══════════════════════════════════════════════════════════════════════

    def _scan_trades(self, mt):
        flags = {
            "m38_buy_hp": False, "m38_sell_hp": False,
            "m01_active": False,
            "m67_buy_ve": False, "m49_sell_ve": False,
            "m55_buy_ve": False, "m55_sell_ve": False,
        }
        if not mt:
            return flags

        for t in mt.get("HYDROGEL_PACK", []):
            b = getattr(t, 'buyer', '') or ''
            sl = getattr(t, 'seller', '') or ''
            if "Mark 38" in b:
                flags["m38_buy_hp"] = True
            if "Mark 38" in sl:
                flags["m38_sell_hp"] = True

        # Mark 01 active on any VEV product
        for prod, trades in mt.items():
            if not prod.startswith("VEV"):
                continue
            for t in trades:
                b = getattr(t, 'buyer', '') or ''
                if "Mark 01" in b:
                    flags["m01_active"] = True
                    break
            if flags["m01_active"]:
                break

        # VE counterparties: Mark 67 (momentum, Sharpe 2.05), Mark 55 (losing bot)
        for t in mt.get("VELVETFRUIT_EXTRACT", []):
            b = getattr(t, 'buyer', '') or ''
            sl = getattr(t, 'seller', '') or ''
            if "Mark 67" in b: flags["m67_buy_ve"] = True
            if "Mark 49" in sl: flags["m49_sell_ve"] = True
            if "Mark 55" in b: flags["m55_buy_ve"] = True
            if "Mark 55" in sl: flags["m55_sell_ve"] = True

        return flags

    # ═══════════════════════════════════════════════════════════════════════
    #  Adaptive edge (from 518982)
    # ═══════════════════════════════════════════════════════════════════════

    def _adapt(self, hp_edge, opt_sell, vev_velocity, fill_log):
        # HP: tighten if not getting fills, widen if over-filling
        hp_fl = fill_log.get("HYDROGEL_PACK", {"f": 0, "t": 1})
        hp_rate = hp_fl["f"] / max(hp_fl["t"], 1)
        if hp_rate < 0.015:
            hp_edge = max(HP_EDGE_MIN, hp_edge - 1)
        elif hp_rate > 0.12:
            hp_edge = min(HP_EDGE_MAX, hp_edge + 1)

        # Options: widen during velocity, tighten during low fill rate
        if vev_velocity >= VEV_VEL_WARN:
            extra = (vev_velocity - VEV_VEL_WARN) * 0.25
            opt_sell = _fclamp(opt_sell + extra, OPT_SELL_MIN, OPT_SELL_MAX)
        else:
            # Decay toward init
            opt_sell = _fclamp(
                opt_sell * 0.97 + OPT_SELL_INIT * 0.03,
                OPT_SELL_MIN, OPT_SELL_MAX
            )

        # If option fill rate is very low, tighten
        opt_fills = 0
        opt_total = 0
        for k, v in fill_log.items():
            if k.startswith("VEV"):
                opt_fills += v["f"]
                opt_total += v["t"]
        opt_rate = opt_fills / max(opt_total, 1)
        if opt_rate < 0.02 and vev_velocity < VEV_VEL_WARN:
            opt_sell = max(OPT_SELL_MIN, opt_sell - 0.05)

        return hp_edge, opt_sell

    # ═══════════════════════════════════════════════════════════════════════
    #  HYDROGEL_PACK — Inside-best quoting (518982-style)
    #  Evidence: 518982 +883 ALL phases vs our -429
    # ═══════════════════════════════════════════════════════════════════════

    def _hp(self, state, fair, edge, flags, winding_down):
        sym = "HYDROGEL_PACK"
        od = state.order_depths.get(sym)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []
        pos = state.position.get(sym, 0)
        limit = POS_LIMITS[sym]
        orders: List[Order] = []

        bb = max(od.buy_orders)
        ba = min(od.sell_orders)

        # Inventory skew (±2 ticks max)
        skew = round(-2.0 * pos / limit)

        # Inside-best quoting
        our_bid = bb + 1 + skew
        our_ask = ba - 1 + skew
        if our_bid >= our_ask:
            our_bid = our_ask - 1

        # ── Taker: lift obvious mispricings ────────────────────────
        rem_buy = max(0, limit - 30 - pos)
        for ask in sorted(od.sell_orders.keys()):
            if ask < fair - edge and rem_buy > 0:
                vol = min(rem_buy, abs(od.sell_orders[ask]))
                orders.append(Order(sym, ask, vol))
                rem_buy -= vol
            else:
                break

        rem_sell = max(0, limit - 30 + pos)
        for bid in sorted(od.buy_orders.keys(), reverse=True):
            if bid > fair + edge and rem_sell > 0:
                vol = min(rem_sell, abs(od.buy_orders[bid]))
                orders.append(Order(sym, bid, -vol))
                rem_sell -= vol
            else:
                break

        # ── Passive maker ──────────────────────────────────────────
        max_sz = 15 if winding_down else 25
        bq = _iclamp(max(0, limit - 15 - pos), 0, max_sz)
        aq = _iclamp(max(0, limit - 15 + pos), 0, max_sz)
        if bq > 0:
            orders.append(Order(sym, our_bid, bq))
        if aq > 0:
            orders.append(Order(sym, our_ask, -aq))

        # ── Reactive burst on Mark 38 ──────────────────────────────
        if flags["m38_buy_hp"]:
            burst_ask = our_ask - 1
            burst_qty = _iclamp(max(0, limit - 5 + pos), 0, 8)
            if burst_qty > 0 and burst_ask > our_bid:
                orders.append(Order(sym, burst_ask, -burst_qty))

        if flags["m38_sell_hp"]:
            burst_bid = our_bid + 1
            burst_qty = _iclamp(max(0, limit - 5 - pos), 0, 8)
            if burst_qty > 0 and burst_bid < our_ask:
                orders.append(Order(sym, burst_bid, burst_qty))

        return orders

    # ═══════════════════════════════════════════════════════════════════════
    #  VELVETFRUIT_EXTRACT — Delta-hedge-aware quoting
    #  Uses aggregate option delta to bias VE position toward hedging.
    #  We can only hedge 26% of delta (200 VE limit vs ~758 option delta)
    #  but that still reduces drawdowns by ~4k.
    # ═══════════════════════════════════════════════════════════════════════

    VE_SPREAD_HALF = 2
    VE_QUOTE_SIZE = 5

    def _ve(self, state, fair, total_delta, flags):
        sym = "VELVETFRUIT_EXTRACT"
        od = state.order_depths.get(sym)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []
        pos = state.position.get(sym, 0)
        limit = POS_LIMITS[sym]
        orders: List[Order] = []

        bb = max(od.buy_orders)
        ba = min(od.sell_orders)

        # Delta hedge target
        hedge_target = _iclamp(int(-total_delta), -limit, limit)
        hedge_gap = hedge_target - pos

        bp = int(fair - self.VE_SPREAD_HALF)
        sp = int(fair + self.VE_SPREAD_HALF) + 1

        bc = limit - pos
        sc = limit + pos

        # Size-based hedging
        base_sz = self.VE_QUOTE_SIZE
        if hedge_gap > 20:
            bid_sz = min(base_sz + min(abs(hedge_gap) // 20, 10), bc)
            ask_sz = min(max(1, base_sz - 2), sc)
        elif hedge_gap < -20:
            bid_sz = min(max(1, base_sz - 2), bc)
            ask_sz = min(base_sz + min(abs(hedge_gap) // 20, 10), sc)
        else:
            bid_sz = min(base_sz, bc)
            ask_sz = min(base_sz, sc)

        if bid_sz > 0:
            orders.append(Order(sym, bp, bid_sz))
        if ask_sz > 0:
            orders.append(Order(sym, sp, -ask_sz))

        # Mark 67 momentum: when M67 buys VE, price rises next tick
        # Taker buy to ride the move (518982 Sharpe 2.05, 95.8% win)
        if flags.get("m67_buy_ve") and bc > 0:
            qty = min(15, bc)
            orders.append(Order(sym, ba, qty))

        # Fade Mark 55 (losing momentum bot)
        if flags.get("m55_buy_ve") and not flags.get("m55_sell_ve") and sc > 0:
            qty = min(10, sc)
            orders.append(Order(sym, round(fair + 2), -qty))
        elif flags.get("m55_sell_ve") and not flags.get("m55_buy_ve") and bc > 0:
            qty = min(10, bc)
            orders.append(Order(sym, round(fair - 2), qty))

        return orders

    # ═══════════════════════════════════════════════════════════════════════
    #  VEV Deep ITM (4000) — VE-oracle MM
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

        return orders

    # ═══════════════════════════════════════════════════════════════════════
    #  VEV ATM/NTM — BS-priced with adaptive edge + Mark 01 detection
    # ═══════════════════════════════════════════════════════════════════════

    def _vev_atm(self, sym, od, pos, ve_fair, strike, lim, tte,
                 opt_sell, vev_velocity, allow_passive,
                 snipe_mode, mark01_active, pos_reserve):
        orders: List[Order] = []

        bs_fair = bs_call(ve_fair, strike, tte, SIGMA)
        delta = bs_delta(ve_fair, strike, tte, SIGMA)

        if bs_fair < 0.25:
            return orders

        # ── Edge sizing by moneyness ──────────────────────────────
        if delta > 0.95:
            taker_edge = 1.5
        elif delta < 0.03:
            taker_edge = 0.5
        else:
            # v13: tighter when Mark 01 active (0.40x vs v10's 0.55x)
            # 518982 gets +5.5k on VEV_5000 vs our +2.5k — need more fills
            taker_edge = opt_sell * (0.40 if mark01_active else 1.0)

        buy_thresh = bs_fair - taker_edge
        sell_thresh = bs_fair + taker_edge

        # ── Snipe bonus during velocity ───────────────────────────
        snipe_bonus = (delta * vev_velocity * 1.2) if snipe_mode else 0.0

        # ── Taker: sweep mispricings ──────────────────────────────
        rem_buy = max(0, lim - pos_reserve - pos)
        for ask in sorted(od.sell_orders.keys()):
            if ask < buy_thresh + snipe_bonus and rem_buy > 0:
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

        if not allow_passive:
            return orders

        # ── Passive maker ─────────────────────────────────────────
        skew = -taker_edge * 0.3 * (pos / lim)

        passive_ask = max(1, math.floor(bs_fair - opt_sell + skew))
        passive_bid = max(1, math.ceil(bs_fair - taker_edge * 2.0 - skew))

        if passive_bid >= passive_ask:
            passive_bid = passive_ask - 1

        max_sz = 40 if (0.05 <= delta <= 0.95) else 12
        ask_qty = _iclamp(max(0, lim - pos_reserve + pos), 0, max_sz)
        bid_qty = _iclamp(max(0, lim - pos_reserve - pos), 0, max_sz)

        if ask_qty > 0:
            orders.append(Order(sym, passive_ask, -ask_qty))
        if bid_qty > 0 and passive_bid >= 1:
            orders.append(Order(sym, passive_bid, bid_qty))

        return orders

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
