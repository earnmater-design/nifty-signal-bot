"""
main.py - Fixed version
Handles synthetic chain fallback properly.
"""

import sys
import os
import json
import logging
from datetime import datetime
import pytz

# Setup logging first
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s"
)
log = logging.getLogger(__name__)

# ── Test Telegram FIRST before anything else ──────────────────────────────────
def test_telegram():
    """Quick test to verify Telegram credentials work."""
    import requests
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token:
        log.error("TELEGRAM_BOT_TOKEN is not set!")
        return False
    if not chat_id:
        log.error("TELEGRAM_CHAT_ID is not set!")
        return False

    log.info(f"Token starts with: {token[:10]}...")
    log.info(f"Chat ID: {chat_id}")

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id"   : chat_id,
                "text"      : "🤖 <b>Bot test ping — Telegram is working!</b>",
                "parse_mode": "HTML"
            },
            timeout=15
        )
        result = resp.json()
        log.info(f"Telegram response: {result}")
        if result.get("ok"):
            log.info("✅ Telegram working!")
            return True
        else:
            log.error(f"Telegram error: {result.get('description')}")
            return False
    except Exception as e:
        log.error(f"Telegram request failed: {e}")
        return False


from nse_data import get_option_chain, get_vix, get_pcr
from strategy import build_iron_condor
from telegram_bot import (
    send_entry_signal, send_skip_signal,
    send_exit_signal, send_error
)

IST           = pytz.timezone("Asia/Kolkata")
POSITION_FILE = "/tmp/open_position.json"


def is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    start = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    end   = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= now <= end


def save_position(sig, expiry):
    with open(POSITION_FILE, "w") as f:
        json.dump({
            "sell_ce_strike": sig.sell_ce_strike,
            "buy_ce_strike" : sig.buy_ce_strike,
            "sell_pe_strike": sig.sell_pe_strike,
            "buy_pe_strike" : sig.buy_pe_strike,
            "net_premium"   : sig.net_premium,
            "target_exit"   : sig.target_exit,
            "stop_loss"     : sig.stop_loss,
            "expiry"        : expiry,
        }, f)


def load_position():
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


def get_current_premium(chain, pos):
    def ltp(strike, side):
        for s in chain["strikes"]:
            if s["strike"] == strike:
                return s[f"{side}_ltp"]
        return 0.0
    sc = ltp(pos["sell_ce_strike"], "ce")
    bc = ltp(pos["buy_ce_strike"],  "ce")
    sp = ltp(pos["sell_pe_strike"], "pe")
    bp = ltp(pos["buy_pe_strike"],  "pe")
    return round((sc - bc) + (sp - bp), 2)


def run_entry(dry_run=False):
    log.info("=== ENTRY MODE ===")

    # Step 1: Test Telegram first
    log.info("Step 1: Testing Telegram connection...")
    tg_ok = test_telegram()
    if not tg_ok:
        log.error("Telegram not working — check your secrets!")
        return

    # Step 2: Fetch market data
    log.info("Step 2: Fetching market data...")
    chain = get_option_chain()

    if chain is None:
        log.error("All data sources failed!")
        send_error("All data sources failed. Cannot generate signal today.")
        return

    source = chain.get("source", "unknown")
    log.info(f"Data source: {source}, spot={chain['spot']}, strikes={len(chain['strikes'])}")

    vix = get_vix() or 14.0
    pcr = get_pcr(chain["strikes"])

    log.info(f"Spot={chain['spot']:.0f}  VIX={vix:.2f}  PCR={pcr:.2f}")

    # Step 3: Build signal
    log.info("Step 3: Building Iron Condor signal...")
    signal, skip_reason = build_iron_condor(chain, vix, pcr)

    if dry_run:
        if signal:
            print(f"\n{'='*50}")
            print("DRY RUN — Signal details:")
            print(f"  Source      : {source}")
            print(f"  Spot        : {chain['spot']}")
            print(f"  VIX         : {vix}")
            print(f"  Sell CE     : {signal.sell_ce_strike} @ ₹{signal.sell_ce_prem}")
            print(f"  Buy  CE     : {signal.buy_ce_strike}  @ ₹{signal.buy_ce_prem}")
            print(f"  Sell PE     : {signal.sell_pe_strike} @ ₹{signal.sell_pe_prem}")
            print(f"  Buy  PE     : {signal.buy_pe_strike}  @ ₹{signal.buy_pe_prem}")
            print(f"  Net Premium : ₹{signal.net_premium}")
            print(f"  Grade       : {signal.signal_grade} ({signal.signal_score}/100)")
            print(f"{'='*50}")
        else:
            print(f"\nDRY RUN — No signal: {skip_reason}")
        return

    # Step 4: Send signal
    log.info("Step 4: Sending Telegram signal...")
    if signal:
        # Add synthetic warning to signal if needed
        signal.is_synthetic = (source == "synthetic")
        send_entry_signal(signal)
        save_position(signal, chain["expiry"])
        log.info("Entry signal sent!")
    else:
        log.info(f"No signal today: {skip_reason}")
        send_skip_signal(skip_reason, chain["spot"], vix)


def run_exit():
    log.info("=== EXIT CHECK ===")
    pos = load_position()
    if not pos:
        log.info("No open position.")
        return

    chain = get_option_chain()
    if not chain:
        return

    now = datetime.now(IST)
    force_exit = now >= now.replace(hour=15, minute=15, second=0, microsecond=0)
    current_premium = get_current_premium(chain, pos)
    log.info(f"Premium now: ₹{current_premium} | Target: ₹{pos['target_exit']} | SL: ₹{pos['stop_loss']}")

    exit_reason = None
    if force_exit:
        exit_reason = "⏰ Time-based exit (3:15 PM)"
    elif current_premium <= pos["target_exit"]:
        exit_reason = f"🎯 Target hit — premium at ₹{current_premium}"
    elif current_premium >= pos["stop_loss"]:
        exit_reason = f"🛑 Stop Loss hit — premium at ₹{current_premium}"

    if exit_reason:
        class _Sig:
            pass
        sig = _Sig()
        for k, v in pos.items():
            setattr(sig, k, v)
        send_exit_signal(sig, current_premium, exit_reason)
        clear_position()


def run_telegram_test():
    """Just test Telegram — nothing else."""
    log.info("=== TELEGRAM TEST ===")
    ok = test_telegram()
    if ok:
        log.info("✅ Telegram works! Check your chat for the test message.")
    else:
        log.error("❌ Telegram failed. Check your BOT_TOKEN and CHAT_ID secrets.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "entry"

    if mode == "entry":
        run_entry()
    elif mode == "exit":
        run_exit()
    elif mode == "test":
        run_entry(dry_run=True)
    elif mode == "tgtest":
        run_telegram_test()
    else:
        print(f"Unknown mode: {mode}. Use: entry | exit | test | tgtest")
        sys.exit(1)
