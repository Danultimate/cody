import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from db import engine
from routes import query, repos

app = FastAPI(title="Codebase Intelligence Engine")

_cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "ok", "service": "Codebase Intelligence Engine"}

app.include_router(repos.router)
app.include_router(query.router)


@app.on_event("startup")
async def verify_db() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
