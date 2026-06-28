"""
The AI-specific risk-tiering engine.

This is intentionally transparent: a reviewer must be able to explain *why* a
model landed in its tier. The tier is a weighted average of per-dimension risk
ratings (each 1=Low, 2=Medium, 3=High), with a small number of explicitly-stated
escalation rules layered on top. Nothing is hidden in a black box — every
contribution and every escalation is returned for display.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

# ── Dimensions ────────────────────────────────────────────────────────────────
# Each dimension is scored 1 (Low risk) / 2 (Medium) / 3 (High risk).
# `applies` is "all" (every model) or "llm" (generative / LLM models only).
# The low/med/high strings describe the *state of the world* at that risk level,
# so the rating reads naturally to a reviewer.
DIMENSIONS: list[dict[str, Any]] = [
    {
        "key": "materiality",
        "label": "Materiality & business impact",
        "applies": "all",
        "weight": 1.5,
        "levels": {
            1: "Low — limited financial or customer impact",
            2: "Medium — moderate impact, limited regulatory relevance",
            3: "High — material to capital / P&L / customers; regulatory relevance",
        },
        "note": "The traditional SR 11-7 anchor: how much rides on the model.",
    },
    {
        "key": "explainability",
        "label": "Explainability / transparency",
        "applies": "all",
        "weight": 1.0,
        "levels": {
            1: "Low risk — transparent & interpretable (scorecard / regression)",
            2: "Medium — partially interpretable (e.g. GBM with SHAP)",
            3: "High risk — black-box / opaque",
        },
        "note": "Can a human understand and challenge why it produced an output?",
    },
    {
        "key": "autonomy",
        "label": "Autonomy of action",
        "applies": "all",
        "weight": 1.25,
        "levels": {
            1: "Low — decision support only, human in the loop",
            2: "Medium — human on the loop, with override",
            3: "High — fully automated action with no human review",
        },
        "note": "How much the model acts on its own vs. advising a human.",
    },
    {
        "key": "output_variability",
        "label": "Output variability / determinism",
        "applies": "all",
        "weight": 0.75,
        "levels": {
            1: "Low — deterministic, stable outputs",
            2: "Medium — some variability run-to-run",
            3: "High — non-deterministic / generative outputs",
        },
        "note": "Same input, same output? Or does it vary?",
    },
    {
        "key": "drift",
        "label": "Susceptibility to drift",
        "applies": "all",
        "weight": 1.0,
        "levels": {
            1: "Low — stable population & relationships",
            2: "Medium — some sensitivity to population shift",
            3: "High — fast-moving data, high drift risk",
        },
        "note": "How quickly does the world it models change underneath it?",
    },
    {
        "key": "data_quality",
        "label": "Data quality & provenance",
        "applies": "all",
        "weight": 1.0,
        "levels": {
            1: "Low risk — high quality, well-documented provenance",
            2: "Medium — some gaps or limited lineage",
            3: "High risk — poor quality / unclear provenance / external data",
        },
        "note": "Do we trust and can we trace the data feeding it?",
    },
    {
        "key": "fairness_bias",
        "label": "Fairness & bias exposure",
        "applies": "all",
        "weight": 1.0,
        "levels": {
            1: "Low — no decisions affecting protected groups",
            2: "Medium — some exposure, mitigated",
            3: "High — direct decisions affecting protected groups",
        },
        "note": "Could it produce unfair outcomes across protected groups?",
    },
    {
        "key": "hallucination",
        "label": "Hallucination exposure (GenAI)",
        "applies": "llm",
        "weight": 1.25,
        "levels": {
            1: "Low — tightly grounded / retrieval-constrained",
            2: "Medium — some generative freedom",
            3: "High — open-ended generation, fabrication risk",
        },
        "note": "How prone is it to confidently making things up?",
    },
    {
        "key": "prompt_injection",
        "label": "Prompt-injection / manipulation exposure (GenAI)",
        "applies": "llm",
        "weight": 1.0,
        "levels": {
            1: "Low — no untrusted input, no tool use",
            2: "Medium — some external / user-supplied input",
            3: "High — ingests untrusted content, agentic / tool use",
        },
        "note": "How exposed is it to people manipulating its instructions?",
    },
]

DIMENSION_BY_KEY = {d["key"]: d for d in DIMENSIONS}

TIER_FREQUENCY_MONTHS = {1: 12, 2: 24, 3: 36}
TIER_FREQUENCY_LABEL = {
    1: "Annual (12 months)",
    2: "Every 2 years (24 months)",
    3: "Every 3 years (36 months)",
}
TIER_LABEL = {
    1: "Tier 1 — High risk",
    2: "Tier 2 — Medium risk",
    3: "Tier 3 — Lower risk",
}

# Weighted-average cut-offs (score runs 1.0–3.0).
_TIER1_CUTOFF = 2.33
_TIER2_CUTOFF = 1.75

RATING_WORD = {1: "Low", 2: "Medium", 3: "High"}


def applicable_dimensions(model: dict[str, Any]) -> list[dict[str, Any]]:
    is_llm = model.get("family", "").startswith("Generative")
    return [d for d in DIMENSIONS if d["applies"] == "all" or (is_llm and d["applies"] == "llm")]


def compute_tier(model: dict[str, Any]) -> dict[str, Any]:
    """Return the full, explainable tiering breakdown for a model."""
    ratings = model.get("ratings", {})
    dims = applicable_dimensions(model)

    contributions = []
    weighted_sum = 0.0
    weight_total = 0.0
    for d in dims:
        rating = int(ratings.get(d["key"], 1))
        rating = min(3, max(1, rating))
        w = d["weight"]
        weighted_sum += rating * w
        weight_total += w
        contributions.append(
            {
                "key": d["key"],
                "label": d["label"],
                "rating": rating,
                "rating_word": RATING_WORD[rating],
                "weight": w,
                "weighted": round(rating * w, 2),
                "level_text": d["levels"][rating],
                "note": d["note"],
            }
        )

    score = weighted_sum / weight_total if weight_total else 1.0

    # Base tier from the weighted score.
    if score >= _TIER1_CUTOFF:
        base_tier = 1
    elif score >= _TIER2_CUTOFF:
        base_tier = 2
    else:
        base_tier = 3

    tier = base_tier
    escalations: list[str] = []

    # Escalation rule 1 — materiality floor: a highly material model is never
    # allowed to sit in the lowest tier purely on a low average.
    if int(ratings.get("materiality", 1)) == 3 and tier == 3:
        tier = 2
        escalations.append(
            "Materiality is High, so the model cannot be Tier 3 — escalated to Tier 2."
        )

    # Escalation rule 2 — autonomous + material: full automation acting on a
    # material decision warrants the highest scrutiny.
    if (
        int(ratings.get("autonomy", 1)) == 3
        and int(ratings.get("materiality", 1)) >= 2
        and tier > 1
    ):
        tier = 1
        escalations.append(
            "Fully automated action on a material decision — escalated to Tier 1."
        )

    # Escalation rule 3 — GenAI safety floor: high hallucination AND high
    # prompt-injection exposure on a customer/regulatory-facing model.
    if (
        int(ratings.get("hallucination", 1)) == 3
        and int(ratings.get("prompt_injection", 1)) == 3
        and tier > 1
    ):
        tier = 1
        escalations.append(
            "High hallucination AND high prompt-injection exposure — escalated to Tier 1."
        )

    return {
        "contributions": contributions,
        "score": round(score, 2),
        "base_tier": base_tier,
        "tier": tier,
        "tier_label": TIER_LABEL[tier],
        "escalations": escalations,
        "frequency_months": TIER_FREQUENCY_MONTHS[tier],
        "frequency_label": TIER_FREQUENCY_LABEL[tier],
        "is_llm": model.get("family", "").startswith("Generative"),
    }


# ── Revalidation scheduling ────────────────────────────────────────────────--
def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    # clamp day to month length
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def revalidation_status(model: dict[str, Any], tier_info: dict[str, Any] | None = None) -> dict[str, Any]:
    tier_info = tier_info or compute_tier(model)
    last = _parse_date(model.get("last_validation_date"))
    months = tier_info["frequency_months"]
    today = date.today()

    if last is None:
        return {
            "next_due": None,
            "next_due_str": "Never validated",
            "days_remaining": None,
            "state": "overdue",
            "state_label": "Never validated",
        }

    next_due = _add_months(last, months)
    days_remaining = (next_due - today).days

    if days_remaining < 0:
        state, label = "overdue", f"Overdue by {abs(days_remaining)} days"
    elif days_remaining <= 90:
        state, label = "due_soon", f"Due in {days_remaining} days"
    else:
        state, label = "ok", f"Due in {days_remaining} days"

    return {
        "next_due": next_due,
        "next_due_str": next_due.strftime("%d %b %Y"),
        "days_remaining": days_remaining,
        "state": state,
        "state_label": label,
    }


def enrich(model: dict[str, Any]) -> dict[str, Any]:
    """Attach computed tier + revalidation info to a model (non-destructive copy)."""
    out = dict(model)
    tier_info = compute_tier(model)
    out["_tier"] = tier_info
    out["_reval"] = revalidation_status(model, tier_info)
    return out
