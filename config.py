"""
Central configuration.

Reads settings from environment variables (and a local .env file if present).
The single most important runtime fact this exposes is LIVE_MODE: whether a real
OpenAI key is configured. When it is False, Track B runs in clearly-labelled
simulated mode and makes no network calls.
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

# ── OpenAI / Track B ─────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_CHATBOT_MODEL = os.getenv("OPENAI_CHATBOT_MODEL", "gpt-4o-mini").strip()
OPENAI_JUDGE_MODEL = os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o-mini").strip()

# Live mode is on only when a key is actually present.
LIVE_MODE = bool(OPENAI_API_KEY)

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
