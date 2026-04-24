"""
Toei Bus Guide PoC FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from routers import gtfs as gtfs_router
from routers import chat as chat_router
from routers import dify_tools as dify_tools_router
from services import gtfs_static

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Eagerly load static GTFS data on startup
    stops = gtfs_static.get_stops()
    routes = gtfs_static.get_routes()
    logger.info("GTFS static data loaded: %d stops, %d routes", len(stops), len(routes))
    yield


app = FastAPI(
    title="Toei Bus Guide PoC",
    description="Toei Bus operation guide PoC with real-time vehicle map and Dify chat integration",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow all origins for PoC
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(gtfs_router.router, prefix="/api/gtfs", tags=["GTFS"])
app.include_router(chat_router.router, prefix="/api/chat", tags=["Chat"])
app.include_router(dify_tools_router.router, tags=["Dify"])


# Serve the frontend static files if the directory exists
if FRONTEND_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/app/index.html")


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
