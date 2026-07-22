from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import yaml
from croniter import croniter
from fastapi import FastAPI, HTTPException
from redis.asyncio import Redis

TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Shanghai"))
last_run: dict[str, str] = {}
redis_client: Redis | None = None


def jobs() -> dict:
    source = Path(os.getenv("JOBS_CONFIG", "/config/jobs.yaml"))
    return (yaml.safe_load(source.read_text(encoding="utf-8")) or {}).get("jobs", {})


async def invoke(name: str, spec: dict) -> dict:
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.request(spec.get("method", "POST"), spec["url"], json=spec.get("body", {}))
        response.raise_for_status()
        payload = response.json()
        notify = spec.get("notify")
        if notify:
            text = str(payload.get(notify.get("field", "message"), "")).strip()
            if text:
                notification = await client.post(
                    os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8083") + "/v1/notifications",
                    json={"channel": "feishu_webhook", "route": notify["route"], "text": text},
                )
                notification.raise_for_status()
    last_run[name] = datetime.now(TZ).isoformat()
    return {"ok": True, "name": name, "status_code": response.status_code, "result": payload}


async def worker() -> None:
    while True:
        now = datetime.now(TZ).replace(second=0, microsecond=0)
        for name, spec in jobs().items():
            if not spec.get("enabled", True):
                continue
            marker = now.isoformat()
            lock_acquired = last_run.get(name) != marker
            if croniter.match(spec["cron"], now) and redis_client:
                try:
                    lock_acquired = bool(await redis_client.set(f"scheduler:{name}:{marker}", "1", ex=86400, nx=True))
                except Exception as exc:
                    print(f"scheduler redis lock unavailable name={name} error={exc}", flush=True)
            if croniter.match(spec["cron"], now) and lock_acquired:
                try:
                    await invoke(name, spec)
                    last_run[name] = marker
                except Exception as exc:
                    print(f"scheduler job failed name={name} error={exc}", flush=True)
        await asyncio.sleep(20)


app = FastAPI(title="AI Platform Scheduler", version="1.0.0")


@app.on_event("startup")
async def startup() -> None:
    global redis_client
    redis_client = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    asyncio.create_task(worker())


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "scheduler", "jobs": list(jobs()), "last_run": last_run}


@app.post("/v1/jobs/{name}/run")
async def run_job(name: str) -> dict:
    spec = jobs().get(name)
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown job")
    return await invoke(name, spec)
