from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class Query(BaseModel):
    question: str
    source_type: str | None = None
    category: str | None = None
    n_results: int = 6


app = FastAPI(title="AI Platform RAG Service", version="1.0.0")


@app.get("/health")
async def health() -> dict:
    chroma_url = os.getenv("CHROMA_URL", "http://chromadb:8000")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(chroma_url)
        return {"ok": response.is_success, "chroma_url": chroma_url}
    except httpx.HTTPError:
        return {"ok": False, "chroma_url": chroma_url}


@app.post("/v1/query")
async def query(request: Query) -> dict:
    workspace = os.getenv("WORKSPACE_AGENT_URL", "http://workspace-agent:8001")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(f"{workspace}/ask", json=request.model_dump())
    if response.is_error:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()
