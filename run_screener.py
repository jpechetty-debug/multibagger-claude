"""
Finology-Like Fundamental Screener — CLI Runner.

Usage:
    python run_screener.py                          # Full universe scan
    python run_screener.py --top 20                 # Show top 20 ranked
    python run_screener.py --export csv             # Export to CSV
    python run_screener.py --symbol RELIANCE.NS     # Single stock deep profile
    python run_screener.py --clear-cache             # Clear cached fundamentals
"""

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime

import yaml

# Fix Windows console encoding
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(name)-35s | %(levelname)-5s | %(message)s",
        datefmt="%H:%M:%S",
    )


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# ---------------------------------------------------------------------------
# Display Helpers
# ---------------------------------------------------------------------------

def print_header(text: str, char: str = "=", width: int = 90):
    print(f"\n{char * width}")
    print(f"  {text}")
    print(f"{char * width}")


def print_profile(profile: dict):
    """Pretty-print a single stock's fundamental profile."""
    print_header(f"📊 {profile.get('company_name', profile['symbol'])} ({profile['symbol']})")

    sections = [
        ("Valuation", [
            ("Market Cap", f"{profile.get('market_cap_cr')} Cr"),
            ("PE (Trailing)", profile.get("trailing_pe")),
            ("PE (Forward)", profile.get("forward_pe")),
            ("P/B", profile.get("price_to_book")),
            ("PEG", profile.get("peg_ratio")),
            ("Price", profile.get("current_price")),
        ]),
        ("Profitability", [
            ("ROCE", f"{profile.get('roce_pct')}%"),
            ("ROE", f"{profile.get('roe_pct')}%"),
            ("ROA", f"{profile.get('roa_pct')}%"),
            ("Profit Margin", f"{profile.get('profit_margin_pct')}%"),
            ("Operating Margin", f"{profile.get('operating_margin_pct')}%"),
        ]),
        ("Growth", [
            ("Rev Growth (TTM)", f"{profile.get('revenue_growth_ttm_pct')}%"),
            ("Earnings Growth (TTM)", f"{profile.get('earnings_growth_ttm_pct')}%"),
            ("EPS CAGR 3Y", f"{profile.get('eps_cagr_3y_pct')}%"),
            ("Revenue CAGR 3Y", f"{profile.get('revenue_cagr_3y_pct')}%"),
        ]),
        ("Balance Sheet", [
            ("Debt/Equity", profile.get("debt_to_equity")),
            ("Current Ratio", profile.get("current_ratio")),
            ("Interest Coverage", profile.get("interest_coverage")),
            ("Free Cash Flow", f"{profile.get('free_cash_flow_cr')} Cr"),
        ]),
        ("Shareholding", [
            ("Promoter Holding", f"{profile.get('promoter_holding_pct')}%"),
            ("Promoter Pledge", f"{profile.get('promoter_pledge_pct')}%"),
            ("Institutional", f"{profile.get('institutional_holding_pct')}%"),
            ("Data Source", profile.get("promoter_data_source")),
        ]),
    ]

    for section_name, fields in sections:
        print(f"\n  +-- {section_name} --")
        for label, value in fields:
            val_str = str(value) if value is not None else "--"
            print(f"  |  {label:<25} {val_str}")
        print(f"  +{'-' * 40}")


