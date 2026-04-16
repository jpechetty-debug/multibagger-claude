"""
Fundamental Data Fetcher for Finology-Like Screener.

Fetches and caches per-stock fundamental profiles using:
- yfinance Ticker.info for core metrics (PE, PB, PEG, ROE, D/E, FCF, margins)
- yfinance Ticker.financials + balance_sheet for calculated ROCE and CAGR
- NSE India API (best-effort) for promoter holding / pledge data

All results cached as JSON in data/fundamentals/ with configurable TTL.
"""

import json
import logging
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional

import requests
import yfinance as yf

logger = logging.getLogger("IntradaySignals.FundamentalData")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CACHE_DIR = os.path.join("data", "fundamentals")
DEFAULT_TTL_HOURS = 24
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val, default=None):
    """Convert to float safely, returning *default* on failure."""
    if val is None:
        return default
    try:
        v = float(val)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _cagr(start_val: float, end_val: float, years: int) -> Optional[float]:
    """Compound annual growth rate.  Returns None if inputs are invalid."""
    if start_val is None or end_val is None or years <= 0:
        return None
    if start_val <= 0 or end_val <= 0:
        return None
    try:
        return ((end_val / start_val) ** (1.0 / years) - 1.0) * 100.0
    except (ZeroDivisionError, ValueError, OverflowError):
        return None


def _nse_symbol(yf_symbol: str) -> str:
    """Convert 'RELIANCE.NS' → 'RELIANCE' for NSE API."""
    return yf_symbol.replace(".NS", "").replace(".BO", "")

# ---------------------------------------------------------------------------
# NSE Promoter Data  (best-effort)
# ---------------------------------------------------------------------------

def _fetch_promoter_data_nse(symbol: str) -> dict:
    """
    Attempt to fetch promoter shareholding from NSE India.
    Returns dict with promoter_holding_pct, promoter_pledge_pct, or None values.
    """
    nse_sym = _nse_symbol(symbol)
    result = {
        "promoter_holding_pct": None,
        "promoter_pledge_pct": None,
        "institutional_holding_pct": None,
        "source": "nse_api",
    }

    try:
        # NSE requires a session cookie first
        session = requests.Session()
        session.headers.update(NSE_HEADERS)
        # Hit the main page to get cookies
        session.get("https://www.nseindia.com", timeout=5)
        time.sleep(0.3)  # Be polite

        url = f"https://www.nseindia.com/api/corporate-shareholding?symbol={nse_sym}"
        resp = session.get(url, timeout=10)

        if resp.status_code != 200:
            logger.debug(f"NSE API returned {resp.status_code} for {nse_sym}")
            return result

        data = resp.json()

        # Parse shareholding pattern
        if isinstance(data, list) and len(data) > 0:
            latest = data[0]  # Most recent quarter
            for category in latest.get("shareholdingPatterns", []):
                cat_name = category.get("category", "").lower()
                pct = _safe_float(category.get("percentage"))

                if "promoter" in cat_name and "group" not in cat_name:
                    result["promoter_holding_pct"] = pct
                    # Check pledge
                    pledge = _safe_float(category.get("pledgedPercentage"))
                    if pledge is not None:
                        result["promoter_pledge_pct"] = pledge
                elif "institution" in cat_name or "fii" in cat_name or "dii" in cat_name:
                    existing = result["institutional_holding_pct"] or 0
                    result["institutional_holding_pct"] = existing + (pct or 0)

    except requests.exceptions.RequestException as e:
        logger.debug(f"NSE API request failed for {nse_sym}: {e}")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.debug(f"NSE API parse error for {nse_sym}: {e}")

    return result

# ---------------------------------------------------------------------------
# Core: Build Fundamental Profile
# ---------------------------------------------------------------------------

