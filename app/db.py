"""SQLite persistence for API keys and request logs.

Both the API service and admin service share the same DB file via a Docker
volume mounted at DB_PATH. WAL mode is enabled so both services can read and
write concurrently without blocking each other.

Credentials are cached in-process (per-worker) for CACHE_TTL seconds so the
hot path (auth check per request) avoids a DB round-trip on every call. New
keys created via the admin panel become active within CACHE_TTL seconds.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger("facecompare.db")

DB_PATH: str = os.environ.get("DB_PATH", "/data/wiseface.db")

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS api_keys (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key      TEXT    UNIQUE NOT NULL,
    api_secret   TEXT    NOT NULL,
    client_label TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    is_active    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS request_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key       TEXT    NOT NULL DEFAULT '',
    requested_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    status_code   INTEGER NOT NULL,
    latency_ms    REAL    NOT NULL,
    confidence    REAL,
    error_message TEXT
);
"""

# Per-worker in-memory cache: api_key -> (api_secret, client_label)
_cred_cache: dict[str, tuple[str, str]] = {}
_cache_ts: float = 0.0
_CACHE_TTL: float = 30.0  # seconds


async def init_db() -> None:
    """Create schema and seed from API_CREDENTIALS env var if the table is empty."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()

        cur = await db.execute("SELECT COUNT(*) FROM api_keys")
        (count,) = await cur.fetchone()
        if count == 0:
            raw_env = os.environ.get("API_CREDENTIALS", "")
            try:
                seeds: list[dict] = json.loads(raw_env) if raw_env else []
            except json.JSONDecodeError:
                seeds = []
            for c in seeds:
                await db.execute(
                    "INSERT OR IGNORE INTO api_keys (api_key, api_secret, client_label) "
                    "VALUES (?, ?, ?)",
                    (c["api_key"], c["api_secret"], c.get("client", "")),
                )
            if seeds:
                await db.commit()
                logger.info("DB seeded with %d credential(s) from API_CREDENTIALS.", len(seeds))


async def count_active_keys() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM api_keys WHERE is_active = 1")
        (n,) = await cur.fetchone()
        return n


async def _refresh_cache() -> None:
    global _cred_cache, _cache_ts
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT api_key, api_secret, client_label FROM api_keys WHERE is_active = 1"
        )
        rows = await cur.fetchall()
    _cred_cache = {r[0]: (r[1], r[2]) for r in rows}
    _cache_ts = time.monotonic()


async def authenticate(api_key: str, api_secret: str) -> Optional[str]:
    """Return client_label if credentials are valid and active, else None."""
    if time.monotonic() - _cache_ts >= _CACHE_TTL:
        await _refresh_cache()
    entry = _cred_cache.get(api_key)
    if entry and entry[0] == api_secret:
        return entry[1]
    return None


async def log_request(
    api_key: str,
    status_code: int,
    latency_ms: float,
    confidence: Optional[float],
    error_message: Optional[str],
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO request_logs "
            "(api_key, status_code, latency_ms, confidence, error_message) "
            "VALUES (?, ?, ?, ?, ?)",
            (api_key, status_code, latency_ms, confidence, error_message),
        )
        await db.commit()
