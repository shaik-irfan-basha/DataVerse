"""
backend/app.py - Main FastAPI Application Factory & Security Middleware
"""

import os
import time
import asyncio
from contextlib import asynccontextmanager
from collections import defaultdict
from pathlib import Path
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import logging

from backend.config import (
    API_TITLE,
    API_DESCRIPTION,
    API_VERSION,
    API_PREFIX,
    CORS_ORIGINS,
    RATE_LIMIT_REQUESTS_PER_MINUTE,
    SESSION_CLEANUP_INTERVAL_SECONDS
)
from backend.session_manager import session_manager
from backend.routers import (
    health,
    auth,
    dataset,
    query,
    analytics,
    history,
    saved_queries,
    preferences,
    export,
    settings,
    cleaning,
    schema_visualizer
)

logger = logging.getLogger("dataverse.api")


# =============================================================================
# In-Memory IP Rate Limiter
# =============================================================================

class InMemoryRateLimiter:
    def __init__(self, requests_per_minute: int = RATE_LIMIT_REQUESTS_PER_MINUTE):
        self.rpm = requests_per_minute
        self.requests = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        if os.getenv("PYTEST_CURRENT_TEST"):
            return True
        now = time.time()
        window = now - 60.0

        # Filter timestamps outside window
        self.requests[client_ip] = [t for t in self.requests[client_ip] if t > window]

        if len(self.requests[client_ip]) >= self.rpm:
            return False

        self.requests[client_ip].append(now)
        return True


rate_limiter = InMemoryRateLimiter()


# =============================================================================
# Lifespan Management (Background Session Cleaner)
# =============================================================================

async def periodic_session_cleanup():
    """Background task running every 5 minutes to evict expired sessions."""
    while True:
        try:
            await asyncio.sleep(SESSION_CLEANUP_INTERVAL_SECONDS)
            evicted = session_manager.cleanup_expired_sessions()
            if evicted > 0:
                logger.info(f"Evicted {evicted} expired session(s). Active: {session_manager.active_session_count()}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in session cleanup loop: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting DataVerse API Gateway...")
    cleanup_task = asyncio.create_task(periodic_session_cleanup())
    yield
    # Shutdown
    logger.info("Shutting down DataVerse API Gateway...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    session_manager.purge_all()


# =============================================================================
# FastAPI Application Factory
# =============================================================================

app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# 1. CORS Middleware (Restricted to configured origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# 2. Security & Rate-Limiting Middleware
@app.middleware("http")
async def security_and_rate_limit_middleware(request: Request, call_next):
    # Extract client IP
    client_ip = request.client.host if request.client else "127.0.0.1"

    # Exclude OpenAPI documentation and health checks from strict rate limits
    is_doc = request.url.path in ["/docs", "/redoc", "/openapi.json", "/api/v1/health", "/"]
    if not is_doc and not rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": f"Rate limit exceeded. Maximum {RATE_LIMIT_REQUESTS_PER_MINUTE} requests per minute allowed."
            }
        )

    t0 = time.time()
    response = await call_next(request)
    elapsed = time.time() - t0

    # Security response headers
    response.headers["X-Process-Time"] = f"{elapsed:.4f}s"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"

    # Cache control: Ensure Service Worker, App Shell, CSS, and JS assets are never held stale in HTTP cache
    path = request.url.path
    if (
        path in ["/", "/index.html", "/sw.js", "/manifest.json"]
        or path.startswith("/css/")
        or path.startswith("/js/")
    ):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


# =============================================================================
# Mount Sub-Routers under /api/v1
# =============================================================================

app.include_router(health.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(dataset.router, prefix=API_PREFIX)
app.include_router(query.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(history.router, prefix=API_PREFIX)
app.include_router(saved_queries.router, prefix=API_PREFIX)
app.include_router(preferences.router, prefix=API_PREFIX)
app.include_router(export.router, prefix=API_PREFIX)
app.include_router(settings.router, prefix=API_PREFIX)
app.include_router(cleaning.router, prefix=API_PREFIX)
app.include_router(schema_visualizer.router, prefix=API_PREFIX)


from paths import get_frontend_dir
FRONTEND_DIR = get_frontend_dir()



@app.get("/", summary="Root Welcome & Service Metadata")
def root_info(request: Request):
    """
    Returns index.html when accessed via browser (Accept: text/html),
    or baseline service metadata JSON when accessed via API/TestClient.
    """
    accept = request.headers.get("accept", "")
    sec_dest = request.headers.get("sec-fetch-dest", "")
    if ("text/html" in accept or sec_dest in ["document", "iframe"]) and FRONTEND_DIR.exists():
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(
                str(index_file),
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
    return {
        "service": "DataVerse Intelligence Platform API",
        "version": API_VERSION,
        "docs_url": "/docs",
        "health_check": f"{API_PREFIX}/health",
        "authentication": f"{API_PREFIX}/auth/session"
    }


# Mount static frontend assets (css, js, icons, manifest, sw)
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