def build_fundamental_profile(symbol: str, cache_ttl_hours: int = DEFAULT_TTL_HOURS) -> dict:
    """
    Build a complete fundamental profile for a single stock.

    Returns a dict with standardized fields, or an error dict if fetch fails.
    Fields that cannot be determined are set to None.
    """
    # ── Check Cache ──
    cached = _load_cache(symbol, cache_ttl_hours)
    if cached is not None:
        return cached

    logger.info(f"Fetching fundamentals for {symbol}...")
    profile = {
        "symbol": symbol,
        "fetch_time": datetime.now().isoformat(),
        "error": None,
        # Identity
        "company_name": None,
        "sector": None,
        "industry": None,
        # Valuation
        "market_cap_cr": None,
        "trailing_pe": None,
        "forward_pe": None,
        "price_to_book": None,
        "peg_ratio": None,
        "enterprise_value_cr": None,
        # Profitability
        "roe_pct": None,
        "roce_pct": None,
        "roa_pct": None,
        "profit_margin_pct": None,
        "operating_margin_pct": None,
        # Growth
        "revenue_growth_ttm_pct": None,
        "earnings_growth_ttm_pct": None,
        "eps_cagr_3y_pct": None,
        "revenue_cagr_3y_pct": None,
        # Balance Sheet
        "debt_to_equity": None,
        "current_ratio": None,
        "interest_coverage": None,
        # Cash Flow
        "free_cash_flow_cr": None,
        "fcf_positive": None,
        # Shareholding (best-effort)
        "promoter_holding_pct": None,
        "promoter_pledge_pct": None,
        "institutional_holding_pct": None,
        "promoter_data_source": None,
        # Price
        "current_price": None,
        "fifty_two_week_high": None,
        "fifty_two_week_low": None,
    }

    try:
        ticker = yf.Ticker(symbol)

        # ── 1. Info Dict ──
        info = ticker.info or {}

        profile["company_name"] = info.get("longName") or info.get("shortName")
        profile["sector"] = info.get("sector")
        profile["industry"] = info.get("industry")

        # Market cap in Crores (1 Cr = 10^7)
        raw_mcap = _safe_float(info.get("marketCap"))
        profile["market_cap_cr"] = round(raw_mcap / 1e7, 2) if raw_mcap else None

        raw_ev = _safe_float(info.get("enterpriseValue"))
        profile["enterprise_value_cr"] = round(raw_ev / 1e7, 2) if raw_ev else None

        profile["trailing_pe"] = _safe_float(info.get("trailingPE"))
        profile["forward_pe"] = _safe_float(info.get("forwardPE"))
        profile["price_to_book"] = _safe_float(info.get("priceToBook"))
        profile["peg_ratio"] = _safe_float(info.get("pegRatio"))

        roe = _safe_float(info.get("returnOnEquity"))
        profile["roe_pct"] = round(roe * 100, 2) if roe is not None else None

        roa = _safe_float(info.get("returnOnAssets"))
        profile["roa_pct"] = round(roa * 100, 2) if roa is not None else None

        pm = _safe_float(info.get("profitMargins"))
        profile["profit_margin_pct"] = round(pm * 100, 2) if pm is not None else None

        om = _safe_float(info.get("operatingMargins"))
        profile["operating_margin_pct"] = round(om * 100, 2) if om is not None else None

        # D/E — yfinance returns as percentage-like (e.g., 150 means 1.5x)
        raw_de = _safe_float(info.get("debtToEquity"))
        profile["debt_to_equity"] = round(raw_de / 100.0, 2) if raw_de is not None else None

        profile["current_ratio"] = _safe_float(info.get("currentRatio"))

        raw_fcf = _safe_float(info.get("freeCashflow"))
        profile["free_cash_flow_cr"] = round(raw_fcf / 1e7, 2) if raw_fcf else None
        profile["fcf_positive"] = raw_fcf > 0 if raw_fcf is not None else None

        rg = _safe_float(info.get("revenueGrowth"))
        profile["revenue_growth_ttm_pct"] = round(rg * 100, 2) if rg is not None else None

        eg = _safe_float(info.get("earningsGrowth"))
        profile["earnings_growth_ttm_pct"] = round(eg * 100, 2) if eg is not None else None

        profile["current_price"] = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        profile["fifty_two_week_high"] = _safe_float(info.get("fiftyTwoWeekHigh"))
        profile["fifty_two_week_low"] = _safe_float(info.get("fiftyTwoWeekLow"))

        # ── 2. Calculate ROCE from Financial Statements ──
        profile["roce_pct"] = _calculate_roce(ticker)

        # ── 3. Calculate Interest Coverage ──
        profile["interest_coverage"] = _calculate_interest_coverage(ticker)

        # ── 4. Calculate CAGR (EPS & Revenue, 3-year) ──
        eps_cagr, rev_cagr = _calculate_cagrs(ticker)
        profile["eps_cagr_3y_pct"] = eps_cagr
        profile["revenue_cagr_3y_pct"] = rev_cagr

        # ── 5. PEG Fallback ──
        # yfinance returns None for PEG on most Indian stocks.
        # Calculate manually: PEG = Trailing PE / EPS Growth Rate (%).
        # Use EPS CAGR 3Y as the growth input. Use earningsGrowth TTM as second fallback.
        if profile["peg_ratio"] is None and profile["trailing_pe"] is not None:
            growth_rate = eps_cagr  # 3-year EPS CAGR (already in %)
            if growth_rate is None or growth_rate <= 0:
                # Fallback to TTM earnings growth
                growth_rate = profile.get("earnings_growth_ttm_pct")
            if growth_rate is not None and growth_rate > 0:
                calculated_peg = round(profile["trailing_pe"] / growth_rate, 2)
                if 0 < calculated_peg < 50:  # Sanity check
                    profile["peg_ratio"] = calculated_peg
                    logger.debug(f"{symbol}: Calculated PEG={calculated_peg} from PE={profile['trailing_pe']}, Growth={growth_rate}%")

        # ── 6. Promoter Data (NSE, best-effort) ──
        promo = _fetch_promoter_data_nse(symbol)
        profile["promoter_holding_pct"] = promo.get("promoter_holding_pct")
        profile["promoter_pledge_pct"] = promo.get("promoter_pledge_pct")
        profile["institutional_holding_pct"] = promo.get("institutional_holding_pct")
        profile["promoter_data_source"] = promo.get("source")

    except Exception as e:
        logger.error(f"Error building profile for {symbol}: {e}", exc_info=True)
        profile["error"] = str(e)

    # ── Save Cache ──
    _save_cache(symbol, profile)

    return profile