def print_results_table(results: list, top_n: int = 50):
    """Print a formatted results table."""
    if not results:
        print("\n  ⚠  No stocks passed the fundamental gate.")
        return

    display = results[:top_n]

    print_header(f"🏆 Top {len(display)} Stocks by Fundamental Score")

    # Header
    print(f"  {'Rank':<5} {'Symbol':<15} {'Score':<7} {'ROCE%':<8} {'PEG':<6} "
          f"{'D/E':<6} {'EPS CAGR':<10} {'MCap Cr':<10} {'Flags':<6}")
    print(f"  {'─'*5} {'─'*15} {'─'*7} {'─'*8} {'─'*6} {'─'*6} {'─'*10} {'─'*10} {'─'*6}")

    for r in display:
        flag_str = ""
        if r.get("high_flags", 0) > 0:
            flag_str = f"🔴×{r['high_flags']}"
        elif r.get("flag_count", 0) > 0:
            flag_str = f"🟡×{r['flag_count']}"
        else:
            flag_str = "✅"

        roce = f"{r.get('roce_pct', 0):.1f}" if r.get("roce_pct") is not None else "—"
        peg = f"{r.get('peg_ratio', 0):.2f}" if r.get("peg_ratio") is not None else "—"
        de = f"{r.get('debt_to_equity', 0):.2f}" if r.get("debt_to_equity") is not None else "—"
        eps = f"{r.get('eps_cagr_3y_pct', 0):.1f}%" if r.get("eps_cagr_3y_pct") is not None else "—"
        mcap = f"{r.get('market_cap_cr', 0):,.0f}" if r.get("market_cap_cr") is not None else "—"

        print(f"  {r['rank']:<5} {r['symbol']:<15} {r['score']:<7.1f} {roce:<8} {peg:<6} "
              f"{de:<6} {eps:<10} {mcap:<10} {flag_str}")

    print()


def print_flag_details(results: list, top_n: int = 20):
    """Print detailed flags for flagged stocks."""
    flagged = [r for r in results[:top_n] if r.get("flag_count", 0) > 0]
    if not flagged:
        return

    print_header("⚠ Qualitative Flags (Manual Review Required)")

    for r in flagged:
        print(f"\n  {r['symbol']} (Score: {r['score']:.1f}):")
        for f in r["flags"]:
            severity_icon = "🔴" if f["severity"] == "HIGH" else "🟡"
            print(f"    {severity_icon} [{f['flag']}] {f['reason']}")


