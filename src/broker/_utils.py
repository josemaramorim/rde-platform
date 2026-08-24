"""
Shared async utility for broker adapters.
"""
import asyncio
import concurrent.futures


def run_async(coro):
    """
    Run a coroutine from synchronous code, handling event loop state.
    Use this instead of duplicating the pattern in each broker file.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=120)
    else:
        return asyncio.run(coro)
