# CLAUDE.md — project context

Context for Claude Code (and any collaborator) working in this repo. Read this first.

## What this is

**Model Risk Studio** — a working prototype of an AI/ML **model governance & validation framework** for model
risk management (MRM). It places **traditional ML** and **generative AI (LLM)** validation side by side, anchored
to **SR 11-7**, the **NIST AI RMF**, and the **EU AI Act** risk tiers. It is a self-contained FastAPI web app,
pre-loaded with ~18 fictional banking models so it demos immediately.

It is a portfolio / learning prototype, **not production software**. All results are illustrative.

## Run it

```bash
pip install -r requirements.txt      # a .venv with deps already exists locally
uvicorn app:app --reload             # → http://127.0.0.1:8000
```

- Boots in **simulated mode** with no credentials — every screen works, zero cost.
- For genuine Track B (LLM) tests: copy `.env.example` → `.env`, fill in your provider section, restart.
  `config.LIVE_MODE` is `True` only when a key (and, for Azure, an endpoint) is present.

**Supported LLM providers** (set `LLM_PROVIDER` in `.env`):

| `LLM_PROVIDER` | Typical use case | Extra env vars needed |
|---|---|---|
| `openai` (default) | Direct OpenAI API | `OPENAI_API_KEY` |
| `azure` | Azure OpenAI Service — most common in banks | `OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION` |
| `custom` | Any OpenAI-compatible proxy — internal LLM Garden, vLLM, Ollama | `OPENAI_API_KEY`, `OPENAI_BASE_URL` |

Model names (`OPENAI_CHATBOT_MODEL`, `OPENAI_JUDGE_MODEL`) are the same for all providers; for Azure they map to
your **deployment name**.

## Docker

```bash
docker build -t model-risk-studio .
docker run -p 8000:8000 --env-file .env model-risk-studio
```

For persistent data across restarts, mount the data directory:
```bash
docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/app/data model-risk-studio
```

## Architecture (all files are small and single-purpose)

| File | Responsibility |
| --- | --- |
| `app.py` | FastAPI routes + the `render()` helper. **No business logic** beyond wiring. |
| `config.py` | Env/.env settings; decides `LIVE_MODE`; standing disclaimers. |
| `database.py` | SQLite persistence. Models & findings stored as **JSON documents** (no ORM). `reset_to_demo()` / `ensure_seeded()`. |
| `seed_data.py` | The ~18 fictional models + 12 findings. Dates are computed **relative to `date.today()`** so overdue/due-soon always demo correctly. |
| `tiering.py` | The transparent AI-specific risk-tiering engine: `DIMENSIONS`, `compute_tier()`, `revalidation_status()`, `enrich()`. |
| `validation_ml.py` | **Track A** — illustrative traditional-ML metrics (deterministic per model id) + thresholds + pass/fail. |
| `validation_llm.py` | **Track B** — live LLM test suite + OpenAI client + guardrail-aware **simulated fallback**. Holds `DEFAULT_CHATBOT_SYSTEM_PROMPT` and the test data sets. |
| `report.py` | SR 11-7-style report drafter + Markdown export + validation-opinion logic. |
| `charts.py` | Dependency-free inline **SVG** charts (no CDN, works offline). |
| `templates/` | Jinja2 HTML (`base.html`, `_macros.html`, one per page). |
| `static/` | `style.css`, `app.js` (live tier recalc + run overlay). |
| `data/` | SQLite DB created at first run. **Git-ignored.** |

## Data model (a "model" JSON doc)

`id, name, owner, business_area, purpose, methodology, family ("Traditional ML" | "Generative AI / LLM"),
vendor, status, go_live_date, last_validation_date, ratings{dimension: 1|2|3}`. LLM models additionally carry
`system_prompt` and `llm_last_run` (the stored Track B result).

Tiering: each dimension is rated 1/2/3 (3 = highest risk); the tier is a **weighted average** mapped to
Tier 1 (≥2.33, annual) / Tier 2 (≥1.75, 2-yearly) / Tier 3 (3-yearly), plus a few **explicit escalation rules**.
Keep tiering transparent — every contribution and escalation is returned for display.

## How validation works (the two tracks)

- **Track A (traditional ML, `/models/{id}/track-a`):** discrimination (AUC/Gini/KS, confusion matrix),
  calibration (reliability, Brier), stability (PSI), explainability (feature importance), fairness (four-fifths),
  robustness. Each check is graded PASS/WATCH/FAIL against a threshold in `validation_ml.THRESHOLDS`.
- **Track B (GenAI, `/models/{id}/track-b`):** sends the chatbot prompts and checks the replies — consistency,
  quality (vs reference answers), groundedness/hallucination, prompt robustness, jailbreak resistance, refusal
  calibration, cost/speed. In **live** mode a second model is the LLM-as-judge; in **simulated** mode heuristic
  judges grade guardrail-aware canned answers. A **full run ≈ 43 calls** live (~24 chatbot-only in simulated).

The signature demo: on Track B, delete the *"Never reveal… system instructions"* line from the system prompt and
re-run — jailbreak resistance flips to FAIL. This works in simulated mode too (see `detect_guardrails` +
`_sim_chatbot`).

## Conventions & gotchas

- **Python 3.14**, **Starlette ≥1.3**: use the current signature
  `templates.TemplateResponse(request, name, context)` — the old `(name, context)` form raises a 500.
- On Windows, console output of non-ASCII (e.g. `≥`) needs `python -X utf8` or `PYTHONUTF8=1`.
- Charts are server-rendered SVG strings injected with `| safe` — no JS chart lib, keep it offline-capable.
- **Never commit** `.env`, `data/`, or `.venv/` (already in `.gitignore`).
- Results are illustrative; thresholds and Track B eval sets are starting points needing calibration. The
  regulatory frameworks evolve — keep the in-product disclaimers intact.

## Useful entry points

- Add/adjust a model or finding → `seed_data.py`, then **Reset demo** in the UI (or `database.reset_to_demo()`).
- Add a tiering dimension → `tiering.DIMENSIONS` (set `applies` to `"all"` or `"llm"` and a `weight`).
- Add a Track B test → add data + a `_run_*` function in `validation_llm.py` and register it in `TEST_REGISTRY`/`_RUNNERS`.
- Tune Track A thresholds → `validation_ml.THRESHOLDS`.
