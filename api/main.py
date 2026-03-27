import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from db import engine
from routes import query, repos, ingest

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


@app.get("/models")
async def list_models():
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
    models = [
        {"name": m.name, "methods": m.supported_generation_methods}
        for m in genai.list_models()
        if "generateContent" in m.supported_generation_methods
    ]
    return {"models": models}

app.include_router(repos.router)
app.include_router(query.router)
app.include_router(ingest.router)


@app.on_event("startup")
async def verify_db() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
