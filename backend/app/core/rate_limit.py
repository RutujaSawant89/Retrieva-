"""Fixed-window rate limiting backed by Redis, with an in-process fallback.

The in-process fallback is only correct for a single API process; production deployments run
with Redis so limits are shared across replicas.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

import redis

from app.core.errors import RateLimitedError
from app.core.redis import get_redis


class RateLimiter:
    def __init__(self) -> None:
        self._local: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int = 60) -> None:
        """Count one request for ``key``; raise ``RateLimitedError`` when over ``limit``."""
        if limit <= 0:
            return
        window = int(time.time() // window_seconds)
        retry_after = window_seconds - int(time.time() % window_seconds)
        bucket = f"ratelimit:{key}:{window}"
        count = self._hit_redis(bucket, window_seconds)
        if count is None:
            count = self._hit_local(bucket, window)
        if count > limit:
            raise RateLimitedError(
                "Too many requests, please slow down", details={"retry_after": retry_after, "limit": limit}
            )

    def _hit_redis(self, bucket: str, window_seconds: int) -> int | None:
        client = get_redis()
        if client is None:
            return None
        try:
            pipe = client.pipeline()
            pipe.incr(bucket)
            pipe.expire(bucket, window_seconds + 1)
            count, _ = pipe.execute()
            return int(count)
        except redis.RedisError:
            return None

    def _hit_local(self, bucket: str, window: int) -> int:
        with self._lock:
            if len(self._local) > 10_000:  # drop stale windows
                for key in [k for k, (_, w) in self._local.items() if w != window]:
                    del self._local[key]
            count, _ = self._local[bucket]
            self._local[bucket] = (count + 1, window)
            return count + 1

    def reset(self) -> None:
        with self._lock:
            self._local.clear()


rate_limiter = RateLimiter()
