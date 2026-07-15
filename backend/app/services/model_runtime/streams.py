from __future__ import annotations

import asyncio
import inspect
from typing import Any


async def aclose_async_iterator(iterator: Any) -> None:
    close = getattr(iterator, "aclose", None)
    if not callable(close):
        close = getattr(iterator, "close", None)
    if not callable(close):
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except asyncio.CancelledError:
        raise
    except Exception:
        return
