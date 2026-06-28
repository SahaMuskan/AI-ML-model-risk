"""
Model Risk Studio — FastAPI application.

Run with:   uvicorn app:app --reload
Then open:  http://127.0.0.1:8000
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
import database
import report as report_mod
import tiering
import validation_llm
import validation_ml

app = FastAPI(title=config.APP_TITLE)
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))


@app.on_event("startup")
def _startup() -> None:
    database.ensure_seeded()


# ── Template helpers ─────────────────────────────────────────────────────────
def render(request: Request, template: str, **ctx: Any) -> HTMLResponse:
    base = {
        "request": request,
        "app_title": config.APP_TITLE,
        "app_subtitle": config.APP_SUBTITLE,
        "live_mode": config.LIVE_MODE,
        "disclaimers": config.DISCLAIMERS,
        "chatbot_model": config.OPENAI_CHATBOT_MODEL,
        "judge_model": config.OPENAI_JUDGE_MODEL,
        "today": date.today().strftime("%d %b %Y"),
    }
    base.update(ctx)
    # Starlette's current signature is TemplateResponse(request, name, context).
    return templates.TemplateResponse(request, template, base)


# ── Dashboard ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    import charts

    models = [tiering.enrich(m) for m in database.get_all_models()]
    findings = database.get_all_findings()

    ml = [m for m in models if not m["_tier"]["is_llm"]]
    gen = [m for m in models if m["_tier"]["is_llm"]]
    tier_counts = {1: 0, 2: 0, 3: 0}
    for m in models:
        tier_counts[m["_tier"]["tier"]] += 1

    overdue = [m for m in models if m["_reval"]["state"] == "overdue"]
    due_soon = [m for m in models if m["_reval"]["state"] == "due_soon"]

    open_findings = [f for f in findings if f.get("status") != "Closed"]

    def _overdue_finding(f):
        td = f.get("target_date")
        try:
            return td and date.fromisoformat(td) < date.today() and f.get("status") != "Closed"
        except ValueError:
            return False

    overdue_findings = [f for f in open_findings if _overdue_finding(f)]
    sev_counts = {"High": 0, "Medium": 0, "Low": 0}
    for f in open_findings:
        sev_counts[f.get("severity", "Low")] = sev_counts.get(f.get("severity", "Low"), 0) + 1

    family_donut = charts.donut([
        {"label": "Traditional ML", "value": len(ml), "color": charts.C_PRIMARY},
        {"label": "Generative / LLM", "value": len(gen), "color": "#7d5ba6"},
    ])
    tier_donut = charts.donut([
        {"label": "Tier 1", "value": tier_counts[1], "color": charts.C_BAD},
        {"label": "Tier 2", "value": tier_counts[2], "color": charts.C_WARN},
        {"label": "Tier 3", "value": tier_counts[3], "color": charts.C_GOOD},
    ])

    return render(
        request, "dashboard.html",
        models=models, total=len(models),
        ml_count=len(ml), gen_count=len(gen),
        tier_counts=tier_counts,
        overdue=overdue, due_soon=due_soon,
        ok_count=len(models) - len(overdue) - len(due_soon),
        open_findings=open_findings, overdue_findings=overdue_findings,
        sev_counts=sev_counts,
        family_donut=family_donut, tier_donut=tier_donut,
    )


# ── Inventory ────────────────────────────────────────────────────────────────
@app.get("/inventory", response_class=HTMLResponse)
def inventory(request: Request, family: str = "", tier: str = "",
              area: str = "", q: str = "") -> HTMLResponse:
    models = [tiering.enrich(m) for m in database.get_all_models()]
    areas = sorted({m.get("business_area", "") for m in models})

    def keep(m: dict[str, Any]) -> bool:
        if family == "ml" and m["_tier"]["is_llm"]:
            return False
        if family == "gen" and not m["_tier"]["is_llm"]:
            return False
        if tier and str(m["_tier"]["tier"]) != tier:
            return False
        if area and m.get("business_area") != area:
            return False
        if q and q.lower() not in (m["name"] + m["id"] + m.get("owner", "")).lower():
            return False
        return True

    filtered = [m for m in models if keep(m)]
    return render(request, "inventory.html", models=filtered, areas=areas,
                  family=family, tier=tier, area=area, q=q, total=len(filtered))


# ── Model detail / tiering ───────────────────────────────────────────────────
@app.get("/models/{model_id}", response_class=HTMLResponse)
def model_detail(request: Request, model_id: str) -> HTMLResponse:
    model = database.get_model(model_id)
    if not model:
        return render(request, "not_found.html", model_id=model_id)
    enriched = tiering.enrich(model)
    findings = database.get_findings_for_model(model_id)
    dims = tiering.applicable_dimensions(model)
    return render(request, "model_detail.html", m=enriched, findings=findings,
                  dimensions=dims, rating_word=tiering.RATING_WORD)


@app.post("/models/{model_id}/ratings")
async def save_ratings(request: Request, model_id: str) -> RedirectResponse:
    model = database.get_model(model_id)
    if not model:
        return RedirectResponse(url="/inventory", status_code=303)
    form = await request.form()
    ratings = dict(model.get("ratings", {}))
    for d in tiering.applicable_dimensions(model):
        key = d["key"]
        if key in form:
            try:
                ratings[key] = min(3, max(1, int(form[key])))
            except (ValueError, TypeError):
                pass
    model["ratings"] = ratings
    if form.get("last_validation_date"):
        model["last_validation_date"] = str(form["last_validation_date"])
    database.upsert_model(model)
    return RedirectResponse(url=f"/models/{model_id}", status_code=303)


@app.post("/api/tiering/preview")
async def tiering_preview(request: Request) -> JSONResponse:
    data = await request.json()
    pseudo = {"family": data.get("family", "Traditional ML"),
              "ratings": {k: int(v) for k, v in data.get("ratings", {}).items()}}
    return JSONResponse(tiering.compute_tier(pseudo))


# ── Track A — traditional ML validation ──────────────────────────────────────
@app.get("/models/{model_id}/track-a", response_class=HTMLResponse)
def track_a(request: Request, model_id: str) -> HTMLResponse:
    model = database.get_model(model_id)
    if not model:
        return render(request, "not_found.html", model_id=model_id)
    enriched = tiering.enrich(model)
    results = validation_ml.generate(model)
    return render(request, "track_a.html", m=enriched, r=results,
                  thresholds=validation_ml.THRESHOLDS)


# ── Track B — generative / LLM validation ────────────────────────────────────
@app.get("/models/{model_id}/track-b", response_class=HTMLResponse)
def track_b(request: Request, model_id: str) -> HTMLResponse:
    model = database.get_model(model_id)
    if not model:
        return render(request, "not_found.html", model_id=model_id)
    enriched = tiering.enrich(model)
    system_prompt = model.get("system_prompt") or validation_llm.DEFAULT_CHATBOT_SYSTEM_PROMPT
    guardrails = validation_llm.detect_guardrails(system_prompt)
    estimate = validation_llm.estimate_calls(validation_llm.TEST_KEYS)
    return render(
        request, "track_b.html", m=enriched,
        system_prompt=system_prompt,
        guardrails=guardrails, guardrail_labels=validation_llm.GUARDRAIL_LABELS,
        tests=validation_llm.TEST_REGISTRY,
        estimate=estimate,
        last_run=model.get("llm_last_run"),
        default_prompt=validation_llm.DEFAULT_CHATBOT_SYSTEM_PROMPT,
    )


@app.post("/models/{model_id}/track-b/system-prompt")
async def save_system_prompt(request: Request, model_id: str) -> RedirectResponse:
    model = database.get_model(model_id)
    if model:
        form = await request.form()
        model["system_prompt"] = str(form.get("system_prompt", ""))
        database.upsert_model(model)
    return RedirectResponse(url=f"/models/{model_id}/track-b", status_code=303)


@app.post("/models/{model_id}/track-b/reset-prompt")
def reset_system_prompt(model_id: str) -> RedirectResponse:
    model = database.get_model(model_id)
    if model:
        model["system_prompt"] = validation_llm.DEFAULT_CHATBOT_SYSTEM_PROMPT
        database.upsert_model(model)
    return RedirectResponse(url=f"/models/{model_id}/track-b", status_code=303)


@app.post("/models/{model_id}/track-b/run")
async def run_track_b(request: Request, model_id: str) -> RedirectResponse:
    model = database.get_model(model_id)
    if not model:
        return RedirectResponse(url="/inventory", status_code=303)
    form = await request.form()
    selected = form.getlist("tests") or validation_llm.TEST_KEYS
    # Run against the prompt currently in the editor (and persist that edit), so
    # "tweak a guardrail and run" works in a single click.
    submitted_prompt = form.get("system_prompt")
    if submitted_prompt is not None and str(submitted_prompt).strip():
        system_prompt = str(submitted_prompt)
        model["system_prompt"] = system_prompt
    else:
        system_prompt = model.get("system_prompt") or validation_llm.DEFAULT_CHATBOT_SYSTEM_PROMPT
    result = validation_llm.run_suite(system_prompt, selected)
    model["llm_last_run"] = result
    database.upsert_model(model)
    return RedirectResponse(url=f"/models/{model_id}/track-b", status_code=303)


# ── Findings ─────────────────────────────────────────────────────────────────
@app.get("/findings", response_class=HTMLResponse)
def findings_page(request: Request, status: str = "", severity: str = "",
                  model_id: str = "") -> HTMLResponse:
    findings = database.get_all_findings()
    models = {m["id"]: m for m in database.get_all_models()}

    for f in findings:
        td = f.get("target_date")
        try:
            f["_overdue"] = bool(td) and date.fromisoformat(td) < date.today() and f.get("status") != "Closed"
        except ValueError:
            f["_overdue"] = False
        f["_model_name"] = models.get(f.get("model_id"), {}).get("name", f.get("model_id"))

    def keep(f):
        if status and f.get("status") != status:
            return False
        if severity and f.get("severity") != severity:
            return False
        if model_id and f.get("model_id") != model_id:
            return False
        return True

    filtered = sorted([f for f in findings if keep(f)],
                      key=lambda f: (f.get("status") == "Closed", not f["_overdue"],
                                     {"High": 0, "Medium": 1, "Low": 2}.get(f.get("severity"), 3)))
    return render(request, "findings.html", findings=filtered,
                  models=sorted(models.values(), key=lambda m: m["id"]),
                  status=status, severity=severity, model_id=model_id)


@app.post("/findings/new")
async def add_finding(request: Request) -> RedirectResponse:
    form = await request.form()
    finding = {
        "id": database.next_finding_id(),
        "model_id": str(form.get("model_id", "")),
        "title": str(form.get("title", "Untitled finding")),
        "description": str(form.get("description", "")),
        "source": str(form.get("source", "Validation")),
        "severity": str(form.get("severity", "Medium")),
        "owner": str(form.get("owner", "")),
        "raised_date": date.today().isoformat(),
        "target_date": str(form.get("target_date", "")),
        "status": "Open",
    }
    database.upsert_finding(finding)
    return RedirectResponse(url="/findings", status_code=303)


@app.post("/findings/{finding_id}/status")
async def update_finding_status(request: Request, finding_id: str) -> RedirectResponse:
    form = await request.form()
    finding = database.get_finding(finding_id)
    if finding:
        finding["status"] = str(form.get("status", finding.get("status")))
        database.upsert_finding(finding)
    return RedirectResponse(url=str(form.get("next", "/findings")), status_code=303)


# ── Report ───────────────────────────────────────────────────────────────────
@app.get("/models/{model_id}/report", response_class=HTMLResponse)
def model_report(request: Request, model_id: str) -> HTMLResponse:
    model = database.get_model(model_id)
    if not model:
        return render(request, "not_found.html", model_id=model_id)
    rpt = report_mod.build_report(model)
    return render(request, "report.html", r=rpt)


@app.get("/models/{model_id}/report.md", response_class=PlainTextResponse)
def model_report_md(model_id: str) -> PlainTextResponse:
    model = database.get_model(model_id)
    if not model:
        return PlainTextResponse("Model not found", status_code=404)
    rpt = report_mod.build_report(model)
    md = report_mod.build_markdown(rpt)
    return PlainTextResponse(
        md, headers={"Content-Disposition": f'attachment; filename="{model_id}-validation-report.md"'}
    )


# ── Methodology & lifecycle ──────────────────────────────────────────────────
@app.get("/methodology", response_class=HTMLResponse)
def methodology(request: Request) -> HTMLResponse:
    estimate = validation_llm.estimate_calls(validation_llm.TEST_KEYS)
    return render(request, "methodology.html",
                  dimensions=tiering.DIMENSIONS,
                  thresholds=validation_ml.THRESHOLDS,
                  tests=validation_llm.TEST_REGISTRY,
                  estimate=estimate)


@app.get("/lifecycle", response_class=HTMLResponse)
def lifecycle(request: Request) -> HTMLResponse:
    return render(request, "lifecycle.html")


# ── Admin ────────────────────────────────────────────────────────────────────
@app.post("/reset-demo")
def reset_demo() -> RedirectResponse:
    database.reset_to_demo()
    return RedirectResponse(url="/", status_code=303)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "live_mode": config.LIVE_MODE,
            "models": len(database.get_all_models()),
            "time": datetime.utcnow().isoformat()}
