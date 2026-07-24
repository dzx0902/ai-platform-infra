from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import yaml
from croniter import croniter
from fastapi import FastAPI, HTTPException
from redis.asyncio import Redis

TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Shanghai"))
last_run: dict[str, str] = {}
redis_client: Redis | None = None
config_lock = asyncio.Lock()


def config_path() -> Path:
    return Path(os.getenv("JOBS_CONFIG", "/config/jobs.yaml"))


def load_config() -> dict[str, Any]:
    source = config_path()
    if not source.exists():
        source = Path(os.getenv("JOBS_TEMPLATE", "/config/jobs.yaml"))
    if not source.exists():
        return {}
    return yaml.safe_load(source.read_text(encoding="utf-8")) or {}


def save_config(config: dict[str, Any]) -> None:
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
        temporary = Path(handle.name)
    temporary.replace(target)


def jobs() -> dict:
    return load_config().get("jobs", {})


def job_summary(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "enabled": spec.get("enabled", True),
        "cron": spec.get("cron"),
        "time": daily_time_from_cron(str(spec.get("cron", ""))),
        "method": spec.get("method", "POST"),
        "url": spec.get("url"),
        "body": spec.get("body", {}),
        "notify": spec.get("notify"),
        "last_run": last_run.get(name),
    }


def daily_time_from_cron(cron: str) -> str | None:
    parts = cron.split()
    if len(parts) != 5:
        return None
    minute, hour, day, month, weekday = parts
    if day != "*" or month != "*" or weekday != "*":
        return None
    if not minute.isdigit() or not hour.isdigit():
        return None
    minute_int = int(minute)
    hour_int = int(hour)
    if not (0 <= minute_int <= 59 and 0 <= hour_int <= 23):
        return None
    return f"{hour_int:02d}:{minute_int:02d}"


def cron_from_daily_time(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="time must use HH:MM, for example 08:00") from exc
    return f"{parsed.minute} {parsed.hour} * * *"


def merge_job_patch(spec: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    updated = dict(spec)
    if "time" in patch:
        updated["cron"] = cron_from_daily_time(str(patch["time"]))
    if "enabled" in patch:
        updated["enabled"] = bool(patch["enabled"])
    if "body" in patch:
        body = patch["body"]
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be an object")
        updated["body"] = body
    return updated


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


@app.get("/v1/jobs")
def list_jobs() -> dict:
    return {"jobs": [job_summary(name, spec) for name, spec in jobs().items()]}


@app.get("/v1/jobs/{name}")
def get_job(name: str) -> dict:
    spec = jobs().get(name)
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown job")
    return job_summary(name, spec)


@app.patch("/v1/jobs/{name}")
async def update_job(name: str, patch: dict[str, Any]) -> dict:
    async with config_lock:
        config = load_config()
        configured_jobs = config.setdefault("jobs", {})
        spec = configured_jobs.get(name)
        if not spec:
            raise HTTPException(status_code=404, detail="Unknown job")
        configured_jobs[name] = merge_job_patch(spec, patch)
        save_config(config)
        return job_summary(name, configured_jobs[name])


@app.post("/v1/jobs/{name}/run")
async def run_job(name: str) -> dict:
    spec = jobs().get(name)
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown job")
    return await invoke(name, spec)
