"""
SafeMerchant Backend Server Entrypoint.
Configures Windows SelectorEventLoop for psycopg async compatibility and launches Uvicorn.
"""

import sys
import asyncio
import selectors

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        import uvicorn.loops.asyncio
        uvicorn.loops.asyncio.asyncio_loop_factory = lambda use_subprocess=False: lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    except Exception:
        pass

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        loop="asyncio",
        reload=False,
    )
