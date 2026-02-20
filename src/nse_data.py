"""
nse_data.py - Fixed after diagnostic
NSE returns 200 but JSON structure differs from expected.
We now handle multiple NSE response formats + Yahoo fallback.
"""

import requests
import random
import math
import time
import logging
from datetime import date, timedelta

log = logging.getLogger(__name__)
NIFTY_STEP = 50

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
]

def _h():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/option-chain",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }

def _nearest_thursday() -> str:
    today = date.today()
    days  = (3 - today.weekday()) % 7
    return (today + timedelta(days=days)).strftime("%d-%b-%Y").upper()


def _fetch_nse_raw() -> dict | None:
    """Fetch raw NSE response and log the actual structure."""
    session = requests.Session()
    session.headers.update(_h())
    try:
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(2)
        session.get("https://www.nseindia.com/option-chain", timeout=10)
        time.sleep(2)
        resp = session.get(
            "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            timeout=20
        )
        log.info(f"NSE status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            # Log top-level keys so we know the structure
            log.info(f"NSE top-level keys: {list(data.keys())}")
            return data
    except Exception as e:
        log.warning(f"NSE fetch failed: {e}")
    return None


def _parse_nse(data: dict, expiry: str) -> dict | None:
    """
    Try all known NSE response formats.
    NSE has changed their API structure multiple times.
    """
    # Format 1: data -> records -> data (old format)
    if "records" in data:
        try:
            records = data["records"]
            log.info(f"Format 1 keys: {list(records.keys())}")
            spot    = float(records.get("underlyingValue", 0))
            expiries = records.get("expiryDates", [])
            if expiries:
                expiry = expiries[0]
            rows = records.get("data", [])
            return _extract_strikes(rows, spot, expiry, "expiryDate")
        except Exception as e:
            log.warning(f"Format 1 parse failed: {e}")

    # Format 2: filtered -> data (newer format)
    if "filtered" in data:
        try:
            filtered = data["filtered"]
            log.info(f"Format 2 keys: {list(filtered.keys())}")
            spot = float(data.get("records", {}).get("underlyingValue", 0))
            if not spot:
                # Try alternate spot location
                spot = float(filtered.get("CE", {}).get("totOI", 0))
            rows = filtered.get("data", [])
            return _extract_strikes(rows, spot, expiry, "expiryDate")
        except Exception as e:
            log.warning(f"Format 2 parse failed: {e}")

    # Format 3: direct data array
    if "data" in data:
        try:
            log.info("Format 3: direct data array")
            rows = data["data"]
            spot = float(data.get("underlyingValue", 0))
            return _extract_strikes(rows, spot, expiry, "expiryDate")
        except Exception as e:
            log.warning(f"Format 3 parse failed: {e}")

    # Log actual structure to help debug further
    log.error(f"Unknown NSE format. Keys: {list(data.keys())}")
    for k, v in data.items():
        if isinstance(v, dict):
            log.error(f"  {k}: {list(v.keys())}")
        elif isinstance(v, list) and len(v) > 0:
            log.error(f"  {k}: list of {len(v)}, first item keys: {list(v[0].keys()) if isinstance(v[0], dict) else type(v[0])}")
        else:
            log.error(f"  {k}: {str(v)[:100]}")

    return None


def _extract_strikes(rows: list, spot: float, expiry: str, expiry_key: str) -> dict | None:
    """Extract strike data from NSE rows."""
    if not rows:
        log.warning("No rows in option chain data")
        return None

    log.info(f"Total rows: {len(rows)}, sample keys: {list(rows[0].keys()) if rows else 'none'}")

    strikes = []
    for row in rows:
        # Filter by expiry if expiry_key exists
        if expiry_key in row and row[expiry_key] != expiry:
            continue
        strike = row.get("strikePrice", 0)
        ce     = row.get("CE", {}) or {}
        pe     = row.get("PE", {}) or {}
        if not strike:
            continue
        strikes.append({
            "strike"  : float(strike),
            "ce_ltp"  : float(ce.get("lastPrice", 0) or 0),
            "pe_ltp"  : float(pe.get("lastPrice", 0) or 0),
            "ce_oi"   : float(ce.get("openInterest", 0) or 0),
            "pe_oi"   : float(pe.get("openInterest", 0) or 0),
            "ce_iv"   : float(ce.get("impliedVolatility", 0) or 0),
            "pe_iv"   : float(pe.get("impliedVolatility", 0) or 0),
            "ce_choi" : float(ce.get("changeinOpenInterest", 0) or 0),
            "pe_choi" : float(pe.get("changeinOpenInterest", 0) or 0),
        })

    if not strikes:
        # Try without expiry filter
        log.warning("No strikes with expiry filter — trying without filter")
        for row in rows:
            strike = row.get("strikePrice", 0)
            ce     = row.get("CE", {}) or {}
            pe     = row.get("PE", {}) or {}
            if not strike:
                continue
            strikes.append({
                "strike"  : float(strike),
                "ce_ltp"  : float(ce.get("lastPrice", 0) or 0),
                "pe_ltp"  : float(pe.get("lastPrice", 0) or 0),
                "ce_oi"   : float(ce.get("openInterest", 0) or 0),
                "pe_oi"   : float(pe.get("openInterest", 0) or 0),
                "ce_iv"   : float(ce.get("impliedVolatility", 0) or 0),
                "pe_iv"   : float(pe.get("impliedVolatility", 0) or 0),
                "ce_choi" : float(ce.get("changeinOpenInterest", 0) or 0),
                "pe_choi" : float(pe.get("changeinOpenInterest", 0) or 0),
            })

    strikes.sort(key=lambda x: x["strike"])
    log.info(f"Extracted {len(strikes)} strikes, spot={spot}")
    return {
        "spot"    : spot,
        "expiry"  : expiry,
        "strikes" : strikes,
        "source"  : "nse_live"
    }


def get_nifty_spot_yahoo() -> float | None:
    """Yahoo Finance — confirmed working from diagnostic."""
    for url in [
        "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI",
        "https://query2.finance.yahoo.com/v8/finance/chart/%5ENSEI",
    ]:
        try:
            resp = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=10)
            price = resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
            log.info(f"Yahoo spot: ₹{price}")
            return float(price)
        except Exception as e:
            log.warning(f"Yahoo spot failed ({url}): {e}")
    return None


