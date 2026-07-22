from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from fastapi import FastAPI
from pydantic import BaseModel, Field


class MemoryWrite(BaseModel):
    user_id: str = "default"
    namespace: str = "general"
    key: str
    value: dict[str, Any] = Field(default_factory=dict)


def connection():
    return psycopg.connect(os.environ["POSTGRES_URL"])


def initialize() -> None:
    with connection() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id BIGSERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                value JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                UNIQUE(user_id, namespace, key)
            )
        """)


app = FastAPI(title="AI Platform Memory Service", version="1.0.0")


@app.on_event("startup")
def startup() -> None:
    initialize()


@app.get("/health")
def health() -> dict[str, str]:
    return {"ok": "true", "service": "memory-service"}


@app.get("/v1/memory")
def get_memory(user_id: str = "default", namespace: str = "general") -> dict[str, Any]:
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT key, value, updated_at FROM memory WHERE user_id=%s AND namespace=%s ORDER BY key", (user_id, namespace))
        rows = cur.fetchall()
    return {"items": [{"key": key, "value": value, "updated_at": updated_at} for key, value, updated_at in rows]}


@app.post("/v1/memory")
def put_memory(item: MemoryWrite) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with connection() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO memory (user_id, namespace, key, value, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, namespace, key) DO UPDATE
            SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at
        """, (item.user_id, item.namespace, item.key, psycopg.types.json.Jsonb(item.value), now))
    return {"ok": True, "updated_at": now}
