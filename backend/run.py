"""
Entry point for running the SafeMerchant backend with uvicorn.

Sets the Windows event loop policy before uvicorn creates its event loop,
which is required for psycopg (async) compatibility.

Usage:
    python run.py
"""

import asyncio
import platform
import sys

# psycopg (async) requires SelectorEventLoop on Windows.
# This MUST be set before uvicorn creates its event loop.
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
