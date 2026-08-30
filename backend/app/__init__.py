# SafeMerchant Backend — Autonomous AI Risk Manager

# ── Windows event loop policy fix ──
# psycopg (async) requires SelectorEventLoop on Windows.
# This must be set before any event loop is created.
import asyncio
import platform

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
