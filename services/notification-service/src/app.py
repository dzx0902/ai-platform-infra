from __future__ import annotations

import os
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class Notification(BaseModel):
    channel: Literal["feishu_webhook", "log"] = "log"
    text: str
    route: Literal["paper", "finance", "default"] = "default"


app = FastAPI(title="AI Platform Notification Service", version="1.0.0")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/v1/notifications")
async def notify(item: Notification) -> dict[str, bool]:
    if item.channel == "log":
        print(item.text, flush=True)
        return {"ok": True}
    webhook_names = {
        "paper": "FEISHU_PAPER_WEBHOOK_URL",
        "finance": "FEISHU_FINANCE_WEBHOOK_URL",
        "default": "FEISHU_WEBHOOK_URL",
    }
    webhook = os.getenv(webhook_names[item.route], "")
    if not webhook:
        raise HTTPException(status_code=503, detail=f"Webhook route is not configured: {item.route}")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(webhook, json={"msg_type": "text", "content": {"text": item.text}})
        response.raise_for_status()
    return {"ok": True}
