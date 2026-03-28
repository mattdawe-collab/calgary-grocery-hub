"""
Calgary Grocery Hub — FastAPI Application
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.data import store
from api.routes import deals, insights, stores

DIST_DIR = Path(__file__).parent.parent / "dashboard" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.load()
    print(f"Loaded {len(store.current):,} current deals, {len(store.historical):,} historical records")
    yield


app = FastAPI(title="Calgary Grocery Hub API", lifespan=lifespan)

# Build CORS origins — always allow local dev, plus Railway domain if set
cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
]
railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
if railway_domain:
    cors_origins.append(f"https://{railway_domain}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def auto_reload_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        store.check_reload()
    return await call_next(request)

app.include_router(deals.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(stores.router, prefix="/api")

# Serve React production build — mount as fallback SPA
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="spa")
