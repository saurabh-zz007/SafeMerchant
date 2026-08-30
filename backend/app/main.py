"""
FastAPI application factory.

Assembles the app with:
  - Async lifespan for DB engine startup/shutdown
  - LangGraph checkpointer initialization (AsyncPostgresSaver)
  - CORS middleware for Flutter frontend
  - REST routes (webhook, disputes, review, health)
  - WebSocket routes (agent observability)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.dispute.routes import router as api_router
from app.dispute.metrics_routes import router as metrics_router
from app.dispute.websocket import router as ws_router
from app.core.config import settings
from app.core.db import engine
from app.core.checkpointer import checkpointer_context, compile_graph_with_checkpointer

# ── Logging ──
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup/shutdown) ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage async resources across the app lifecycle.

    Startup:
      1. Enter the LangGraph PostgreSQL checkpointer context
      2. Compile the dispute graph with checkpointer + interrupt breakpoints
      3. Store both on ``app.state`` for use by route handlers

    Shutdown:
      1. Exit the checkpointer context (closes psycopg pool)
      2. Dispose the SQLAlchemy async engine
    """
    logger.info("🚀 SafeMerchant Risk Agent starting up...")
    logger.info("   Database: %s", settings.database_url.split("@")[-1])  # Log host only

    # ── LangGraph Checkpointer ──
    async with checkpointer_context() as checkpointer:
        compiled_graph = compile_graph_with_checkpointer(checkpointer)

        app.state.checkpointer = checkpointer
        app.state.graph = compiled_graph

        logger.info("✅ LangGraph checkpointer and compiled graph ready")

        yield

    logger.info("🛑 Shutting down — disposing DB engine...")
    await engine.dispose()


# ── App Factory ──
app = FastAPI(
    title="SafeMerchant — Autonomous AI Risk Manager",
    description=(
        "Defense-only agentic system that ingests payment dispute webhooks, "
        "gathers evidence, scores winnability, and drafts bank response letters."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# ── CORS (allow Flutter web/mobile) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount Routers ──
app.include_router(api_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(ws_router)