def get_vix_yahoo() -> float | None:
    """Yahoo Finance VIX — confirmed working from diagnostic."""
    try:
        resp = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX",
            headers={"User-Agent": random.choice(USER_AGENTS)},
            timeout=10
        )
        vix = resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        log.info(f"Yahoo VIX: {vix}")
        return float(vix)
    except Exception as e:
        log.warning(f"Yahoo VIX failed: {e}")
    return None


def _synthetic_chain(spot: float, vix: float, expiry: str) -> dict:
    """Black-Scholes synthetic chain — last resort fallback."""
    log.warning("Using synthetic chain (Black-Scholes)")
    T     = 1 / 365.0
    sigma = vix / 100.0
    r     = 0.065

    def N(x):
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def bs(S, K, opt):
        if T <= 0:
            return max(0, S-K) if opt == "CE" else max(0, K-S)
        d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        if opt == "CE":
            return S*N(d1) - K*math.exp(-r*T)*N(d2)
        return K*math.exp(-r*T)*N(-d2) - S*N(-d1)

    atm = round(spot / NIFTY_STEP) * NIFTY_STEP
    strikes = []
    for k in range(atm - 500, atm + 550, NIFTY_STEP):
        dist = abs(k - atm)
        oi   = max(100, int(5000 * math.exp(-dist / 200)))
        strikes.append({
            "strike": float(k),
            "ce_ltp": round(max(0.05, bs(spot, k, "CE")), 2),
            "pe_ltp": round(max(0.05, bs(spot, k, "PE")), 2),
            "ce_oi": oi, "pe_oi": oi,
            "ce_iv": vix, "pe_iv": vix,
            "ce_choi": 0, "pe_choi": 0,
        })
    return {
        "spot"    : spot,
        "expiry"  : expiry,
        "strikes" : strikes,
        "source"  : "synthetic"
    }


def get_option_chain() -> dict | None:
    expiry = _nearest_thursday()
    log.info(f"Target expiry: {expiry}")

    # Step 1: Try NSE live
    log.info("Trying NSE live data...")
    raw = _fetch_nse_raw()
    if raw:
        parsed = _parse_nse(raw, expiry)
        if parsed and parsed["spot"] > 0 and len(parsed["strikes"]) > 5:
            log.info(f"✅ NSE live chain: {len(parsed['strikes'])} strikes")
            return parsed
        log.warning("NSE returned data but parsing failed — using Yahoo fallback")

    # Step 2: Yahoo Finance spot + synthetic chain
    log.info("Using Yahoo Finance + synthetic chain...")
    spot = get_nifty_spot_yahoo()
    if not spot:
        log.error("Cannot get spot price from any source!")
        return None

    vix = get_vix() or 14.0
    log.info(f"Building synthetic chain: spot=₹{spot}, vix={vix}")
    return _synthetic_chain(spot, vix, expiry)


def get_vix() -> float | None:
    v = get_vix_yahoo()
    return v if v else 14.0


def get_pcr(strikes: list) -> float:
    ce = sum(s["ce_oi"] for s in strikes)
    pe = sum(s["pe_oi"] for s in strikes)
    return round(pe / ce, 2) if ce else 1.0
