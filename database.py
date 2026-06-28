"""
A deliberately small persistence layer over SQLite.

Models and findings are stored as JSON documents (one row each) so the rich,
nested risk-rating and test-evidence structures can evolve without migrations.
SQLite keeps everything in a single file (data/mrm.db) so the app is fully
self-contained and your edits persist between sessions.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from config import DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS models (id TEXT PRIMARY KEY, data TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS findings (id TEXT PRIMARY KEY, data TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )


# ── Models ───────────────────────────────────────────────────────────────────
def get_all_models() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT data FROM models").fetchall()
    models = [json.loads(r["data"]) for r in rows]
    models.sort(key=lambda m: m.get("id", ""))
    return models


def get_model(model_id: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT data FROM models WHERE id = ?", (model_id,)
        ).fetchone()
    return json.loads(row["data"]) if row else None


def upsert_model(model: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO models (id, data) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
            (model["id"], json.dumps(model)),
        )


# ── Findings ───────────────────────────────────────────────────────────────--
def get_all_findings() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT data FROM findings").fetchall()
    return [json.loads(r["data"]) for r in rows]


def get_findings_for_model(model_id: str) -> list[dict[str, Any]]:
    return [f for f in get_all_findings() if f.get("model_id") == model_id]


def get_finding(finding_id: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT data FROM findings WHERE id = ?", (finding_id,)
        ).fetchone()
    return json.loads(row["data"]) if row else None


def upsert_finding(finding: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO findings (id, data) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
            (finding["id"], json.dumps(finding)),
        )


def next_finding_id() -> str:
    findings = get_all_findings()
    nums = []
    for f in findings:
        fid = f.get("id", "")
        if fid.startswith("F-") and fid[2:].isdigit():
            nums.append(int(fid[2:]))
    return f"F-{(max(nums) + 1) if nums else 1:03d}"


# ── Meta / seeding ─────────────────────────────────────────────────────────--
def _get_meta(key: str) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _set_meta(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def is_seeded() -> bool:
    return _get_meta("seeded") == "1"


def reset_to_demo() -> None:
    """Wipe everything and reload the bundled demo data."""
    from seed_data import build_findings, build_models

    with _connect() as conn:
        conn.execute("DELETE FROM models")
        conn.execute("DELETE FROM findings")
    for m in build_models():
        upsert_model(m)
    for f in build_findings():
        upsert_finding(f)
    _set_meta("seeded", "1")


def ensure_seeded() -> None:
    init_db()
    if not is_seeded() or not get_all_models():
        reset_to_demo()