# ---------------------------------------------------------------------------
# Calculated Metrics
# ---------------------------------------------------------------------------

def _calculate_roce(ticker) -> Optional[float]:
    """
    ROCE = EBIT / Capital Employed
    Capital Employed = Total Assets − Current Liabilities
    """
    try:
        financials = ticker.financials
        bs = ticker.balance_sheet

        if financials is None or financials.empty or bs is None or bs.empty:
            return None

        # Most recent column (latest annual)
        latest_fin = financials.iloc[:, 0]
        latest_bs = bs.iloc[:, 0]

        # EBIT (Operating Income is closest proxy in yfinance)
        ebit = None
        for label in ["EBIT", "Operating Income", "Ebit", "operatingIncome"]:
            if label in latest_fin.index:
                ebit = _safe_float(latest_fin[label])
                if ebit is not None:
                    break

        # Fallback: Net Income + Tax + Interest
        if ebit is None:
            net_income = None
            tax = None
            interest = None
            for label in ["Net Income", "Net Income Common Stockholders"]:
                if label in latest_fin.index:
                    net_income = _safe_float(latest_fin[label])
                    break
            for label in ["Tax Provision", "Income Tax Expense"]:
                if label in latest_fin.index:
                    tax = _safe_float(latest_fin[label])
                    break
            for label in ["Interest Expense", "Interest Expense Non Operating"]:
                if label in latest_fin.index:
                    interest = _safe_float(latest_fin[label])
                    break
            if net_income is not None:
                ebit = net_income + (tax or 0) + abs(interest or 0)

        if ebit is None:
            return None

        # Capital Employed = Total Assets - Current Liabilities
        total_assets = None
        current_liab = None

        for label in ["Total Assets", "totalAssets"]:
            if label in latest_bs.index:
                total_assets = _safe_float(latest_bs[label])
                break

        for label in ["Current Liabilities", "Total Current Liabilities", "currentLiabilities"]:
            if label in latest_bs.index:
                current_liab = _safe_float(latest_bs[label])
                break

        if total_assets is None or current_liab is None:
            return None

        capital_employed = total_assets - current_liab
        if capital_employed <= 0:
            return None

        roce = (ebit / capital_employed) * 100.0
        return round(roce, 2)

    except Exception as e:
        logger.debug(f"ROCE calculation failed: {e}")
        return None


def _calculate_interest_coverage(ticker) -> Optional[float]:
    """Interest Coverage = EBIT / Interest Expense."""
    try:
        financials = ticker.financials
        if financials is None or financials.empty:
            return None

        latest = financials.iloc[:, 0]

        ebit = None
        for label in ["EBIT", "Operating Income", "Ebit"]:
            if label in latest.index:
                ebit = _safe_float(latest[label])
                if ebit is not None:
                    break

        interest = None
        for label in ["Interest Expense", "Interest Expense Non Operating"]:
            if label in latest.index:
                interest = _safe_float(latest[label])
                if interest is not None:
                    interest = abs(interest)
                    break

        if ebit is not None and interest and interest > 0:
            return round(ebit / interest, 2)

        return None
    except Exception:
        return None


