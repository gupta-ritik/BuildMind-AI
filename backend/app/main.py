"""BuildMind AI backend entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as tasks_router
from app.db.session import init_db

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="BuildMind AI API",
    description="AI-powered software engineering workspace with PostgreSQL, Redis, and persistent task history",
    version="0.5.0",
)


@app.on_event("startup")
def _startup() -> None:
    init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000","https://build-mind-ai.vercel.app/dashboard"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
