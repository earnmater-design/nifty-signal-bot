"""
strategy.py
Iron Condor signal engine.
Analyses live NSE option chain and decides entry/exit.
"""

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

NIFTY_STEP   = 50     # Nifty strike step
SPREAD_WIDTH = 100    # Points between short and long leg
OTM_OFFSET   = 1      # Strikes away from ATM for short leg

# ── Signal filters ────────────────────────────────────────────────────────────
MIN_VIX         = 10.0
MAX_VIX         = 18.0
MIN_NET_PREMIUM = 40.0   # Skip if total net credit < ₹40
MIN_WING_PREM   = 15.0   # Each short leg must have at least ₹15 premium


@dataclass
class IronCondorSignal:
    # Market data
    spot: float
    vix: float
    pcr: float
    expiry: str

    # Legs
    sell_ce_strike: int
    buy_ce_strike: int
    sell_pe_strike: int
    buy_pe_strike: int

    sell_ce_prem: float
    buy_ce_prem: float
    sell_pe_prem: float
    buy_pe_prem: float

    # Risk/reward
    net_premium: float
    spread_width: int
    max_profit: float
    max_loss: float
    target_exit: float   # exit when net premium decays to this
    stop_loss: float     # exit if net premium rises to this

    # OI analysis
    max_pain: int
    ce_wall: int         # strike with highest CE OI = resistance
    pe_wall: int         # strike with highest PE OI = support

    # Signal quality
    signal_score: int    # 0–100
    signal_grade: str    # A / B / C


def round_to_strike(price: float, step: int = NIFTY_STEP) -> int:
    return int(round(price / step) * step)


def find_atm(spot: float, strikes: list) -> int:
    available = [s["strike"] for s in strikes]
    return min(available, key=lambda x: abs(x - spot))


def find_max_pain(strikes: list) -> int:
    """Max pain = strike where total OI loss is minimum for option writers."""
    all_strikes = [s["strike"] for s in strikes]
    losses = {}
    for target in all_strikes:
        ce_loss = sum(max(0, target - s["strike"]) * s["ce_oi"] for s in strikes)
        pe_loss = sum(max(0, s["strike"] - target) * s["pe_oi"] for s in strikes)
        losses[target] = ce_loss + pe_loss
    return min(losses, key=losses.get)


def find_oi_walls(strikes: list) -> tuple[int, int]:
    """Find strikes with max CE OI (resistance) and max PE OI (support)."""
    ce_wall = max(strikes, key=lambda s: s["ce_oi"])["strike"]
    pe_wall = max(strikes, key=lambda s: s["pe_oi"])["strike"]
    return ce_wall, pe_wall


def get_strike_data(strikes: list, strike: int, opt_type: str) -> dict:
    for s in strikes:
        if s["strike"] == strike:
            return s
    return {}


def score_signal(vix, pcr, net_premium, ce_wall, pe_wall, sell_ce, sell_pe) -> tuple[int, str]:
    """Score the signal quality 0–100."""
    score = 0

    # VIX in sweet spot
    if 12 <= vix <= 16: score += 30
    elif 10 <= vix < 12 or 16 < vix <= 18: score += 15

    # PCR in healthy range
    if 0.9 <= pcr <= 1.3: score += 20
    elif 0.7 <= pcr < 0.9 or 1.3 < pcr <= 1.5: score += 10

    # Premium quality
    if net_premium >= 80: score += 25
    elif net_premium >= 55: score += 20
    elif net_premium >= 40: score += 10

    # Short legs inside OI walls (safer range)
    if sell_ce <= ce_wall: score += 15
    if sell_pe >= pe_wall: score += 10

    grade = "A" if score >= 70 else "B" if score >= 50 else "C"
    return score, grade


