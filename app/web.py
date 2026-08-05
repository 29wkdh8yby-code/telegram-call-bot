"""Minimal aiohttp health check server."""
from __future__ import annotations

import json

from aiohttp import web

from app.database import get_session_factory


async def health(request: web.Request) -> web.Response:
    """Return 200 if DB is reachable."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_ok = False

    payload = {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "error",
    }
    status = 200 if db_ok else 503
    return web.Response(
        body=json.dumps(payload),
        status=status,
        content_type="application/json",
    )


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    return app
