"""
Finology-Like Fundamental Screener — 3-Stage Pipeline.

Stage 1: Hard Fundamental Gate   (binary pass/fail on 9 criteria)
Stage 2: Qualitative Flag Bucket (marks for manual review, never auto-eliminates)
Stage 3: Pure Fundamental Rank   (0–100 score, zero technical contamination)

Usage:
    from src.fundamental_screener import FinologyScreener
    screener = FinologyScreener(config)
    results = screener.run(profiles)
"""

import logging
from typing import Optional

logger = logging.getLogger("IntradaySignals.FundamentalScreener")

# ---------------------------------------------------------------------------
# BFSI sector detection
# ---------------------------------------------------------------------------
BFSI_KEYWORDS = {
    "financial services", "banks", "banking", "insurance",
    "nbfc", "credit", "capital markets", "asset management",
    "diversified financials", "specialty finance",
}


def _is_bfsi(sector: Optional[str], industry: Optional[str]) -> bool:
    """Auto-detect if a stock belongs to BFSI based on yfinance sector/industry."""
    text = f"{sector or ''} {industry or ''}".lower()
    return any(kw in text for kw in BFSI_KEYWORDS)

# ---------------------------------------------------------------------------
# Default thresholds (overridden by config.yaml)
# ---------------------------------------------------------------------------
DEFAULT_HARD_GATE = {
    "min_market_cap_cr": 500,
    "min_roce_pct": 15,
    "min_eps_cagr_3y_pct": 12,
    "min_revenue_cagr_3y_pct": 10,
    "peg_range": [0.5, 2.5],
    "max_debt_equity": 1.5,
    "max_debt_equity_non_bfsi": 0.5,
    "min_promoter_holding_pct": 40,
    "min_roe_pct": 12,
    "require_positive_fcf": True,
}

DEFAULT_RANKING_WEIGHTS = {
    "roce": 0.25,
    "growth": 0.25,
    "valuation": 0.20,
    "quality": 0.15,
    "promoter": 0.15,
}

# ---------------------------------------------------------------------------
# Screener Class
# ---------------------------------------------------------------------------