def print_rejection_summary(rejected: list, show_max: int = 20):
    """Print summary of rejected stocks."""
    if not rejected:
        return

    print_header(f"❌ Rejected Stocks ({len(rejected)} total, showing top {min(show_max, len(rejected))})")

    for r in rejected[:show_max]:
        print(f"  • {r['symbol']}: {r['reason'][:80]}")

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_results(output: dict, fmt: str = "json"):
    """Export screener results to file."""
    os.makedirs("reports", exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d_%H%M")

    if fmt == "csv":
        import csv
        path = f"reports/screener_results_{date_str}.csv"
        results = output["results"]
        if not results:
            print("  No results to export.")
            return

        fieldnames = [
            "rank", "symbol", "company_name", "sector", "score",
            "market_cap_cr", "roce_pct", "roe_pct", "peg_ratio",
            "debt_to_equity", "eps_cagr_3y_pct", "revenue_cagr_3y_pct",
            "promoter_holding_pct", "free_cash_flow_cr", "trailing_pe",
            "current_price", "flag_count", "high_flags",
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in results:
                writer.writerow(r)

        print(f"\n  ✅ Exported to {path} ({len(results)} rows)")

    else:
        path = f"reports/screener_results_{date_str}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)
        print(f"\n  ✅ Exported to {path}")

    return path

# ---------------------------------------------------------------------------
# Telegram Notification
# ---------------------------------------------------------------------------

def send_telegram_summary(config: dict, results: list, top_n: int = 10):
    """Send top picks via Telegram."""
    tg_cfg = config.get("telegram", {})
    if not tg_cfg.get("enabled", False):
        return

    try:
        from src.telegram_bot import TelegramBot
        bot = TelegramBot(tg_cfg["bot_token"], tg_cfg["chat_id"], True)

        msg = "🏆 *Finology Screener Results*\n\n"
        for r in results[:top_n]:
            flag_icon = "⚠" if r.get("flag_count", 0) > 0 else "✅"
            msg += (f"{r['rank']}. *{r['symbol']}* — Score {r['score']:.1f} {flag_icon}\n"
                    f"   ROCE {r.get('roce_pct', '—')}% | PEG {r.get('peg_ratio', '—')} | "
                    f"D/E {r.get('debt_to_equity', '—')}\n")

        msg += f"\n_Total passed: {len(results)}_"
        bot.send_message(msg)
        print(f"\n  📱 Telegram notification sent (top {top_n})")

    except Exception as e:
        print(f"\n  ⚠  Telegram send failed: {e}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Finology-Like Fundamental Stock Screener")
    parser.add_argument("--top", type=int, default=30, help="Show top N results (default: 30)")
    parser.add_argument("--export", choices=["json", "csv"], help="Export results to file")
    parser.add_argument("--symbol", type=str, help="Deep-dive single stock (e.g., RELIANCE.NS)")
    parser.add_argument("--clear-cache", action="store_true", help="Clear fundamental data cache")
    parser.add_argument("--config", type=str, default="config/config.yaml", help="Config file path")
    parser.add_argument("--notify", action="store_true", help="Send Telegram notification")
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level")
    args = parser.parse_args()

    setup_logging(args.log_level)

    # Load config
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"  ❌ Config file not found: {args.config}")
        sys.exit(1)

    # Clear cache
    if args.clear_cache:
        cache_dir = os.path.join("data", "fundamentals")
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            print("  🗑  Cache cleared.")
        else:
            print("  ℹ  No cache to clear.")
        return

    # Import after config loaded
    from src.fundamental_data import build_fundamental_profile, fetch_universe_profiles
    from src.fundamental_screener import FinologyScreener

    screener_cfg = config.get("screener", {})
    cache_ttl = screener_cfg.get("cache_ttl_hours", 24)
    max_workers = screener_cfg.get("max_parallel_fetches", 10)

    # Single stock mode
    if args.symbol:
        sym = args.symbol if "." in args.symbol else f"{args.symbol}.NS"
        profile = build_fundamental_profile(sym, cache_ttl)

        if profile.get("error"):
            print(f"\n  ❌ Error fetching {sym}: {profile['error']}")
            sys.exit(1)

        print_profile(profile)

        # Run through screener for gate/flag/rank analysis
        screener = FinologyScreener(config)
        gate = screener.hard_gate(profile)
        flags = screener.qualitative_flags(profile)
        rank = screener.fundamental_rank(profile)

        print_header("Gate Result")
        status = "✅ PASSED" if gate["passed"] else "❌ REJECTED"
        print(f"  Status: {status}")
        for name, cr in gate["criteria_results"].items():
            icon = "✅" if cr["passed"] else "❌"
            val_display = str(cr['value']) if cr['value'] is not None else "N/A"
            print(f"  {icon} {name:<22} Value: {val_display:<10} Threshold: {cr['threshold']}")

        if flags:
            print_header("Flags")
            for f in flags:
                sev = "🔴" if f["severity"] == "HIGH" else "🟡"
                print(f"  {sev} [{f['flag']}] {f['reason']}")

        print_header(f"Fundamental Score: {rank['total_score']:.1f}/100")
        for name, comp in rank["components"].items():
            print(f"  {name:<12} Score: {comp['score']:.1f}  (Weight: {comp['weight']:.0%})")

        return

    # Full universe mode
    universe = config.get("symbols", [])
    if not universe:
        print("  ❌ No symbols in config.")
        sys.exit(1)

    print_header(f"Finology Screener — Scanning {len(universe)} stocks")
    print(f"  Mode: {screener_cfg.get('mode', 'finology_strict')}")
    print(f"  Cache TTL: {cache_ttl}h | Workers: {max_workers}")
    print()

    # Fetch fundamentals
    profiles = fetch_universe_profiles(universe, cache_ttl, max_workers)

    # Run screener
    screener = FinologyScreener(config)
    output = screener.run(profiles)

    # Display results
    print_header("Pipeline Summary")
    print(f"  Total Screened:   {output['total_screened']}")
    print(f"  Passed Gate:      {output['passed_gate']}")
    print(f"  Rejected:         {output['rejected_count']}")
    print(f"  Mode:             {output['mode']}")

    print_results_table(output["results"], top_n=args.top)
    print_flag_details(output["results"], top_n=args.top)
    print_rejection_summary(output["rejected"], show_max=10)

    # Export
    if args.export:
        export_results(output, args.export)

    # Always save JSON for dashboard
    os.makedirs("reports", exist_ok=True)
    latest_path = "reports/screener_latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  💾 Saved latest results to {latest_path}")

    # Telegram
    if args.notify:
        send_telegram_summary(config, output["results"], top_n=args.top)


if __name__ == "__main__":
    main()
