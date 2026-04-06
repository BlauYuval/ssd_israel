"""
Dividend Safety Score calculator.

Produces a score from 0–100 for each stock based on five components,
matching the weights defined in the project plan.

Component          Weight   Logic
-----------------  -------  --------------------------------------------------
Payout ratio        25%     Lower is safer. >100% EPS payout = critical risk
FCF coverage        25%     FCF / annual dividends paid. >1.5x = max score
Debt / Equity       20%     Lower is safer, sector-adjusted
Dividend history    20%     Years without a cut. Each cut = penalty
Dividend growth     10%     Positive multi-year CAGR = bonus

Final score is clipped to [0, 100].
Each component score is also returned so the frontend can display it.
"""
from dataclasses import dataclass, field


@dataclass
class SafetyScoreInput:
    # Payout ratio component
    payout_ratio: float | None = None          # dividends / net_income (e.g. 0.45 = 45%)

    # FCF coverage component
    annual_dividends_paid: float | None = None  # total cash paid (absolute value)
    free_cash_flow: float | None = None         # FCF for same period

    # Debt/Equity component
    debt_to_equity: float | None = None        # total_debt / equity
    sector: str | None = None                  # used for D/E sector adjustment

    # Dividend history component (computed from dividend records)
    years_of_consecutive_dividends: int = 0
    dividend_cuts_last_10y: int = 0

    # Dividend growth component
    dividend_cagr_3y: float | None = None      # e.g. 0.05 = 5% annual growth
    dividend_cagr_5y: float | None = None


@dataclass
class SafetyScoreResult:
    total: float                               # 0–100

    payout_score: float                        # 0–25
    fcf_score: float                           # 0–25
    debt_score: float                          # 0–20
    history_score: float                       # 0–20
    growth_score: float                        # 0–10

    payout_label: str = ""
    fcf_label: str = ""
    debt_label: str = ""
    history_label: str = ""
    growth_label: str = ""


# Sectors with structurally higher leverage — use relaxed D/E thresholds
_HIGH_LEVERAGE_SECTORS = {"real_estate", "banking", "insurance", "utilities", "realestate"}


def _score_payout(payout_ratio: float | None) -> tuple[float, str]:
    """
    25 points.
    < 40%  → 25  (very safe)
    40–60% → 20
    60–75% → 14
    75–90% → 7
    90–100%→ 3
    > 100% → 0  (paying more than earnings)
    None   → 10 (penalised but not zero — missing data)
    """
    if payout_ratio is None:
        return 10.0, "No data"
    p = payout_ratio * 100  # convert to percentage
    if p > 100:
        return 0.0, f"Critical ({p:.0f}% payout)"
    if p > 90:
        return 3.0, f"Dangerous ({p:.0f}%)"
    if p > 75:
        return 7.0, f"High ({p:.0f}%)"
    if p > 60:
        return 14.0, f"Moderate ({p:.0f}%)"
    if p > 40:
        return 20.0, f"Healthy ({p:.0f}%)"
    return 25.0, f"Very safe ({p:.0f}%)"


def _score_fcf_coverage(
    fcf: float | None,
    dividends_paid: float | None,
) -> tuple[float, str]:
    """
    25 points.
    FCF / dividends_paid:
    ≥ 2.0x  → 25
    1.5–2.0 → 20
    1.0–1.5 → 14
    0.5–1.0 → 7
    < 0.5   → 0
    Either None → 10
    """
    if fcf is None or not dividends_paid:
        return 10.0, "No data"
    try:
        coverage = fcf / abs(dividends_paid)
    except ZeroDivisionError:
        return 10.0, "No data"

    if coverage >= 2.0:
        return 25.0, f"Excellent ({coverage:.1f}x)"
    if coverage >= 1.5:
        return 20.0, f"Strong ({coverage:.1f}x)"
    if coverage >= 1.0:
        return 14.0, f"Adequate ({coverage:.1f}x)"
    if coverage >= 0.5:
        return 7.0, f"Weak ({coverage:.1f}x)"
    return 0.0, f"Insufficient ({coverage:.1f}x)"