def build_iron_condor(chain: dict, vix: float, pcr: float) -> tuple[IronCondorSignal | None, str]:
    """
    Main function. Returns (IronCondorSignal, "") or (None, skip_reason).
    """
    spot    = chain["spot"]
    strikes = chain["strikes"]
    expiry  = chain["expiry"]

    # ── Filter checks ─────────────────────────────────────────────────────────
    if vix > MAX_VIX:
        return None, f"VIX {vix:.1f} is too HIGH (max {MAX_VIX}) — market too volatile to sell options today"
    if vix < MIN_VIX:
        return None, f"VIX {vix:.1f} is too LOW (min {MIN_VIX}) — premiums not worth selling today"

    # ── Strike selection ──────────────────────────────────────────────────────
    atm = find_atm(spot, strikes)
    available = sorted([s["strike"] for s in strikes])

    atm_idx    = available.index(atm) if atm in available else -1
    if atm_idx < 2 or atm_idx > len(available) - 3:
        return None, "Not enough strikes around ATM in option chain"

    sell_ce_strike = available[atm_idx + OTM_OFFSET]
    sell_pe_strike = available[atm_idx - OTM_OFFSET]

    # Find buy legs (spread_width away)
    buy_ce_strike = round_to_strike(sell_ce_strike + SPREAD_WIDTH)
    buy_pe_strike = round_to_strike(sell_pe_strike - SPREAD_WIDTH)

    # ── Fetch premiums ────────────────────────────────────────────────────────
    sc = get_strike_data(strikes, sell_ce_strike, "CE")
    bc = get_strike_data(strikes, buy_ce_strike,  "CE")
    sp = get_strike_data(strikes, sell_pe_strike, "PE")
    bp = get_strike_data(strikes, buy_pe_strike,  "PE")

    sell_ce_prem = sc.get("ce_ltp", 0)
    buy_ce_prem  = bc.get("ce_ltp", 0)
    sell_pe_prem = sp.get("pe_ltp", 0)
    buy_pe_prem  = bp.get("pe_ltp", 0)

    net_premium = round((sell_ce_prem - buy_ce_prem) + (sell_pe_prem - buy_pe_prem), 2)

    if sell_ce_prem < MIN_WING_PREM:
        return None, f"CE leg premium ₹{sell_ce_prem} too low (min ₹{MIN_WING_PREM}) — not worth trading"
    if sell_pe_prem < MIN_WING_PREM:
        return None, f"PE leg premium ₹{sell_pe_prem} too low (min ₹{MIN_WING_PREM}) — not worth trading"
    if net_premium < MIN_NET_PREMIUM:
        return None, f"Net premium ₹{net_premium} too low (min ₹{MIN_NET_PREMIUM}) — skip today"

    # ── Risk / reward ─────────────────────────────────────────────────────────
    max_profit  = round(net_premium * 50, 2)          # 1 lot = 50 qty
    max_loss    = round((SPREAD_WIDTH - net_premium) * 50, 2)
    target_exit = round(net_premium * 0.40, 2)        # capture 60% of premium
    stop_loss   = round(net_premium * 2.0,  2)        # SL at 2× premium

    # ── OI analysis ───────────────────────────────────────────────────────────
    max_pain        = find_max_pain(strikes)
    ce_wall, pe_wall = find_oi_walls(strikes)

    # ── Score ─────────────────────────────────────────────────────────────────
    score, grade = score_signal(vix, pcr, net_premium, ce_wall, pe_wall, sell_ce_strike, sell_pe_strike)

    signal = IronCondorSignal(
        spot=spot, vix=vix, pcr=pcr, expiry=expiry,
        sell_ce_strike=sell_ce_strike, buy_ce_strike=buy_ce_strike,
        sell_pe_strike=sell_pe_strike, buy_pe_strike=buy_pe_strike,
        sell_ce_prem=sell_ce_prem, buy_ce_prem=buy_ce_prem,
        sell_pe_prem=sell_pe_prem, buy_pe_prem=buy_pe_prem,
        net_premium=net_premium, spread_width=SPREAD_WIDTH,
        max_profit=max_profit, max_loss=max_loss,
        target_exit=target_exit, stop_loss=stop_loss,
        max_pain=max_pain, ce_wall=ce_wall, pe_wall=pe_wall,
        signal_score=score, signal_grade=grade,
    )
    return signal, ""
