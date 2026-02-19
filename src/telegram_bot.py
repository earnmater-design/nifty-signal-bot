"""
telegram_bot.py
Sends beautifully formatted Iron Condor signals to Telegram.
"""

import requests
import logging
import os

log = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
API_URL   = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def _send(text: str, parse_mode: str = "HTML") -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.")
        return False
    try:
        resp = requests.post(API_URL, json={
            "chat_id"   : CHAT_ID,
            "text"      : text,
            "parse_mode": parse_mode,
        }, timeout=15)
        resp.raise_for_status()
        log.info("Telegram message sent ✓")
        return True
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


def send_entry_signal(sig) -> bool:
    grade_emoji = {"A": "🟢", "B": "🟡", "C": "🟠"}.get(sig.signal_grade, "⚪")
    text = (
        f"<b>📊 NIFTY IRON CONDOR — ENTRY SIGNAL</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"📈 <b>Spot</b>   : ₹{sig.spot:,.0f}\n"
        f"🌡 <b>VIX</b>    : {sig.vix:.2f}\n"
        f"📉 <b>PCR</b>    : {sig.pcr:.2f}\n"
        f"📅 <b>Expiry</b> : {sig.expiry}\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"<b>LEGS TO PLACE:</b>\n"
        f"🔴 SELL <b>{sig.sell_ce_strike} CE</b>  @ ₹{sig.sell_ce_prem}\n"
        f"🟢 BUY  <b>{sig.buy_ce_strike} CE</b>  @ ₹{sig.buy_ce_prem}\n"
        f"🔴 SELL <b>{sig.sell_pe_strike} PE</b>  @ ₹{sig.sell_pe_prem}\n"
        f"🟢 BUY  <b>{sig.buy_pe_strike} PE</b>  @ ₹{sig.buy_pe_prem}\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"💰 <b>Net Premium</b>  : ₹{sig.net_premium} per unit\n"
        f"🎯 <b>Target Exit</b>  : ₹{sig.target_exit} (60% capture)\n"
        f"🛑 <b>Stop Loss</b>    : ₹{sig.stop_loss} (2× premium)\n"
        f"📈 <b>Max Profit</b>   : ₹{sig.max_profit:,.0f} / lot\n"
        f"📉 <b>Max Loss</b>     : ₹{sig.max_loss:,.0f} / lot\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"<b>OI ANALYSIS:</b>\n"
        f"🧱 CE Wall (Resistance): <b>{sig.ce_wall}</b>\n"
        f"🧱 PE Wall (Support)   : <b>{sig.pe_wall}</b>\n"
        f"⚖️ Max Pain            : <b>{sig.max_pain}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"{grade_emoji} <b>Signal Grade : {sig.signal_grade} ({sig.signal_score}/100)</b>\n"
        f"⏰ <b>Force exit by 3:15 PM IST</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"<i>⚠️ Signal only. Place trades manually on Zerodha.</i>"
    )
    return _send(text)


def send_skip_signal(reason: str, spot: float, vix: float) -> bool:
    text = (
        f"<b>🚫 NO SIGNAL TODAY</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"📌 <b>Reason</b>  : {reason}\n"
        f"📈 <b>Nifty</b>   : ₹{spot:,.0f}\n"
        f"🌡 <b>VIX</b>     : {vix:.2f}\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"✅ <i>Skipping is also a valid decision. Protect your capital.</i>"
    )
    return _send(text)


def send_exit_signal(sig, current_premium: float, reason: str) -> bool:
    pnl_per_unit = round(sig.net_premium - current_premium, 2)
    pnl_per_lot  = round(pnl_per_unit * 50, 2)
    pnl_emoji    = "🟢" if pnl_per_lot >= 0 else "🔴"
    text = (
        f"<b>🚨 EXIT SIGNAL — CLOSE NOW</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"📌 <b>Reason</b>          : {reason}\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"<b>LEGS TO CLOSE:</b>\n"
        f"🟢 BUY BACK  <b>{sig.sell_ce_strike} CE</b>\n"
        f"🔴 SELL      <b>{sig.buy_ce_strike} CE</b>\n"
        f"🟢 BUY BACK  <b>{sig.sell_pe_strike} PE</b>\n"
        f"🔴 SELL      <b>{sig.buy_pe_strike} PE</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"💵 Entry Premium   : ₹{sig.net_premium}\n"
        f"💵 Current Premium : ₹{current_premium}\n"
        f"{pnl_emoji} <b>Approx P&L : ₹{pnl_per_lot:+,.0f} / lot</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"<i>⚠️ Close ALL 4 legs simultaneously.</i>"
    )
    return _send(text)


def send_error(msg: str) -> bool:
    return _send(f"🤖 <b>Bot Error</b>\n<code>{msg}</code>")


def send_startup() -> bool:
    return _send(
        "🤖 <b>Nifty Iron Condor Bot is LIVE</b>\n"
        "Fetching option chain from NSE...\n"
        "Entry signal will arrive shortly ✅"
    )
