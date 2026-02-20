"""
nse_data.py - Fixed version with Yahoo Finance fallback
NSE blocks GitHub IPs, so we fallback to Yahoo Finance + synthetic chain.
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
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
]


def _h():
    return {"User-Agent": random.choice(USER_AGENTS), "Accept": "application/json"}


def _nearest_thursday() -> str:
    today = date.today()
    days  = (3 - today.weekday()) % 7
    return (today + timedelta(days=days)).strftime("%d-%b-%Y").upper()


def _fetch_nse() -> dict | None:
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/option-chain",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    })
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
            return resp.json()
    except Exception as e:
        log.warning(f"NSE failed: {e}")
    return None


def get_nifty_spot_yahoo() -> float | None:
    try:
        resp = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI",
            headers=_h(), timeout=10
        )
        price = resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        log.info(f"Yahoo spot: {price}")
        return float(price)
    except Exception as e:
        log.error(f"Yahoo spot failed: {e}")
        return None


def get_vix_yahoo() -> float | None:
    try:
        resp = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX",
            headers=_h(), timeout=10
        )
        vix = resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        log.info(f"Yahoo VIX: {vix}")
        return float(vix)
    except Exception as e:
        log.error(f"Yahoo VIX failed: {e}")
        return None


def _synthetic_chain(spot: float, vix: float, expiry: str) -> dict:
    log.warning("Using synthetic chain (Black-Scholes estimate)")
    T = 1 / 365.0
    sigma = vix / 100.0
    r = 0.065

    def N(x):
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def bs(S, K, opt):
        if T <= 0:
            return max(0, S-K) if opt == "CE" else max(0, K-S)
        d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
        d2 = d1 - sigma*math.sqrt(T)
        if opt == "CE":
            return S*N(d1) - K*math.exp(-r*T)*N(d2)
        return K*math.exp(-r*T)*N(-d2) - S*N(-d1)

    atm = round(spot / NIFTY_STEP) * NIFTY_STEP
    strikes = []
    for k in range(atm - 500, atm + 550, NIFTY_STEP):
        dist = abs(k - atm)
        oi   = max(100, int(5000 * math.exp(-dist / 200)))
        strikes.append({
            "strike": k,
            "ce_ltp": round(max(0.05, bs(spot, k, "CE")), 2),
            "pe_ltp": round(max(0.05, bs(spot, k, "PE")), 2),
            "ce_oi": oi, "pe_oi": oi,
            "ce_iv": vix, "pe_iv": vix,
            "ce_choi": 0, "pe_choi": 0,
        })
    return {"spot": spot, "expiry": expiry, "strikes": strikes, "source": "synthetic"}


def get_option_chain() -> dict | None:
    expiry = _nearest_thursday()

    # Try live NSE first
    raw = _fetch_nse()
    if raw:
        try:
            records = raw["records"]
            spot    = float(records["underlyingValue"])
            expiry  = records["expiryDates"][0]
            strikes = []
            for row in records["data"]:
                if row.get("expiryDate") != expiry:
                    continue
                ce = row.get("CE", {})
                pe = row.get("PE", {})
                strikes.append({
                    "strike": row["strikePrice"],
                    "ce_ltp": ce.get("lastPrice", 0),
                    "pe_ltp": pe.get("lastPrice", 0),
                    "ce_oi":  ce.get("openInterest", 0),
                    "pe_oi":  pe.get("openInterest", 0),
                    "ce_iv":  ce.get("impliedVolatility", 0),
                    "pe_iv":  pe.get("impliedVolatility", 0),
                    "ce_choi": ce.get("changeinOpenInterest", 0),
                    "pe_choi": pe.get("changeinOpenInterest", 0),
                })
            strikes.sort(key=lambda x: x["strike"])
            log.info(f"Live chain OK: {len(strikes)} strikes")
            return {"spot": spot, "expiry": expiry, "strikes": strikes, "source": "nse_live"}
        except Exception as e:
            log.error(f"NSE parse error: {e}")

    # Fallback to Yahoo + synthetic
    log.warning("Falling back to Yahoo Finance + synthetic chain")
    spot = get_nifty_spot_yahoo()
    if not spot:
        log.error("Cannot get spot from any source!")
        return None

    vix = get_vix() or 14.0
    return _synthetic_chain(spot, vix, expiry)


def get_vix() -> float | None:
    v = get_vix_yahoo()
    return v if v else 14.0


def get_pcr(strikes: list) -> float:
    ce = sum(s["ce_oi"] for s in strikes)
    pe = sum(s["pe_oi"] for s in strikes)
    return round(pe / ce, 2) if ce else 1.0
