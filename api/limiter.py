import os

import redis.asyncio as aioredis
from fastapi import Request

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")
INDEX_LIMIT_PER_IP = 1
INDEX_WINDOW_SECONDS = 86400  # 24h
QUESTION_LIMIT = 5
QUESTION_WINDOW_SECONDS = 1800  # 30min
GLOBAL_INDEX_LIMIT = 20
GLOBAL_WINDOW_SECONDS = 3600  # 1h

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def _get_ip(request: Request) -> str:
    return (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


async def check_index_allowed(request: Request) -> tuple[bool, str]:
    """Returns (allowed, reason). reason: '' | 'ip' | 'global'. Fails open on Redis error."""
    try:
        r = _client()
        if await r.exists("global_index_count"):
            count = int(await r.get("global_index_count") or 0)
            if count >= GLOBAL_INDEX_LIMIT:
                return False, "global"
        ip = _get_ip(request)
        if await r.exists(f"index_limit:{ip}"):
            return False, "ip"
    except Exception:
        pass
    return True, ""


async def record_index_start(request: Request) -> None:
    try:
        r = _client()
        ip = _get_ip(request)
        await r.setex(f"index_limit:{ip}", INDEX_WINDOW_SECONDS, 1)
        pipe = r.pipeline()
        pipe.incr("global_index_count")
        pipe.expire("global_index_count", GLOBAL_WINDOW_SECONDS)
        await pipe.execute()
    except Exception:
        pass


async def check_question_limit(session_id: str) -> int:
    """Returns questions remaining (0–5). Fails open (returns 5) on error."""
    if not session_id:
        return QUESTION_LIMIT
    try:
        r = _client()
        count = await r.get(f"session:{session_id}:questions")
        used = int(count) if count else 0
        return max(0, QUESTION_LIMIT - used)
    except Exception:
        return QUESTION_LIMIT


async def record_question(session_id: str) -> int:
    """Increments question count, returns remaining. Fails open on error."""
    if not session_id:
        return QUESTION_LIMIT
    try:
        r = _client()
        key = f"session:{session_id}:questions"
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, QUESTION_WINDOW_SECONDS)
        result = await pipe.execute()
        used = result[0]
        return max(0, QUESTION_LIMIT - used)
    except Exception:
        return QUESTION_LIMIT
