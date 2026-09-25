"""
In-memory async-safe TTL cache for repository analysis results and preview assets.
Supports request coalescing (single-flight) to prevent redundant upstream API calls.
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Tuple, Callable, Awaitable, Any

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 30 * 60  # 30 minutes
DEFAULT_GITHUB_CACHE_TTL_SECONDS = 5 * 60  # 5 minutes for upstream GitHub REST API data


class AnalysisCache:
    """
    In-memory async-safe TTL cache with in-flight request coalescing.
    Used for analysis results, static preview assets, and shared GitHub REST API responses.
    """

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS, case_sensitive: bool = False):
        self.ttl_seconds = ttl_seconds
        self.case_sensitive = case_sensitive
        # key -> (payload, expires_at_timestamp)
        self._cache: Dict[str, Tuple[Any, float]] = {}
        # key -> asyncio.Future for in-flight leader-follower coalescing
        self._in_flight: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    def _format_key(self, key: str) -> str:
        """Format key according to cache case sensitivity setting."""
        cleaned = key.strip()
        return cleaned if self.case_sensitive else cleaned.lower()

    @staticmethod
    def normalize_key(owner: str, repo: str) -> str:
        """Normalize owner and repository to lowercase key."""
        return f"{owner.strip().lower()}/{repo.strip().lower()}"

    async def get_by_key(self, key: str) -> Optional[Any]:
        """Get cached value by exact string key if not expired."""
        normalized_key = self._format_key(key)
        async with self._lock:
            entry = self._cache.get(normalized_key)
            if entry:
                value, expires_at = entry
                if time.monotonic() < expires_at:
                    return value
                del self._cache[normalized_key]
        return None

    async def set_by_key(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Store value with TTL by exact string key."""
        normalized_key = self._format_key(key)
        ttl_val = ttl if ttl is not None else self.ttl_seconds
        expires_at = time.monotonic() + ttl_val
        async with self._lock:
            self._cache[normalized_key] = (value, expires_at)

    async def get_or_compute_by_key(
        self,
        key: str,
        compute_fn: Callable[[], Awaitable[Any]],
        ttl: Optional[float] = None,
    ) -> Any:
        """
        Retrieve cached result or compute it asynchronously with in-flight coalescing.
        If multiple coroutines request the same key concurrently, only one runs compute_fn,
        and all others await the result. Errors are never cached.
        """
        normalized_key = self._format_key(key)

        async with self._lock:
            entry = self._cache.get(normalized_key)
            if entry:
                cached_res, expires_at = entry
                if time.monotonic() < expires_at:
                    return cached_res
                del self._cache[normalized_key]

            if normalized_key in self._in_flight:
                future = self._in_flight[normalized_key]
                is_leader = False
            else:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self._in_flight[normalized_key] = future
                is_leader = True

        if not is_leader:
            logger.debug("Coalescing concurrent request for %s to in-flight leader", normalized_key)
            return await future

        try:
            result = await compute_fn()
            await self.set_by_key(normalized_key, result, ttl=ttl)
            if not future.done():
                future.set_result(result)
            return result
        except Exception as exc:
            if not future.done():
                future.set_exception(exc)
                future.exception()
            raise
        finally:
            async with self._lock:
                self._in_flight.pop(normalized_key, None)

    async def get(self, owner: str, repo: str) -> Optional[Any]:
        """Convenience method for (owner, repo) pairs."""
        return await self.get_by_key(self.normalize_key(owner, repo))

    async def set(self, owner: str, repo: str, response: Any, ttl: Optional[float] = None) -> None:
        """Convenience method for (owner, repo) pairs."""
        await self.set_by_key(self.normalize_key(owner, repo), response, ttl=ttl)

    async def get_or_compute(
        self,
        owner: str,
        repo: str,
        compute_fn: Callable[[], Awaitable[Any]],
        ttl: Optional[float] = None,
    ) -> Any:
        """Convenience method for (owner, repo) pairs."""
        return await self.get_or_compute_by_key(self.normalize_key(owner, repo), compute_fn, ttl=ttl)

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
github_api_cache = AnalysisCache(ttl_seconds=DEFAULT_GITHUB_CACHE_TTL_SECONDS, case_sensitive=True)

