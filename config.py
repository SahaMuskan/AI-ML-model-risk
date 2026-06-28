"""
Central configuration.

Reads settings from environment variables (and a local .env file if present).
The single most important runtime fact this exposes is LIVE_MODE: whether a real
LLM key/endpoint is configured. When it is False, Track B runs in clearly-labelled
simulated mode and makes no network calls.

Supported LLM providers (set LLM_PROVIDER in .env):
  openai  — Direct OpenAI API (default)
  azure   — Azure OpenAI Service (most common in banks)
  custom  — Any OpenAI-compatible endpoint, e.g. an internal LLM Garden proxy
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "mrm.db"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# ── LLM provider selection ────────────────────────────────────────────────────
# Values: "openai" | "azure" | "custom"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()

# ── Credentials & endpoints ───────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_CHATBOT_MODEL = os.getenv("OPENAI_CHATBOT_MODEL", "gpt-4o-mini").strip()
OPENAI_JUDGE_MODEL = os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o-mini").strip()

# azure provider
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01").strip()

# custom / LLM Garden provider — OpenAI-compatible base URL
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip()

# Live mode: a key (and, for Azure, an endpoint) must be present.
LIVE_MODE = bool(
    (LLM_PROVIDER == "azure" and AZURE_OPENAI_ENDPOINT and OPENAI_API_KEY)
    or (LLM_PROVIDER in ("openai", "custom") and OPENAI_API_KEY)
)

APP_TITLE = "Model Risk Studio"
APP_SUBTITLE = "AI / ML Model Governance & Validation Framework"

# A short, honest standing disclaimer surfaced across the UI.
DISCLAIMERS = [
    "Results are ILLUSTRATIVE. Thresholds and the test/eval sets are starting "
    "points — they need proper calibration and larger samples before anyone "
    "relies on them.",
    "The GenAI (Track B) tests make REAL calls to a live model when an API key "
    "is configured, which costs money and consumes quota.",
    "SR 11-7, the NIST AI RMF and the EU AI Act all evolve. Check anything here "
    "against the current versions for your jurisdiction.",
]
