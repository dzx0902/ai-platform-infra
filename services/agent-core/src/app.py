from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    messages: list[dict[str, Any]]
    provider: str = "auto"
    model: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=16384)


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    provider: str = "auto"
    model: str | None = None


def provider_config(provider: str) -> tuple[str, str, str]:
    selected = provider.lower().strip()
    if selected == "auto":
        selected = os.getenv("LLM_DEFAULT_PROVIDER", "deepseek")
    values = {
        "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"),
        "qwen": ("QWEN_API_KEY", "QWEN_BASE_URL", "QWEN_MODEL"),
        "openai": ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"),
    }
    if selected not in values:
        raise ValueError(f"Unsupported provider: {selected}")
    key_name, base_name, model_name = values[selected]
    return os.getenv(key_name, ""), os.getenv(base_name, ""), os.getenv(model_name, "")


def load_agents() -> dict[str, Any]:
    path = Path(os.getenv("AGENTS_CONFIG", "/config/agents.yaml"))
    if not path.exists():
        return {}
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("agents", {})


app = FastAPI(title="AI Platform Agent Core", version="1.0.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "agent-core", "agents": sorted(load_agents())}


@app.get("/v1/agents")
def agents() -> dict[str, Any]:
    return {"agents": load_agents()}


@app.post("/v1/generate")
def generate(request: GenerateRequest) -> dict[str, Any]:
    try:
        api_key, base_url, default_model = provider_config(request.provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not api_key:
        raise HTTPException(status_code=503, detail="Selected LLM provider is not configured")
    response = OpenAI(api_key=api_key, base_url=base_url).chat.completions.create(
        model=request.model or default_model,
        messages=request.messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    return {
        "content": response.choices[0].message.content or "",
        "model": response.model,
        "provider": request.provider,
        "usage": response.usage.model_dump() if response.usage else None,
    }


@app.post("/v1/embeddings")
def embeddings(request: EmbeddingRequest) -> dict[str, Any]:
    try:
        api_key, base_url, default_model = provider_config(request.provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not api_key:
        raise HTTPException(status_code=503, detail="Selected embedding provider is not configured")
    response = OpenAI(api_key=api_key, base_url=base_url).embeddings.create(
        model=request.model or default_model,
        input=request.input,
    )
    return {"data": [{"embedding": item.embedding, "index": item.index} for item in response.data], "model": response.model}
