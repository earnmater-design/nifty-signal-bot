"""
debug.py
Run this to diagnose exactly what is failing.
Mode: python debug.py
"""

import requests
import json
import sys
import os

print("=" * 60)
print("NIFTY BOT — FULL DIAGNOSTIC")
print("=" * 60)

# ── TEST 1: Basic internet ────────────────────────────────────
print("\n[TEST 1] Basic internet connectivity...")
try:
    r = requests.get("https://www.google.com", timeout=10)
    print(f"  ✅ Google reachable: {r.status_code}")
except Exception as e:
    print(f"  ❌ No internet: {e}")
    sys.exit(1)

# ── TEST 2: Yahoo Finance spot ────────────────────────────────
print("\n[TEST 2] Yahoo Finance — Nifty spot price...")
try:
    r = requests.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10
    )
    data  = r.json()
    price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    print(f"  ✅ Nifty Spot: ₹{price}")
except Exception as e:
    print(f"  ❌ Yahoo Finance failed: {e}")
    try:
        print(f"     Response: {r.text[:300]}")
    except:
        pass

# ── TEST 3: Yahoo Finance VIX ─────────────────────────────────
print("\n[TEST 3] Yahoo Finance — India VIX...")
try:
    r = requests.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10
    )
    data = r.json()
    vix  = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    print(f"  ✅ India VIX: {vix}")
except Exception as e:
    print(f"  ❌ VIX failed: {e}")

# ── TEST 4: Yahoo Finance alternative endpoint ────────────────
print("\n[TEST 4] Yahoo Finance — alternative v7 endpoint...")
try:
    r = requests.get(
        "https://query2.finance.yahoo.com/v8/finance/chart/%5ENSEI",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        timeout=10
    )
    data  = r.json()
    price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    print(f"  ✅ Nifty Spot (v2): ₹{price}")
except Exception as e:
    print(f"  ❌ v2 failed: {e}")

# ── TEST 5: NSE direct ────────────────────────────────────────
print("\n[TEST 5] NSE India direct API...")
try:
    import time
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/option-chain",
    })
    session.get("https://www.nseindia.com", timeout=10)
    time.sleep(2)
    r = session.get(
        "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
        timeout=15
    )
    print(f"  NSE status code: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        spot = data["records"]["underlyingValue"]
        print(f"  ✅ NSE working! Spot: {spot}")
    else:
        print(f"  ❌ NSE blocked. Response: {r.text[:200]}")
except Exception as e:
    print(f"  ❌ NSE failed: {e}")

# ── TEST 6: Telegram ──────────────────────────────────────────
print("\n[TEST 6] Telegram Bot API...")
token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
if not token or not chat_id:
    print("  ⚠️  Secrets not set (normal if running locally)")
else:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "🔧 Diagnostic test — all systems OK!"},
            timeout=10
        )
        result = r.json()
        if result.get("ok"):
            print("  ✅ Telegram working!")
        else:
            print(f"  ❌ Telegram error: {result.get('description')}")
    except Exception as e:
        print(f"  ❌ Telegram failed: {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
