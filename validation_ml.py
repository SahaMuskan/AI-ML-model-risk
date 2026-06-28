"""
Track A — traditional ML validation battery (illustrative).

These results are generated deterministically from the model id (so a given
model always shows the same numbers and charts across sessions) and are NOT
the output of a real fitted model. They demonstrate the *shape* of a classic
validation: discrimination, calibration, stability/drift, explainability,
fairness, and robustness — each with sensible thresholds and pass/fail flags.

The thresholds below are conventional starting points, not house policy.
"""

from __future__ import annotations

import math
import random
from typing import Any

import charts

# ── Conventional thresholds (illustrative) ──────────────────────────────────--
THRESHOLDS = {
    "auc": 0.70,          # >= pass
    "gini": 0.40,         # >= pass
    "ks": 0.30,           # >= pass
    "brier": 0.20,        # <= pass
    "psi": 0.25,          # > breach (0.10–0.25 = watch)
    "psi_watch": 0.10,
    "four_fifths": 0.80,  # disparate-impact ratio >= pass
    "robust_drop": 0.10,  # max acceptable relative AUC drop under stress
}


def _rng(model_id: str) -> random.Random:
    return random.Random(f"trackA::{model_id}")


def _grade(passed: bool, watch: bool = False) -> str:
    if passed and not watch:
        return "PASS"
    if watch:
        return "WATCH"
    return "FAIL"


