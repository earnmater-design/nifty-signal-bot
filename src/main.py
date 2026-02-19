"""
main.py
Nifty Iron Condor Signal Bot — Main Runner

Modes (set via ENV or CLI arg):
  entry  → fetch chain, analyse, send entry signal (run at 9:25 AM)
  exit   → check current premium, send exit if needed (run every 5 min)
  test   → full dry run with console output only
"""

import sys
import os
import json
import logging
from datetime import datetime
import pytz

from nse_data import get_option_chain, get_vix, get_pcr
from strategy import build_iron_condor
from telegram_bot import (
    send_entry_signal, send_skip_signal,
    send_exit_signal, send_error, send_startup
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s"
)
log = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")
POSITION_FILE = "/tmp/open_position.json"


# ── Helpers ────────────────────────────────────────────────────────────────────
def is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    start = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    end   = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= now <= end


def save_position(sig):
    with open(POSITION_FILE, "w") as f:
        json.dump({
            "sell_ce_strike": sig.sell_ce_strike,
            "buy_ce_strike" : sig.buy_ce_strike,
            "sell_pe_strike": sig.sell_pe_strike,
            "buy_pe_strike" : sig.buy_pe_strike,
            "net_premium"   : sig.net_premium,
            "target_exit"   : sig.target_exit,
            "stop_loss"     : sig.stop_loss,
            "expiry"        : sig.expiry,
        }, f)


def load_position() -> dict | None:
    try:
        with open(POSITION_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def clear_position():
    try:
        os.remove(POSITION_FILE)
    except FileNotFoundError:
        pass


def get_current_premium(chain: dict, pos: dict) -> float:
    """Recalculate net premium from live option chain."""
    strikes = chain["strikes"]

    def ltp(strike, side):
        for s in strikes:
            if s["strike"] == strike:
                return s[f"{side}_ltp"]
        return 0.0

    sc = ltp(pos["sell_ce_strike"], "ce")
    bc = ltp(pos["buy_ce_strike"],  "ce")
    sp = ltp(pos["sell_pe_strike"], "pe")
    bp = ltp(pos["buy_pe_strike"],  "pe")
    return round((sc - bc) + (sp - bp), 2)


# ── Entry ──────────────────────────────────────────────────────────────────────
def run_entry(dry_run=False):
    log.info("=== ENTRY MODE ===")

    if not is_market_open() and not dry_run:
        log.warning("Market is closed. Skipping.")
        return

    log.info("Fetching NSE option chain…")
    chain = get_option_chain()
    if not chain:
        send_error("Could not fetch NSE option chain. NSE may be down.")
        return

    vix = get_vix()
    if vix is None:
        vix = 13.0   # fallback estimate
        log.warning("VIX fetch failed — using fallback 13.0")

    pcr = get_pcr(chain["strikes"])

    log.info(f"Spot={chain['spot']:.0f}  VIX={vix:.2f}  PCR={pcr:.2f}  Expiry={chain['expiry']}")
    log.info(f"Strikes available: {len(chain['strikes'])}")

    signal, skip_reason = build_iron_condor(chain, vix, pcr)

    if dry_run:
        if signal:
            print("\n" + "="*50)
            print("DRY RUN — SIGNAL WOULD BE SENT:")
            print(f"  Sell CE: {signal.sell_ce_strike} @ ₹{signal.sell_ce_prem}")
            print(f"  Buy  CE: {signal.buy_ce_strike}  @ ₹{signal.buy_ce_prem}")
            print(f"  Sell PE: {signal.sell_pe_strike} @ ₹{signal.sell_pe_prem}")
            print(f"  Buy  PE: {signal.buy_pe_strike}  @ ₹{signal.buy_pe_prem}")
            print(f"  Net Premium : ₹{signal.net_premium}")
            print(f"  Grade       : {signal.signal_grade} ({signal.signal_score}/100)")
            print(f"  Max Profit  : ₹{signal.max_profit}")
            print(f"  Max Loss    : ₹{signal.max_loss}")
            print("="*50)
        else:
            print(f"\nDRY RUN — NO SIGNAL: {skip_reason}")
        return

    if signal:
        log.info(f"Signal Grade={signal.signal_grade} Score={signal.signal_score} Premium=₹{signal.net_premium}")
        send_entry_signal(signal)
        save_position(signal)
    else:
        log.info(f"No signal: {skip_reason}")
        send_skip_signal(skip_reason, chain["spot"], vix)


# ── Exit Monitor ───────────────────────────────────────────────────────────────
def run_exit():
    log.info("=== EXIT CHECK ===")

    pos = load_position()
    if not pos:
        log.info("No open position to monitor.")
        return

    if not is_market_open():
        log.warning("Market closed.")
        return

    now = datetime.now(IST)
    force_exit = now >= now.replace(hour=15, minute=15, second=0, microsecond=0)

    chain = get_option_chain()
    if not chain:
        log.error("Could not fetch chain for exit check.")
        return

    current_premium = get_current_premium(chain, pos)
    log.info(f"Current premium: ₹{current_premium}  Target: ₹{pos['target_exit']}  SL: ₹{pos['stop_loss']}")

    exit_reason = None

    if force_exit:
        exit_reason = "⏰ Time-based exit (3:15 PM)"
    elif current_premium <= pos["target_exit"]:
        exit_reason = f"🎯 Target hit — premium decayed to ₹{current_premium}"
    elif current_premium >= pos["stop_loss"]:
        exit_reason = f"🛑 Stop Loss hit — premium rose to ₹{current_premium}"

    if exit_reason:
        # Build a minimal signal-like object for the message
        class _Sig:
            pass
        sig = _Sig()
        for k, v in pos.items():
            setattr(sig, k, v)

        send_exit_signal(sig, current_premium, exit_reason)
        clear_position()
        log.info(f"Exit signal sent: {exit_reason}")
    else:
        log.info("Holding position — no exit condition met.")


# ── Main ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "entry"

    if mode == "entry":
        run_entry()
    elif mode == "exit":
        run_exit()
    elif mode == "test":
        log.info("Running in DRY RUN / TEST mode…")
        run_entry(dry_run=True)
    else:
        print(f"Unknown mode: {mode}. Use: entry | exit | test")
        sys.exit(1)