def _calculate_cagrs(ticker) -> tuple:
    """
    Calculate 3-year EPS CAGR and Revenue CAGR from annual financials.
    Returns (eps_cagr_pct, revenue_cagr_pct) — either may be None.
    """
    eps_cagr = None
    rev_cagr = None

    try:
        financials = ticker.financials
        if financials is None or financials.empty:
            return (None, None)

        # Columns are dates, most recent first → reverse for chronological
        cols = list(financials.columns)
        if len(cols) < 2:
            return (None, None)

        years_available = min(len(cols), 4)  # Up to 4 annual periods
        oldest_idx = years_available - 1
        years_gap = years_available - 1

        # ── Revenue CAGR ──
        for label in ["Total Revenue", "Revenue", "totalRevenue"]:
            if label in financials.index:
                rev_new = _safe_float(financials.loc[label].iloc[0])
                rev_old = _safe_float(financials.loc[label].iloc[oldest_idx])
                rev_cagr = _cagr(rev_old, rev_new, years_gap)
                break

        # ── EPS CAGR ──
        # yfinance financials may not have EPS directly; derive from Net Income / Shares
        for label in ["Basic EPS", "Diluted EPS"]:
            if label in financials.index:
                eps_new = _safe_float(financials.loc[label].iloc[0])
                eps_old = _safe_float(financials.loc[label].iloc[oldest_idx])
                eps_cagr = _cagr(eps_old, eps_new, years_gap)
                break

        # Fallback: Net Income as proxy for EPS direction
        if eps_cagr is None:
            for label in ["Net Income", "Net Income Common Stockholders"]:
                if label in financials.index:
                    ni_new = _safe_float(financials.loc[label].iloc[0])
                    ni_old = _safe_float(financials.loc[label].iloc[oldest_idx])
                    eps_cagr = _cagr(ni_old, ni_new, years_gap)
                    break

    except Exception as e:
        logger.debug(f"CAGR calculation failed: {e}")

    if eps_cagr is not None:
        eps_cagr = round(eps_cagr, 2)
    if rev_cagr is not None:
        rev_cagr = round(rev_cagr, 2)

    return (eps_cagr, rev_cagr)

# ---------------------------------------------------------------------------
# Cache Management
# ---------------------------------------------------------------------------

def _cache_path(symbol: str) -> str:
    safe_name = symbol.replace(".", "_").replace("&", "_")
    return os.path.join(CACHE_DIR, f"{safe_name}.json")


def _load_cache(symbol: str, ttl_hours: int) -> Optional[dict]:
    path = _cache_path(symbol)
    if not os.path.exists(path):
        return None
    try:
        mtime = os.path.getmtime(path)
        age_hours = (time.time() - mtime) / 3600
        if age_hours > ttl_hours:
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(symbol: str, profile: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(symbol)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Cache write failed for {symbol}: {e}")

# ---------------------------------------------------------------------------
# Batch Fetch
# ---------------------------------------------------------------------------

def fetch_universe_profiles(
    symbols: list,
    cache_ttl_hours: int = DEFAULT_TTL_HOURS,
    max_workers: int = 10,
    delay_between: float = 0.5,
) -> list:
    """
    Fetch fundamental profiles for an entire universe in parallel.

    Rate-limited to avoid API bans.
    Returns list of profile dicts (includes errors).
    """
    logger.info(f"Fetching fundamentals for {len(symbols)} symbols (max_workers={max_workers})...")

    results = []
    failed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for i, sym in enumerate(symbols):
            future = executor.submit(build_fundamental_profile, sym, cache_ttl_hours)
            futures[future] = sym
            # Stagger submissions to be polite
            if i % max_workers == 0 and i > 0:
                time.sleep(delay_between)

        for future in as_completed(futures):
            sym = futures[future]
            try:
                profile = future.result(timeout=60)
                results.append(profile)
                if profile.get("error"):
                    failed += 1
            except Exception as e:
                logger.error(f"Fatal error fetching {sym}: {e}")
                results.append({"symbol": sym, "error": str(e), "fetch_time": datetime.now().isoformat()})
                failed += 1

    logger.info(f"Fetched {len(results)} profiles ({failed} errors)")
    return results
