#!/usr/bin/env python3
"""
Estado de "escuchado/visto" en SQLite, compartido entre serve.py (API) y
freshrss_html_generator.py (filtra al renderizar). Solo local: no se llama
a la API de FreshRSS para marcar leído en origen — el artículo simplemente
deja de aparecer en esta web, aunque siga "unread" en FreshRSS.
"""
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("LISTENED_DB", "data/listened.db")


def _connect():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS listened (id TEXT PRIMARY KEY, marked_at TEXT NOT NULL)"
    )
    return conn


def is_listened(item_id: str) -> bool:
    if not item_id:
        return False
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM listened WHERE id = ?", (item_id,)).fetchone()
        return row is not None


def listened_ids() -> set:
    with _connect() as conn:
        return {row[0] for row in conn.execute("SELECT id FROM listened")}


def mark_listened(item_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO listened (id, marked_at) VALUES (?, ?)",
            (item_id, datetime.now(timezone.utc).isoformat()),
        )
