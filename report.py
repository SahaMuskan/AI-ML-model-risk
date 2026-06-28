"""
Auto-drafts an SR 11-7-style validation report for a model, pulling from its
profile, its tiering rationale, its validation evidence (Track A or Track B),
and its open findings — and reaching an overall validation opinion.

The opinion logic is deliberately simple and transparent; it is a drafting aid,
not a substitute for reviewer judgement.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import database
import tiering
import validation_ml


def _open_findings(model_id: str) -> list[dict[str, Any]]:
    return [f for f in database.get_findings_for_model(model_id) if f.get("status") != "Closed"]


def _is_overdue(finding: dict[str, Any]) -> bool:
    td = finding.get("target_date")
    if not td:
        return False
    try:
        return date.fromisoformat(td) < date.today() and finding.get("status") != "Closed"
    except ValueError:
        return False


def _opinion(model, tier_info, track, evidence, open_findings):
    high_open = [f for f in open_findings if f.get("severity") == "High"]
    overdue_high = [f for f in high_open if _is_overdue(f)]
    overdue_any = [f for f in open_findings if _is_overdue(f)]

    evidence_overall = None
    evidence_ran = True
    if track == "A":
        evidence_overall = evidence["overall"]
    else:
        if evidence and evidence.get("ok"):
            evidence_overall = evidence["summary"]["overall"]
        else:
            evidence_ran = False

    reasons: list[str] = []
    # Decision
    if overdue_high or evidence_overall == "FAIL":
        opinion = "Not approved"
        if overdue_high:
            reasons.append(f"{len(overdue_high)} high-severity finding(s) are open and overdue.")
        if evidence_overall == "FAIL":
            reasons.append("Validation testing shows at least one failed check against threshold.")
    elif high_open or evidence_overall == "WATCH" or overdue_any or not evidence_ran:
        opinion = "Approved with conditions"
        if high_open:
            reasons.append(f"{len(high_open)} high-severity finding(s) remain open.")
        if evidence_overall == "WATCH":
            reasons.append("Some validation checks are in a 'watch' state near threshold.")
        if overdue_any:
            reasons.append(f"{len(overdue_any)} finding(s) are past their target date.")
        if not evidence_ran:
            reasons.append("No Track B test evidence has been captured yet for this model.")
    else:
        opinion = "Approved"
        reasons.append("No open high-severity findings; validation evidence within thresholds.")

    # Tier-driven condition
    if opinion != "Not approved" and tier_info["tier"] == 1:
        reasons.append("Tier 1 model — annual revalidation and enhanced ongoing monitoring required.")

    return opinion, reasons


def build_report(model: dict[str, Any]) -> dict[str, Any]:
    tier_info = tiering.compute_tier(model)
    reval = tiering.revalidation_status(model, tier_info)
    is_llm = tier_info["is_llm"]
    track = "B" if is_llm else "A"

    if track == "A":
        evidence = validation_ml.generate(model)
    else:
        evidence = model.get("llm_last_run")

    open_findings = _open_findings(model["id"])
    all_findings = database.get_findings_for_model(model["id"])
    opinion, opinion_reasons = _opinion(model, tier_info, track, evidence, open_findings)

    # Executive summary text
    exec_summary = (
        f"{model['name']} ({model['id']}) is a {model['family'].lower()} model owned by "
        f"{model.get('owner', 'n/a')} in {model.get('business_area', 'n/a')}. It is assessed as "
        f"{tier_info['tier_label']} under the AI-specific risk-tiering approach, with a "
        f"revalidation cadence of {tier_info['frequency_label'].lower()}. "
    )
    if track == "A":
        exec_summary += (
            f"The traditional validation battery returned an overall status of "
            f"'{evidence['overall']}' across {len(evidence['checks'])} checks. "
        )
    else:
        if evidence and evidence.get("ok"):
            s = evidence["summary"]
            exec_summary += (
                f"The most recent Track B (GenAI) test run ({evidence['mode']} mode) returned an "
                f"overall status of '{s['overall']}' across {s['total']} test areas. "
            )
        else:
            exec_summary += "No Track B test evidence has been captured yet. "
    exec_summary += (
        f"There are {len(open_findings)} open finding(s). The overall validation opinion is "
        f"'{opinion}'."
    )

    return {
        "model": model,
        "generated": date.today().strftime("%d %b %Y"),
        "tier": tier_info,
        "reval": reval,
        "track": track,
        "is_llm": is_llm,
        "evidence": evidence,
        "open_findings": open_findings,
        "all_findings": all_findings,
        "exec_summary": exec_summary,
        "opinion": opinion,
        "opinion_reasons": opinion_reasons,
    }


def build_markdown(report: dict[str, Any]) -> str:
    """Render the report as Markdown for download."""
    m = report["model"]
    t = report["tier"]
    lines = [
        f"# Model Validation Report — {m['name']} ({m['id']})",
        "",
        f"*Generated {report['generated']} · SR 11-7-style draft · ILLUSTRATIVE*",
        "",
        "## 1. Executive summary",
        "",
        report["exec_summary"],
        "",
        "## 2. Model overview",
        "",
        f"- **Owner:** {m.get('owner', 'n/a')}",
        f"- **Business area:** {m.get('business_area', 'n/a')}",
        f"- **Family:** {m.get('family')}",
        f"- **Methodology:** {m.get('methodology', 'n/a')}",
        f"- **In-house / vendor:** {m.get('vendor', 'n/a')}",
        f"- **Status:** {m.get('status', 'n/a')}",
        f"- **Go-live:** {m.get('go_live_date') or 'n/a'}",
        f"- **Last validation:** {m.get('last_validation_date') or 'Never'}",
        f"- **Purpose:** {m.get('purpose', 'n/a')}",
        "",
        "## 3. Risk tiering rationale",
        "",
        f"**{t['tier_label']}** (weighted score {t['score']}/3.0) — "
        f"revalidation: {t['frequency_label']}; next due {report['reval']['next_due_str']} "
        f"({report['reval']['state_label']}).",
        "",
        "| Dimension | Rating | Weight | Basis |",
        "| --- | --- | --- | --- |",
    ]
    for c in t["contributions"]:
        lines.append(f"| {c['label']} | {c['rating_word']} | {c['weight']} | {c['level_text']} |")
    if t["escalations"]:
        lines.append("")
        lines.append("**Escalations applied:**")
        for e in t["escalations"]:
            lines.append(f"- {e}")
    lines += ["", "## 4. Validation results", ""]
    if report["track"] == "A":
        ev = report["evidence"]
        lines.append(f"Overall: **{ev['overall']}**")
        lines.append("")
        lines.append("| Check | Value | Threshold | Result |")
        lines.append("| --- | --- | --- | --- |")
        for c in ev["checks"]:
            lines.append(f"| {c['name']} | {c['value']} | {c['threshold']} | {c['grade']} |")
    else:
        ev = report["evidence"]
        if ev and ev.get("ok"):
            lines.append(f"Track B run ({ev['mode']} mode), overall: **{ev['summary']['overall']}**")
            lines.append("")
            lines.append("| Test area | Status | Metric |")
            lines.append("| --- | --- | --- |")
            for tst in ev["tests"]:
                lines.append(f"| {tst['name']} | {tst['status']} | {tst.get('metric', '')} |")
        else:
            lines.append("_No Track B test evidence captured yet._")
    lines += ["", "## 5. Findings / issues", ""]
    if report["all_findings"]:
        lines.append("| ID | Severity | Status | Title | Target |")
        lines.append("| --- | --- | --- | --- | --- |")
        for f in report["all_findings"]:
            lines.append(
                f"| {f['id']} | {f.get('severity')} | {f.get('status')} | {f.get('title')} | {f.get('target_date', '')} |"
            )
    else:
        lines.append("_No findings recorded._")
    lines += [
        "",
        "## 6. Validation opinion",
        "",
        f"**{report['opinion']}**",
        "",
    ]
    for r in report["opinion_reasons"]:
        lines.append(f"- {r}")
    lines += [
        "",
        "---",
        "_This is an auto-generated draft from illustrative data. Thresholds and test "
        "sets are starting points requiring calibration. SR 11-7, the NIST AI RMF and the "
        "EU AI Act evolve — verify against current versions for your jurisdiction._",
    ]
    return "\n".join(lines)
