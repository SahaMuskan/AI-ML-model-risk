# Setup Guide

How to get **Model Risk Studio** running and connected to your organisation's LLM
service. This covers local setup, the three supported LLM providers, switching from
simulated to live mode, and common problems.

For **deploying to a server** (Docker, Azure, AWS, on-prem, auth, scaling), see
[DEPLOYMENT.md](DEPLOYMENT.md).

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.10+** | Check with `python --version`. 3.10 through 3.14 all work. |
| **pip** | Ships with Python. |
| **Git** | To clone the repo (or download the ZIP). |
| An LLM endpoint *(optional)* | Only needed for **live** Track B tests. The app runs fully without one. |

You do **not** need a database server, Node.js, or any build tooling. Everything is
Python + server-rendered HTML.

---

## 2. Get the code

```bash
git clone https://github.com/SahaMuskan/AI-ML-model-risk.git
cd AI-ML-model-risk
```

---

## 3. Install

```bash
# 1. create a virtual environment (recommended)
python -m venv .venv

# 2. activate it
#    Windows (PowerShell):
.venv\Scripts\Activate.ps1
#    Windows (cmd):
.venv\Scripts\activate.bat
#    macOS / Linux:
source .venv/bin/activate

# 3. install dependencies
pip install -r requirements.txt
```

---

## 4. Run (simulated mode — no key needed)

```bash
uvicorn app:app --reload
```

Open **http://127.0.0.1:8000**.

The top bar shows **● SIMULATED**. Every screen works, Track B returns clearly-labelled
illustrative answers, and **nothing is sent to any external service**. This is the right
mode for a first look, a demo, or an air-gapped environment.

> **Port already in use?** Add `--port 8050` (or any free port) to the command.

---

## 5. Connect your LLM service (live mode)

Live mode makes Track B send **real** prompts to a live model and have a second model
judge the open-ended answers. To enable it, create a `.env` file and pick your provider.

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Then edit `.env`. There are **three** ways to connect, selected by `LLM_PROVIDER`.

### Option A — OpenAI direct

Simplest; for evaluation or where the bank is comfortable calling OpenAI directly.

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_CHATBOT_MODEL=gpt-4o-mini
OPENAI_JUDGE_MODEL=gpt-4o-mini
```

### Option B — Azure OpenAI Service  *(recommended for banks)*

Calls stay inside your Azure tenant. The model names are your **deployment names**, not
the underlying model ids.

```dotenv
LLM_PROVIDER=azure
OPENAI_API_KEY=<your Azure OpenAI key>
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-01
OPENAI_CHATBOT_MODEL=<your deployment name, e.g. gpt-4o-mini>
OPENAI_JUDGE_MODEL=<your deployment name>
```

Where to find these in the Azure Portal:
- **`AZURE_OPENAI_ENDPOINT`** and **`OPENAI_API_KEY`** → your Azure OpenAI resource → *Keys and Endpoint*.
- **`OPENAI_CHATBOT_MODEL` / `OPENAI_JUDGE_MODEL`** → *Azure OpenAI Studio → Deployments* (use the **deployment name** column).
- **`AZURE_OPENAI_API_VERSION`** → use the version your resource supports; `2024-02-01` is a safe default.

### Option C — Internal LLM gateway / "LLM Garden" *(any OpenAI-compatible proxy)*

For banks that route all model traffic through an internal gateway. Works with anything
that speaks the OpenAI REST contract — internal proxies, vLLM, Ollama, LiteLLM, an AWS
Bedrock OpenAI-compatible gateway, etc.

```dotenv
LLM_PROVIDER=custom
OPENAI_API_KEY=<gateway key or service-account token>
OPENAI_BASE_URL=https://llm-gateway.internal.yourbank.com/v1
OPENAI_CHATBOT_MODEL=<model name as the gateway exposes it>
OPENAI_JUDGE_MODEL=<model name as the gateway exposes it>
```

> The `OPENAI_BASE_URL` must point at the OpenAI-compatible root (it usually ends in
> `/v1`). Ask your platform team for the exact URL and how to authenticate.

### Then restart

```bash
uvicorn app:app --reload
```

The top bar should now read **● LIVE**. If it still says SIMULATED, see §7.

---

## 6. Verify it's working

1. **Health check** — open **http://127.0.0.1:8000/health**. You should see
   `"live_mode": true` once credentials are set.
2. **Run a real test** — open **MR-012 (NorthBank Assistant)** → **Validate (Track B)** →
   **Run tests**. In live mode the cost panel shows real token counts and latency.
3. **Smoke-test the connection cheaply** — untick all but one test (e.g. *Consistency*)
   before running, so you spend only a few calls while confirming connectivity.

---

## 7. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Top bar still says **SIMULATED** after setting a key | `.env` not picked up — confirm the file is named exactly `.env`, in the project root, and **restart** the server. For Azure, `LIVE_MODE` also requires `AZURE_OPENAI_ENDPOINT` to be set. |
| Track B shows an error banner after running | The LLM call failed. The banner contains the provider error. Check the key, endpoint URL, and (Azure/custom) that `OPENAI_CHATBOT_MODEL` matches a **real deployment / model name**. |
| `port already in use` on startup | Another process holds the port. Use `--port 8050`. |
| Non-ASCII characters garbled in the console (Windows) | Run with `python -X utf8 -m uvicorn app:app` or set `PYTHONUTF8=1`. (Affects console logs only, not the web UI.) |
| `ModuleNotFoundError` | The virtual environment isn't activated, or deps aren't installed — re-run steps in §3. |
| Want to start over with fresh demo data | Click **Reset demo** (top right), or delete `data/mrm.db` and restart. |

---

## 8. Make it your own (customising for a real bank)

This ships with **fictional** demo data. To pilot it with real content:

- **Replace the demo models & findings** → edit `seed_data.py`, then click **Reset demo**
  (or call `database.reset_to_demo()`). See *Useful entry points* in [CLAUDE.md](CLAUDE.md).
- **Point Track B at your real chatbot's system prompt** → on a model's *Validate (Track B)*
  page, paste your production system prompt into the editor and run. The guardrail badges
  update automatically.
- **Tune the risk tiering** → `tiering.py` (`DIMENSIONS`, weights, thresholds, escalation rules).
- **Tune Track A thresholds** → `validation_ml.THRESHOLDS`.

> Reminder: the bundled thresholds and evaluation sets are **starting points**, not
> validated standards. Calibrate them against your own policy and larger samples before
> relying on the results. See the caveats in [README.md](README.md).
