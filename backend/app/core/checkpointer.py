"""
LangGraph checkpoint persistence via AsyncPostgresSaver.

Persists graph thread state to PostgreSQL so that interrupted HITL
workflows can be resumed across server restarts.  The checkpointer
uses ``psycopg`` (async mode) — a separate connection from the
``asyncpg``-backed SQLAlchemy engine.

Usage (in lifespan):
    async with checkpointer_context() as checkpointer:
        graph = compile_graph_with_checkpointer(checkpointer)
"""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings
from app.dispute.agent.graph import build_dispute_graph

logger = logging.getLogger(__name__)


def _to_psycopg_dsn(sqlalchemy_url: str) -> str:
    """
    Convert a SQLAlchemy async DSN to a plain ``postgresql://`` DSN
    that ``psycopg`` understands.

    Examples:
        postgresql+asyncpg://user:pass@host/db  →  postgresql://user:pass@host/db
    """
    return re.sub(r"^postgresql\+asyncpg://", "postgresql://", sqlalchemy_url)


@asynccontextmanager
async def checkpointer_context():
    """
    Async context manager that yields a configured AsyncPostgresSaver.

    Manually constructs the connection pool with prepare_threshold=None
    to disable prepared statements for Transaction pooler (PgBouncer/Supabase),
    then initializes AsyncPostgresSaver.
    """
    dsn = _to_psycopg_dsn(settings.database_url)
    logger.info("Initialising LangGraph checkpointer connection pool (PostgreSQL)")

    async with AsyncConnectionPool(
        conninfo=dsn,
        kwargs={"prepare_threshold": None},
        max_size=10,
    ) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        logger.info("LangGraph checkpoint tables ready")
        yield checkpointer


def compile_graph_with_checkpointer(checkpointer: AsyncPostgresSaver):
    """
    Compile the dispute-resolution graph with:
      - PostgreSQL checkpointer for state persistence
      - Interrupt breakpoints before HITL nodes

    Returns a compiled ``CompiledStateGraph``.
    """
    graph_builder = build_dispute_graph()

    compiled = graph_builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review", "refund_review"],
    )

    logger.info(
        "Dispute graph compiled with checkpointer and interrupt_before=%s",
        ["human_review", "refund_review"],
    )
    return compiled