def generate(model: dict[str, Any]) -> dict[str, Any]:
    r = _rng(model["id"])

    # Tie the model's apparent "quality" loosely to its risk ratings so the
    # numbers feel coherent (a higher-drift model shows more PSI movement, etc.)
    ratings = model.get("ratings", {})
    drift_rating = ratings.get("drift", 2)

    # ── Discrimination ─────────────────────────────────────────────────────--
    auc = round(r.uniform(0.71, 0.86) if r.random() > 0.15 else r.uniform(0.63, 0.70), 3)
    gini = round(2 * auc - 1, 3)
    ks = round(r.uniform(0.30, 0.52) if auc >= 0.70 else r.uniform(0.22, 0.31), 3)

    # ROC curve points (concave, passing through (0,0)-(1,1))
    roc_points = [(0.0, 0.0)]
    for i in range(1, 10):
        x = i / 10
        y = min(1.0, x ** (1 - (auc - 0.5)))  # bows toward top-left as auc rises
        roc_points.append((x, round(y, 3)))
    roc_points.append((1.0, 1.0))

    # Confusion matrix at a chosen cut-off
    n = 10000
    prevalence = r.uniform(0.06, 0.18)
    pos = int(n * prevalence)
    neg = n - pos
    tpr = min(0.95, max(0.45, auc + r.uniform(-0.05, 0.08)))
    fpr = max(0.04, min(0.4, (1 - auc) + r.uniform(-0.04, 0.06)))
    tp = int(pos * tpr)
    fn = pos - tp
    fp = int(neg * fpr)
    tn = neg - fp

    # ── Calibration ────────────────────────────────────────────────────────--
    brier = round(r.uniform(0.08, 0.18) if auc >= 0.70 else r.uniform(0.18, 0.26), 3)
    rel_points = [(0.0, 0.0)]
    for i in range(1, 10):
        x = i / 10
        # slight, consistent miscalibration
        bias = (r.random() - 0.5) * 0.06
        y = min(1.0, max(0.0, x + bias))
        rel_points.append((x, round(y, 3)))
    rel_points.append((1.0, 1.0))

    # ── Stability / drift (PSI over recent periods) ──────────────────────────--
    periods = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]
    base = 0.02 + 0.03 * (drift_rating - 1)
    psi_series = []
    psi_val = base
    for _ in periods:
        psi_val = max(0.0, psi_val + r.uniform(-0.02, 0.05 + 0.03 * (drift_rating - 1)))
        psi_series.append(round(psi_val, 3))
    psi_latest = psi_series[-1]

    # ── Explainability (feature importance) ──────────────────────────────────--
    feature_pool = [
        "Bureau score", "Utilisation", "Months on book", "Income",
        "Prior delinquencies", "DTI ratio", "Recent enquiries", "Balance trend",
    ]
    weights = sorted((r.uniform(0.05, 1.0) for _ in feature_pool), reverse=True)
    total = sum(weights)
    features = [
        {"label": f, "value": round(w / total, 3)}
        for f, w in zip(feature_pool, weights)
    ]

    # ── Fairness (four-fifths / disparate impact) ────────────────────────────--
    groups = ["Group A (ref)", "Group B", "Group C", "Group D"]
    ref_rate = r.uniform(0.30, 0.45)
    fairness = []
    min_ratio = 1.0
    for i, g in enumerate(groups):
        if i == 0:
            rate = ref_rate
            ratio = 1.0
        else:
            rate = ref_rate * r.uniform(0.74, 1.05)
            ratio = round(rate / ref_rate, 3)
            min_ratio = min(min_ratio, ratio)
        fairness.append({
            "group": g,
            "selection_rate": round(rate, 3),
            "ratio": round(ratio, 3),
            "pass": ratio >= THRESHOLDS["four_fifths"],
        })

    # ── Robustness / sensitivity (AUC under input noise) ─────────────────────--
    noise_levels = ["0%", "5%", "10%", "20%", "30%"]
    robust = []
    auc_under = auc
    for lvl in noise_levels:
        robust.append({"label": lvl, "value": round(auc_under, 3)})
        auc_under = max(0.5, auc_under - r.uniform(0.005, 0.03))
    rel_drop = (auc - robust[-1]["value"]) / auc

    # ── Pass/fail summary ────────────────────────────────────────────────────--
    checks = [
        {"name": "Discrimination — AUC", "value": f"{auc:.3f}", "threshold": f"≥ {THRESHOLDS['auc']:.2f}",
         "grade": _grade(auc >= THRESHOLDS["auc"])},
        {"name": "Discrimination — Gini", "value": f"{gini:.3f}", "threshold": f"≥ {THRESHOLDS['gini']:.2f}",
         "grade": _grade(gini >= THRESHOLDS["gini"])},
        {"name": "Discrimination — KS", "value": f"{ks:.3f}", "threshold": f"≥ {THRESHOLDS['ks']:.2f}",
         "grade": _grade(ks >= THRESHOLDS["ks"])},
        {"name": "Calibration — Brier score", "value": f"{brier:.3f}", "threshold": f"≤ {THRESHOLDS['brier']:.2f}",
         "grade": _grade(brier <= THRESHOLDS["brier"])},
        {"name": "Stability — latest PSI", "value": f"{psi_latest:.3f}",
         "threshold": f"≤ {THRESHOLDS['psi']:.2f}",
         "grade": _grade(psi_latest <= THRESHOLDS["psi"], watch=THRESHOLDS["psi_watch"] < psi_latest <= THRESHOLDS["psi"])},
        {"name": "Fairness — min four-fifths ratio", "value": f"{min_ratio:.3f}",
         "threshold": f"≥ {THRESHOLDS['four_fifths']:.2f}",
         "grade": _grade(min_ratio >= THRESHOLDS["four_fifths"],
                         watch=THRESHOLDS["four_fifths"] <= min_ratio < THRESHOLDS["four_fifths"] + 0.05)},
        {"name": "Robustness — AUC drop under 30% noise", "value": f"{rel_drop * 100:.1f}%",
         "threshold": f"≤ {THRESHOLDS['robust_drop'] * 100:.0f}%",
         "grade": _grade(rel_drop <= THRESHOLDS["robust_drop"])},
    ]
    n_fail = sum(1 for c in checks if c["grade"] == "FAIL")
    n_watch = sum(1 for c in checks if c["grade"] == "WATCH")
    overall = "FAIL" if n_fail else ("WATCH" if n_watch else "PASS")

    # ── Pre-render charts (inline SVG) ───────────────────────────────────────--
    roc_svg = charts.line_chart(
        [{"points": roc_points, "color": charts.C_PRIMARY, "label": "ROC"}],
        x_label="False positive rate", y_label="True positive rate",
        x_ticks=["0", "0.25", "0.5", "0.75", "1"], diagonal=True,
    )
    rel_svg = charts.line_chart(
        [{"points": rel_points, "color": charts.C_PRIMARY, "label": "Reliability"}],
        x_label="Predicted probability", y_label="Observed frequency",
        x_ticks=["0", "0.25", "0.5", "0.75", "1"], diagonal=True,
    )
    psi_points = [(i / (len(periods) - 1), v) for i, v in enumerate(psi_series)]
    psi_svg = charts.line_chart(
        [{"points": psi_points, "color": charts.C_WARN, "label": "PSI"}],
        x_label="Period", y_label="PSI", x_ticks=periods, y_min=0.0, y_max=0.5,
    )
    feat_svg = charts.bar_chart(features, value_fmt="{:.2f}")
    fairness_items = [
        {"label": f["group"], "value": f["ratio"],
         "color": charts.C_GOOD if f["pass"] else charts.C_BAD}
        for f in fairness
    ]
    fairness_svg = charts.bar_chart(
        fairness_items, max_value=1.1, threshold=THRESHOLDS["four_fifths"],
        threshold_label="0.80", value_fmt="{:.2f}",
    )
    robust_svg = charts.bar_chart(robust, max_value=1.0, value_fmt="{:.3f}")
    cm_svg = charts.confusion_matrix_svg(tn, fp, fn, tp)

    return {
        "auc": auc, "gini": gini, "ks": ks, "brier": brier,
        "psi_latest": psi_latest, "psi_series": list(zip(periods, psi_series)),
        "features": features, "fairness": fairness, "min_ratio": round(min_ratio, 3),
        "robust": robust, "rel_drop": round(rel_drop, 3),
        "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "checks": checks, "overall": overall, "n_fail": n_fail, "n_watch": n_watch,
        "charts": {
            "roc": roc_svg, "reliability": rel_svg, "psi": psi_svg,
            "features": feat_svg, "fairness": fairness_svg, "robust": robust_svg,
            "confusion": cm_svg,
        },
    }
