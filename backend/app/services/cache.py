"""
In-memory async-safe TTL cache for repository analysis results.
Supports request coalescing (single-flight) to prevent redundant upstream API calls.
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Tuple, Callable, Awaitable, Any

from app.models import AnalysisResponse

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 30 * 60  # 30 minutes


class AnalysisCache:
    """
    In-memory async-safe TTL cache for repository analysis responses.
    Includes in-flight request coalescing to prevent duplicate concurrent upstream calls.
    """

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        # key -> (AnalysisResponse, expires_at_timestamp)
        self._cache: Dict[str, Tuple[AnalysisResponse, float]] = {}
        # key -> asyncio.Future for in-flight leader-follower coalescing
        self._in_flight: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def normalize_key(owner: str, repo: str) -> str:
        """Normalize owner and repository to lowercase key."""
        return f"{owner.strip().lower()}/{repo.strip().lower()}"

    async def get(self, owner: str, repo: str) -> Optional[AnalysisResponse]:
        """Get cached response if present and not expired."""
        key = self.normalize_key(owner, repo)
        async with self._lock:
            entry = self._cache.get(key)
            if entry:
                response, expires_at = entry
                if time.monotonic() < expires_at:
                    return response
                # Entry expired: remove from cache
                del self._cache[key]
        return None

    async def set(
        self,
        owner: str,
        repo: str,
        response: AnalysisResponse,
        ttl: Optional[float] = None
    ) -> None:
        """Store a successful analysis response with TTL."""
        key = self.normalize_key(owner, repo)
        ttl_val = ttl if ttl is not None else self.ttl_seconds
        expires_at = time.monotonic() + ttl_val
        async with self._lock:
            self._cache[key] = (response, expires_at)

    async def get_or_compute(
        self,
        owner: str,
        repo: str,
        compute_fn: Callable[[], Awaitable[AnalysisResponse]],
        ttl: Optional[float] = None,
    ) -> AnalysisResponse:
        """
        Retrieve cached result or compute it asynchronously with in-flight coalescing.
        If multiple coroutines request the same key concurrently, only one runs compute_fn,
        and all others await the result. Errors are never cached.
        """
        key = self.normalize_key(owner, repo)

        async with self._lock:
            # 1. Check if already cached and valid
            entry = self._cache.get(key)
            if entry:
                cached_res, expires_at = entry
                if time.monotonic() < expires_at:
                    return cached_res
                del self._cache[key]

            # 2. Check if another coroutine is already in-flight for this key
            if key in self._in_flight:
                future = self._in_flight[key]
                is_leader = False
            else:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self._in_flight[key] = future
                is_leader = True

        if not is_leader:
            # Follower: await the leader's computation
            logger.debug("Coalescing concurrent request for %s to in-flight leader", key)
            return await future

        # Leader: compute the result
        try:
            result = await compute_fn()
            # Only cache successful results
            await self.set(owner, repo, result, ttl=ttl)
            if not future.done():
                future.set_result(result)
            return result
        except Exception as exc:
            # Do NOT cache errors. Propagate error to followers.
            if not future.done():
                future.set_exception(exc)
                # Mark as retrieved so asyncio doesn't log unretrieved warning if no followers
                future.exception()
            raise
        finally:
            async with self._lock:
                self._in_flight.pop(key, None)

    async def clear(self) -> None:
        """Clear all cached entries and in-flight tasks."""
        async with self._lock:
            self._cache.clear()
            self._in_flight.clear()

    async def size(self) -> int:
        """Return the number of unexpired entries currently in cache."""
        async with self._lock:
            now = time.monotonic()
            expired = [k for k, (_, exp) in self._cache.items() if now >= exp]
            for k in expired:
                del self._cache[k]
            return len(self._cache)


analysis_cache = AnalysisCache()
