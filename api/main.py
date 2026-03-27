from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from db import engine
from routes import query, repos

app = FastAPI(title="Codebase Intelligence Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repos.router)
app.include_router(query.router)


@app.on_event("startup")
async def verify_db() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
