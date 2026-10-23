"""Shared Redis client. Redis is optional in development: callers must handle ``None``."""

from __future__ import annotations

import logging
from functools import lru_cache

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_redis() -> redis.Redis | None:
    url = get_settings().redis_url
    if not url:
        return None
    client = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1, decode_responses=False)
    try:
        client.ping()
    except redis.RedisError:
        logger.warning("redis_unavailable", extra={"redis_url": url.split("@")[-1]})
        return None
    return client
