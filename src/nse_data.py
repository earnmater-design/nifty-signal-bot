"""
nse_data.py
Fetches live Nifty option chain from NSE India's unofficial public API.
No API key needed. Completely free.
"""

import requests
import json
import time
import logging

log = logging.getLogger(__name__)

NSE_OC_URL  = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
NSE_VIX_URL = "https://www.nseindia.com/api/allIndices"
NSE_HOME    = "https://www.nseindia.com"

# NSE requires browser-like headers + a session cookie
HEADERS = {
    "User-Agent"      : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept"          : "application/json, text/plain, */*",
    "Accept-Language" : "en-US,en;q=0.9",
    "Accept-Encoding" : "gzip, deflate, br",
    "Referer"         : "https://www.nseindia.com/option-chain",
    "Connection"      : "keep-alive",
    "sec-ch-ua"       : '"Not_A Brand";v="8", "Chromium";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-fetch-dest"  : "empty",
    "sec-fetch-mode"  : "cors",
    "sec-fetch-site"  : "same-origin",
}


def _get_session() -> requests.Session:
    """Create a session with NSE cookies (required to bypass basic protection)."""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        # Hit homepage first to get cookies
        session.get(NSE_HOME, timeout=10)
        time.sleep(1.5)
        # Hit option chain page to get additional cookies
        session.get("https://www.nseindia.com/option-chain", timeout=10)
        time.sleep(1.0)
    except Exception as e:
        log.warning(f"Session warmup warning: {e}")
    return session


def get_option_chain() -> dict | None:
    """
    Returns parsed option chain data:
    {
      spot: float,
      vix: float,
      expiry: str,
      strikes: [ { strike, ce_ltp, pe_ltp, ce_oi, pe_oi, ce_iv, pe_iv }, ... ]
    }
    """
    session = _get_session()
    try:
        resp = session.get(NSE_OC_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.error(f"Option chain fetch failed: {e}")
        return None

    try:
        records   = data["records"]
        spot      = float(records["underlyingValue"])
        expiries  = records["expiryDates"]
        # Pick current week (nearest) expiry
        expiry    = expiries[0]
        raw       = records["data"]

        strikes = []
        for row in raw:
            if row.get("expiryDate") != expiry:
                continue
            strike = row["strikePrice"]
            ce     = row.get("CE", {})
            pe     = row.get("PE", {})
            strikes.append({
                "strike" : strike,
                "ce_ltp" : ce.get("lastPrice", 0),
                "pe_ltp" : pe.get("lastPrice", 0),
                "ce_oi"  : ce.get("openInterest", 0),
                "pe_oi"  : pe.get("openInterest", 0),
                "ce_iv"  : ce.get("impliedVolatility", 0),
                "pe_iv"  : pe.get("impliedVolatility", 0),
                "ce_choi": ce.get("changeinOpenInterest", 0),
                "pe_choi": pe.get("changeinOpenInterest", 0),
            })

        # Sort by strike
        strikes.sort(key=lambda x: x["strike"])
        return {"spot": spot, "expiry": expiry, "strikes": strikes}

    except Exception as e:
        log.error(f"Option chain parse error: {e}")
        return None


def get_vix() -> float | None:
    """Fetch India VIX from NSE indices API."""
    session = _get_session()
    try:
        resp = session.get(NSE_VIX_URL, timeout=10)
        resp.raise_for_status()
        indices = resp.json().get("data", [])
        for idx in indices:
            if "VIX" in idx.get("index", "").upper():
                return float(idx["last"])
    except Exception as e:
        log.warning(f"VIX fetch failed: {e}")
    return None


def get_pcr(strikes: list) -> float:
    """Calculate Put-Call Ratio from OI data."""
    total_ce_oi = sum(s["ce_oi"] for s in strikes)
    total_pe_oi = sum(s["pe_oi"] for s in strikes)
    if total_ce_oi == 0:
        return 1.0
    return round(total_pe_oi / total_ce_oi, 2)