class FinologyScreener:
    """
    Three-stage fundamental screener aligned with Finology's methodology.

    Instantiate with the full config dict (reads screener sub-key).
    Call .run(profiles) with a list of fundamental profile dicts.
    """

    def __init__(self, config: dict):
        screener_cfg = config.get("screener", {})
        self.mode = screener_cfg.get("mode", "finology_strict")
        self.gate_cfg = {**DEFAULT_HARD_GATE, **screener_cfg.get("hard_gate", {})}
        self.weights = {**DEFAULT_RANKING_WEIGHTS, **screener_cfg.get("ranking_weights", {})}

        # Normalize weights to sum to 1.0
        total_w = sum(self.weights.values())
        if total_w > 0:
            self.weights = {k: v / total_w for k, v in self.weights.items()}

    # ======================================================================
    # Stage 1: Hard Fundamental Gate
    # ======================================================================

    def hard_gate(self, profile: dict) -> dict:
        """
        Binary pass/fail on 9 criteria.
        BFSI exceptions: ROCE → ROE substitution, D/E relaxed, FCF waived.

        Returns:
            {
                "passed": bool,
                "criteria_results": {criterion_name: {"passed": bool, "value": ..., "threshold": ...}},
                "rejection_reasons": [str, ...]
            }
        """
        results = {}
        rejections = []
        g = self.gate_cfg

        is_bfsi = _is_bfsi(profile.get("sector"), profile.get("industry"))

        # 1. Market Cap ≥ threshold
        mcap = profile.get("market_cap_cr")
        threshold = g["min_market_cap_cr"]
        passed = mcap is not None and mcap >= threshold
        results["market_cap"] = {"passed": passed, "value": mcap, "threshold": f"≥ {threshold} Cr"}
        if not passed:
            rejections.append(f"Market Cap {mcap} < {threshold} Cr")

        # 2. ROCE ≥ threshold (BFSI: use ROE instead since ROCE is meaningless for banks)
        if is_bfsi:
            roe = profile.get("roe_pct")
            threshold = g["min_roe_pct"]
            passed = roe is not None and roe >= threshold
            results["roce"] = {
                "passed": passed,
                "value": roe,
                "threshold": f"≥ {threshold}% (BFSI→ROE proxy)",
            }
            if not passed:
                rejections.append(f"ROE {roe}% < {threshold}% (BFSI substitute for ROCE)")
        else:
            roce = profile.get("roce_pct")
            threshold = g["min_roce_pct"]
            passed = roce is not None and roce >= threshold
            results["roce"] = {"passed": passed, "value": roce, "threshold": f"≥ {threshold}%"}
            if not passed:
                rejections.append(f"ROCE {roce}% < {threshold}%")

        # 3. EPS CAGR 3Y ≥ threshold
        eps_cagr = profile.get("eps_cagr_3y_pct")
        threshold = g["min_eps_cagr_3y_pct"]
        passed = eps_cagr is not None and eps_cagr >= threshold
        results["eps_cagr_3y"] = {"passed": passed, "value": eps_cagr, "threshold": f"≥ {threshold}%"}
        if not passed:
            rejections.append(f"EPS CAGR 3Y {eps_cagr}% < {threshold}%")

        # 4. Revenue CAGR 3Y ≥ threshold
        rev_cagr = profile.get("revenue_cagr_3y_pct")
        threshold = g["min_revenue_cagr_3y_pct"]
        passed = rev_cagr is not None and rev_cagr >= threshold
        results["revenue_cagr_3y"] = {"passed": passed, "value": rev_cagr, "threshold": f"≥ {threshold}%"}
        if not passed:
            rejections.append(f"Revenue CAGR 3Y {rev_cagr}% < {threshold}%")

        # 5. PEG in range
        peg = profile.get("peg_ratio")
        peg_lo, peg_hi = g["peg_range"]
        passed = peg is not None and peg_lo <= peg <= peg_hi
        results["peg_ratio"] = {"passed": passed, "value": peg, "threshold": f"{peg_lo}–{peg_hi}"}
        if not passed:
            rejections.append(f"PEG {peg} outside [{peg_lo}, {peg_hi}]")

        # 6. Debt/Equity ≤ threshold (sector-aware)
        de = profile.get("debt_to_equity")
        if is_bfsi:
            de_threshold = g["max_debt_equity"]
            # BFSI: D/E is naturally high; if unavailable, pass with flag
            if de is not None:
                passed = de <= de_threshold
            else:
                passed = True  # Stage 2 will flag it
        else:
            de_threshold = g.get("max_debt_equity_non_bfsi", g["max_debt_equity"])
            if de is not None:
                passed = de <= de_threshold
            else:
                passed = True  # Pass if unavailable, flag in Stage 2
        results["debt_to_equity"] = {
            "passed": passed,
            "value": de,
            "threshold": f"≤ {de_threshold} ({'BFSI' if is_bfsi else 'non-BFSI'})",
        }
        if not passed:
            rejections.append(f"D/E {de} > {de_threshold} ({'BFSI' if is_bfsi else 'non-BFSI'})")

        # 7. Promoter Holding ≥ threshold
        promo = profile.get("promoter_holding_pct")
        threshold = g["min_promoter_holding_pct"]
        if promo is not None:
            passed = promo >= threshold
        else:
            # If promoter data unavailable, pass with a flag (Stage 2 will flag it)
            passed = True
        results["promoter_holding"] = {"passed": passed, "value": promo, "threshold": f"≥ {threshold}%"}
        if not passed:
            rejections.append(f"Promoter holding {promo}% < {threshold}%")

        # 8. Positive Free Cash Flow (BFSI: waived — banks don't report FCF meaningfully)
        fcf_positive = profile.get("fcf_positive")
        if is_bfsi:
            results["fcf_positive"] = {"passed": True, "value": fcf_positive, "threshold": "waived (BFSI)"}
        elif g["require_positive_fcf"]:
            # For non-BFSI: if FCF data unavailable, pass with flag rather than hard reject
            if fcf_positive is True:
                passed = True
            elif fcf_positive is False:
                passed = False
            else:
                passed = True  # Data unavailable — Stage 2 flags
            results["fcf_positive"] = {"passed": passed, "value": fcf_positive, "threshold": "> 0"}
            if not passed:
                fcf_val = profile.get("free_cash_flow_cr")
                rejections.append(f"FCF negative ({fcf_val} Cr)")
        else:
            results["fcf_positive"] = {"passed": True, "value": fcf_positive, "threshold": "disabled"}

        # 9. ROE ≥ threshold (already checked via ROCE proxy for BFSI, still apply separately)
        roe = profile.get("roe_pct")
        threshold = g["min_roe_pct"]
        if roe is not None:
            passed = roe >= threshold
        else:
            passed = True  # Pass if unavailable, flag in Stage 2
        results["roe"] = {"passed": passed, "value": roe, "threshold": f"≥ {threshold}%"}
        if not passed:
            rejections.append(f"ROE {roe}% < {threshold}%")

        all_passed = all(r["passed"] for r in results.values())

        return {
            "passed": all_passed,
            "criteria_results": results,
            "rejection_reasons": rejections,
            "is_bfsi": is_bfsi,
        }

    # ======================================================================
    # Stage 2: Qualitative Flag Bucket
    # ======================================================================

    def qualitative_flags(self, profile: dict) -> list:
        """
        Returns list of flag dicts. Does NOT eliminate — marks for manual review.

        Each flag: {"flag": str, "severity": "HIGH"|"MEDIUM", "reason": str}
        """
        flags = []

        # 1. Promoter Data Missing
        if profile.get("promoter_holding_pct") is None:
            flags.append({
                "flag": "PROMOTER_DATA_MISSING",
                "severity": "HIGH",
                "reason": "Could not fetch promoter shareholding data — requires manual verification.",
            })

        # 2. High Promoter Pledge
        pledge = profile.get("promoter_pledge_pct")
        if pledge is not None and pledge > 10:
            flags.append({
                "flag": "PROMOTER_PLEDGE_HIGH",
                "severity": "HIGH",
                "reason": f"Promoter pledge at {pledge}% (threshold: 10%). Indicates potential financial stress.",
            })

        # 3. High Debt in Non-BFSI
        de = profile.get("debt_to_equity")
        is_bfsi = _is_bfsi(profile.get("sector"), profile.get("industry"))
        if de is not None and de > 1.0 and not is_bfsi:
            flags.append({
                "flag": "HIGH_DEBT_SECTOR",
                "severity": "MEDIUM",
                "reason": f"D/E ratio {de} > 1.0 in non-BFSI sector ({profile.get('sector', 'Unknown')}).",
            })

        # 4. Negative FCF despite profitability
        fcf = profile.get("free_cash_flow_cr")
        pm = profile.get("profit_margin_pct")
        if fcf is not None and fcf < 0 and pm is not None and pm > 0:
            flags.append({
                "flag": "NEGATIVE_FCF_TREND",
                "severity": "MEDIUM",
                "reason": f"FCF is {fcf} Cr despite positive margins ({pm}%). Cash conversion issue.",
            })

        # 5. High PE vs Growth mismatch
        pe = profile.get("trailing_pe")
        eg = profile.get("earnings_growth_ttm_pct")
        if pe is not None and pe > 40 and eg is not None and eg < 20:
            flags.append({
                "flag": "HIGH_PE_VS_GROWTH",
                "severity": "MEDIUM",
                "reason": f"PE {pe:.1f} with earnings growth only {eg:.1f}%. Overvaluation risk.",
            })

        # 6. Thin Operating Margins
        om = profile.get("operating_margin_pct")
        if om is not None and om < 8:
            flags.append({
                "flag": "THIN_MARGINS",
                "severity": "MEDIUM",
                "reason": f"Operating margin {om:.1f}% < 8%. Low pricing power or competitive squeeze.",
            })

        # 7. Near 52-week high (not a rejection, just awareness)
        price = profile.get("current_price")
        high_52 = profile.get("fifty_two_week_high")
        if price is not None and high_52 is not None and high_52 > 0:
            distance_pct = ((high_52 - price) / high_52) * 100
            if distance_pct < 5:
                flags.append({
                    "flag": "NEAR_52W_HIGH",
                    "severity": "MEDIUM",
                    "reason": f"Trading within {distance_pct:.1f}% of 52-week high ({high_52}). Timing risk.",
                })

        return flags

    # ======================================================================
    # Stage 3: Pure Fundamental Rank (0–100)
    # ======================================================================

    def fundamental_rank(self, profile: dict) -> dict:
        """
        Score 0–100 based purely on fundamentals.
        NO momentum, NO relative strength, NO news sentiment.

        Returns: {"total_score": float, "components": {name: {"score": float, "weight": float, "raw": ...}}}
        """
        components = {}
        w = self.weights

        # ── 1. ROCE Score (0–100) ──
        roce = profile.get("roce_pct")
        roce_score = self._linear_scale(roce, floor=15, ceiling=35)
        components["roce"] = {"score": roce_score, "weight": w.get("roce", 0.25), "raw": roce}

        # ── 2. Growth Score (0–100) ──
        eps_cagr = profile.get("eps_cagr_3y_pct")
        rev_cagr = profile.get("revenue_cagr_3y_pct")
        eps_score = self._linear_scale(eps_cagr, floor=10, ceiling=35)
        rev_score = self._linear_scale(rev_cagr, floor=8, ceiling=30)
        growth_score = (eps_score + rev_score) / 2.0
        components["growth"] = {
            "score": growth_score,
            "weight": w.get("growth", 0.25),
            "raw": {"eps_cagr": eps_cagr, "rev_cagr": rev_cagr},
        }

        # ── 3. Valuation Score (0–100) — lower PEG is better ──
        peg = profile.get("peg_ratio")
        if peg is not None and peg > 0:
            # PEG 0.5 = 100, PEG 2.5 = 0
            val_score = max(0, min(100, (2.5 - peg) / (2.5 - 0.5) * 100))
        else:
            val_score = 0
        # Bonus: Forward PE discount (if forward < trailing, earnings expected to grow)
        t_pe = profile.get("trailing_pe")
        f_pe = profile.get("forward_pe")
        if t_pe and f_pe and t_pe > 0 and f_pe > 0 and f_pe < t_pe:
            discount_pct = ((t_pe - f_pe) / t_pe) * 100
            val_score = min(100, val_score + discount_pct * 0.5)  # Up to +10 bonus
        components["valuation"] = {"score": val_score, "weight": w.get("valuation", 0.20), "raw": peg}

        # ── 4. Quality Score (0–100) ──
        de = profile.get("debt_to_equity")
        de_score = self._inverse_scale(de, best=0, worst=2.0) if de is not None else 30

        ic = profile.get("interest_coverage")
        ic_score = self._linear_scale(ic, floor=2, ceiling=15) if ic is not None else 30

        fcf_cr = profile.get("free_cash_flow_cr")
        fcf_score = 60 if (fcf_cr is not None and fcf_cr > 0) else 10

        cr = profile.get("current_ratio")
        cr_score = self._linear_scale(cr, floor=1.0, ceiling=3.0) if cr is not None else 30

        quality_score = (de_score * 0.30 + ic_score * 0.30 + fcf_score * 0.25 + cr_score * 0.15)
        components["quality"] = {
            "score": quality_score,
            "weight": w.get("quality", 0.15),
            "raw": {"de": de, "ic": ic, "fcf_cr": fcf_cr},
        }

        # ── 5. Promoter Confidence (0–100) ──
        promo = profile.get("promoter_holding_pct")
        pledge = profile.get("promoter_pledge_pct") or 0

        if promo is not None:
            promo_score = self._linear_scale(promo, floor=30, ceiling=75)
            # Penalty for pledge
            pledge_penalty = min(50, pledge * 3)  # 10% pledge = 30 point penalty
            promo_score = max(0, promo_score - pledge_penalty)
        else:
            promo_score = 30  # Neutral if data unavailable
        components["promoter"] = {
            "score": promo_score,
            "weight": w.get("promoter", 0.15),
            "raw": {"holding": promo, "pledge": pledge},
        }

        # ── Total ──
        total = sum(c["score"] * c["weight"] for c in components.values())
        total = round(total, 2)

        return {"total_score": total, "components": components}

    # ======================================================================
    # Full Pipeline
    # ======================================================================

    def run(self, profiles: list) -> dict:
        """
        Run the complete 3-stage pipeline on a list of fundamental profiles.

        Returns:
            {
                "total_screened": int,
                "passed_gate": int,
                "results": [sorted list of result dicts],
                "rejected": [list of rejected stocks with reasons],
                "run_time": str (ISO timestamp),
            }
        """
        from datetime import datetime

        results = []
        rejected = []

        for profile in profiles:
            sym = profile.get("symbol", "UNKNOWN")

            # Skip profiles with fetch errors
            if profile.get("error"):
                rejected.append({
                    "symbol": sym,
                    "reason": f"Data fetch error: {profile['error']}",
                    "gate_result": None,
                })
                continue

            # Stage 1
            gate_result = self.hard_gate(profile)

            # Stage 2 (run on ALL stocks, not just passed)
            flags = self.qualitative_flags(profile)

            if not gate_result["passed"]:
                rejected.append({
                    "symbol": sym,
                    "reason": "; ".join(gate_result["rejection_reasons"]),
                    "gate_result": gate_result,
                    "flags": flags,
                })
                continue

            # Stage 3 (only for gate-passed stocks)
            rank = self.fundamental_rank(profile)

            results.append({
                "symbol": sym,
                "company_name": profile.get("company_name"),
                "sector": profile.get("sector"),
                "score": rank["total_score"],
                "rank_components": rank["components"],
                "gate_result": gate_result,
                "flags": flags,
                "flag_count": len(flags),
                "high_flags": sum(1 for f in flags if f["severity"] == "HIGH"),
                # Key metrics for display
                "market_cap_cr": profile.get("market_cap_cr"),
                "roce_pct": profile.get("roce_pct"),
                "roe_pct": profile.get("roe_pct"),
                "peg_ratio": profile.get("peg_ratio"),
                "debt_to_equity": profile.get("debt_to_equity"),
                "eps_cagr_3y_pct": profile.get("eps_cagr_3y_pct"),
                "revenue_cagr_3y_pct": profile.get("revenue_cagr_3y_pct"),
                "promoter_holding_pct": profile.get("promoter_holding_pct"),
                "free_cash_flow_cr": profile.get("free_cash_flow_cr"),
                "current_price": profile.get("current_price"),
                "trailing_pe": profile.get("trailing_pe"),
            })

        # Sort by score (highest first)
        results.sort(key=lambda x: x["score"], reverse=True)

        # Assign rank numbers
        for i, r in enumerate(results, 1):
            r["rank"] = i

        return {
            "total_screened": len(profiles),
            "passed_gate": len(results),
            "rejected_count": len(rejected),
            "results": results,
            "rejected": rejected,
            "run_time": datetime.now().isoformat(),
            "mode": self.mode,
        }

    # ======================================================================
    # Scoring Helpers
    # ======================================================================

    @staticmethod
    def _linear_scale(value, floor: float, ceiling: float) -> float:
        """Scale *value* linearly: floor→0, ceiling→100. Clamp to [0, 100]."""
        if value is None:
            return 0.0
        if ceiling == floor:
            return 50.0
        score = ((value - floor) / (ceiling - floor)) * 100.0
        return max(0.0, min(100.0, score))

    @staticmethod
    def _inverse_scale(value, best: float, worst: float) -> float:
        """Inverse scale: best→100, worst→0. Lower is better."""
        if value is None:
            return 0.0
        if worst == best:
            return 50.0
        score = ((worst - value) / (worst - best)) * 100.0
        return max(0.0, min(100.0, score))
