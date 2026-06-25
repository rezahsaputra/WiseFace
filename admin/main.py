"""WiseFace Admin Service.

Provides:
  - Usage records by time window (hour / day / month / year)
  - API key CRUD (create, list, revoke)

Auth: POST /api/login -> bearer token stored client-side in localStorage.
All /api/* routes require Authorization: Bearer <token>.
"""
from __future__ import annotations

import os
import secrets
import string
import time
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_PATH: str = os.environ.get("DB_PATH", "/data/wiseface.db")
ADMIN_USER: str = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "")

# In-memory sessions: token -> monotonic expiry timestamp
_sessions: dict[str, float] = {}
_SESSION_TTL: float = 8 * 3600  # 8 hours

app = FastAPI(title="WiseFace Admin", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")

_bearer = HTTPBearer(auto_error=False)


def _require_auth(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = creds.credentials
    expiry = _sessions.get(token)
    if expiry is None or time.monotonic() > expiry:
        _sessions.pop(token, None)
        raise HTTPException(status_code=401, detail="Session expired")
    return token


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #

@app.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html")


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/login")
async def login(data: LoginRequest) -> dict:
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="ADMIN_PASSWORD not set on server")
    if data.username != ADMIN_USER or data.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_hex(32)
    _sessions[token] = time.monotonic() + _SESSION_TTL
    return {"token": token, "username": ADMIN_USER}


@app.post("/api/logout")
async def logout(token: str = Depends(_require_auth)) -> dict:
    _sessions.pop(token, None)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Usage
# --------------------------------------------------------------------------- #

_WINDOW_CONFIG: dict[str, tuple[str, str, str]] = {
    # window -> (sql_interval, display_label_expr, group_by_expr)
    "hour":  ("-1 hour",   "strftime('%H:%M', requested_at)",  "strftime('%Y-%m-%d %H:%M', requested_at)"),
    "day":   ("-1 day",    "strftime('%H:00', requested_at)",  "strftime('%Y-%m-%d %H',    requested_at)"),
    "month": ("-30 days",  "strftime('%d/%m', requested_at)",  "strftime('%Y-%m-%d',       requested_at)"),
    "year":  ("-365 days", "strftime('%m/%Y', requested_at)",  "strftime('%Y-%m',          requested_at)"),
}


@app.get("/api/usage")
async def get_usage(
    window: str = "day",
    _token: str = Depends(_require_auth),
) -> dict:
    if window not in _WINDOW_CONFIG:
        window = "day"
    interval, label_expr, group_expr = _WINDOW_CONFIG[window]

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Summary stats
        cur = await db.execute(
            f"""
            SELECT
                COUNT(*)                                                       AS total,
                SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END)            AS success,
                ROUND(AVG(latency_ms), 1)                                      AS avg_latency,
                ROUND(AVG(CASE WHEN status_code = 200 THEN confidence END), 2) AS avg_confidence
            FROM request_logs
            WHERE requested_at >= datetime('now', '{interval}')
            """
        )
        row = await cur.fetchone()
        summary = dict(row) if row else {}

        # Count of active keys (for the summary card)
        cur = await db.execute("SELECT COUNT(*) AS active_keys FROM api_keys WHERE is_active = 1")
        row = await cur.fetchone()
        summary["active_keys"] = row[0] if row else 0

        # Time-series buckets
        cur = await db.execute(
            f"""
            SELECT
                {label_expr}                                                   AS label,
                COUNT(*)                                                       AS total,
                SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END)            AS success,
                ROUND(AVG(latency_ms), 1)                                      AS avg_latency
            FROM request_logs
            WHERE requested_at >= datetime('now', '{interval}')
            GROUP BY {group_expr}
            ORDER BY {group_expr}
            """
        )
        rows = await cur.fetchall()
        buckets = [dict(r) for r in rows]

        # Per-key breakdown
        cur = await db.execute(
            f"""
            SELECT
                r.api_key,
                COALESCE(NULLIF(k.client_label, ''), r.api_key) AS label,
                COUNT(*)                                          AS total,
                SUM(CASE WHEN r.status_code = 200 THEN 1 ELSE 0 END) AS success,
                ROUND(AVG(r.latency_ms), 1)                       AS avg_latency
            FROM request_logs r
            LEFT JOIN api_keys k ON r.api_key = k.api_key
            WHERE r.requested_at >= datetime('now', '{interval}')
            GROUP BY r.api_key
            ORDER BY total DESC
            """
        )
        rows = await cur.fetchall()
        by_key = [dict(r) for r in rows]

    return {"summary": summary, "buckets": buckets, "by_key": by_key}


# --------------------------------------------------------------------------- #
# API Keys
# --------------------------------------------------------------------------- #

@app.get("/api/keys")
async def list_keys(_token: str = Depends(_require_auth)) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, api_key, api_secret, client_label, created_at, is_active "
            "FROM api_keys ORDER BY id DESC"
        )
        rows = await cur.fetchall()

    keys = []
    for r in rows:
        d = dict(r)
        ak = d["api_key"]
        # Mask key for display; keep full value for copy-to-clipboard
        d["api_key_masked"] = (ak[:8] + "..." + ak[-4:]) if len(ak) > 12 else ak
        keys.append(d)
    return {"keys": keys}


class CreateKeyRequest(BaseModel):
    client_label: str


_CHARS = string.ascii_letters + string.digits


def _gen(n: int = 32) -> str:
    return "".join(secrets.choice(_CHARS) for _ in range(n))


@app.post("/api/keys", status_code=201)
async def create_key(
    data: CreateKeyRequest,
    _token: str = Depends(_require_auth),
) -> dict:
    api_key = _gen(32)
    api_secret = _gen(32)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO api_keys (api_key, api_secret, client_label) VALUES (?, ?, ?)",
            (api_key, api_secret, data.client_label),
        )
        await db.commit()
        key_id = cur.lastrowid
    return {
        "id": key_id,
        "api_key": api_key,
        "api_secret": api_secret,
        "client_label": data.client_label,
    }


@app.delete("/api/keys/{key_id}")
async def revoke_key(
    key_id: int,
    _token: str = Depends(_require_auth),
) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE api_keys SET is_active = 0 WHERE id = ? AND is_active = 1",
            (key_id,),
        )
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Key not found or already revoked")
    return {"revoked": True, "id": key_id}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
