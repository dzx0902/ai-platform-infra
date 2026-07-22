from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class Note(BaseModel):
    category: str = Field(pattern="^(papers|finance|reviews|research)$")
    filename: str
    content: str
    tags: list[str] = Field(default_factory=list)


ROOT = Path(os.getenv("KNOWLEDGE_DIR", "/knowledge"))
app = FastAPI(title="AI Platform Knowledge Sync", version="1.0.0")


def safe_name(value: str) -> str:
    name = Path(value).name
    if name != value or not name.endswith(".md"):
        raise ValueError("filename must be a Markdown file name")
    return name


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/v1/notes")
def write_note(note: Note) -> dict[str, str]:
    try:
        filename = safe_name(note.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    target = ROOT / note.category / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = "---\ntags: [" + ", ".join(note.tags) + "]\n---\n\n" if note.tags else ""
    target.write_text(frontmatter + note.content, encoding="utf-8")
    return {"ok": "true", "path": str(target.relative_to(ROOT))}


@app.post("/v1/sync")
def sync() -> dict[str, str]:
    if not (ROOT / ".git").exists():
        raise HTTPException(status_code=409, detail="Knowledge directory is not a Git repository")
    subprocess.run(["git", "add", "."], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-m", "chore: sync AI platform knowledge"], cwd=ROOT, check=False)
    subprocess.run(["git", "push", "origin", os.getenv("KNOWLEDGE_GIT_BRANCH", "main")], cwd=ROOT, check=True)
    return {"ok": "true"}