def _score_debt(
    debt_to_equity: float | None,
    sector: str | None,
) -> tuple[float, str]:
    """
    20 points.
    For high-leverage sectors (banks, real estate), thresholds are 2× higher.
    D/E:
    < 0.3   → 20
    0.3–0.6 → 16
    0.6–1.0 → 12
    1.0–1.5 → 6
    > 1.5   → 2
    None    → 8
    """
    if debt_to_equity is None:
        return 8.0, "No data"

    multiplier = 2.0 if (sector or "").lower().replace(" ", "_") in _HIGH_LEVERAGE_SECTORS else 1.0
    d = debt_to_equity / multiplier

    if d < 0.3:
        return 20.0, f"Low ({debt_to_equity:.2f})"
    if d < 0.6:
        return 16.0, f"Moderate ({debt_to_equity:.2f})"
    if d < 1.0:
        return 12.0, f"Elevated ({debt_to_equity:.2f})"
    if d < 1.5:
        return 6.0, f"High ({debt_to_equity:.2f})"
    return 2.0, f"Very high ({debt_to_equity:.2f})"


def _score_history(
    years_consecutive: int,
    cuts_last_10y: int,
) -> tuple[float, str]:
    """
    20 points.
    Years of consecutive dividends (no cuts):
    ≥ 10 → 20
    7–9  → 17
    5–6  → 14
    3–4  → 10
    1–2  →  6
    0    →  0
    Each cut subtracts 4 points (floor 0).
    """
    if years_consecutive >= 10:
        base = 20.0
    elif years_consecutive >= 7:
        base = 17.0
    elif years_consecutive >= 5:
        base = 14.0
    elif years_consecutive >= 3:
        base = 10.0
    elif years_consecutive >= 1:
        base = 6.0
    else:
        base = 0.0

    penalty = cuts_last_10y * 4.0
    score = max(0.0, base - penalty)
    label = f"{years_consecutive}yr streak"
    if cuts_last_10y:
        label += f", {cuts_last_10y} cut(s)"
    return score, label


def _score_growth(
    cagr_3y: float | None,
    cagr_5y: float | None,
) -> tuple[float, str]:
    """
    10 points.
    Prefer 5Y CAGR; fall back to 3Y.
    ≥ 10%  → 10
    5–10%  →  8
    0–5%   →  5
    Negative → 0
    No data  → 4
    """
    cagr = cagr_5y if cagr_5y is not None else cagr_3y
    if cagr is None:
        return 4.0, "No data"

    pct = cagr * 100
    if pct >= 10:
        return 10.0, f"Strong ({pct:.1f}%/yr)"
    if pct >= 5:
        return 8.0, f"Good ({pct:.1f}%/yr)"
    if pct >= 0:
        return 5.0, f"Modest ({pct:.1f}%/yr)"
    return 0.0, f"Declining ({pct:.1f}%/yr)"


def calculate(inp: SafetyScoreInput) -> SafetyScoreResult:
    """Compute the full Dividend Safety Score from the given inputs."""
    payout_score, payout_label = _score_payout(inp.payout_ratio)
    fcf_score, fcf_label = _score_fcf_coverage(inp.free_cash_flow, inp.annual_dividends_paid)
    debt_score, debt_label = _score_debt(inp.debt_to_equity, inp.sector)
    history_score, history_label = _score_history(inp.years_of_consecutive_dividends, inp.dividend_cuts_last_10y)
    growth_score, growth_label = _score_growth(inp.dividend_cagr_3y, inp.dividend_cagr_5y)

    total = round(payout_score + fcf_score + debt_score + history_score + growth_score, 1)
    total = max(0.0, min(100.0, total))

    return SafetyScoreResult(
        total=total,
        payout_score=payout_score,
        fcf_score=fcf_score,
        debt_score=debt_score,
        history_score=history_score,
        growth_score=growth_score,
        payout_label=payout_label,
        fcf_label=fcf_label,
        debt_label=debt_label,
        history_label=history_label,
        growth_label=growth_label,
    )
