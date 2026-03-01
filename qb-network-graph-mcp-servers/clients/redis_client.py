"""
Redis cache client — hot subgraph caching with TTL-based invalidation.

Cache key patterns:
  entity:{id}                     → golden record profile (TTL 1h)
  rels:{id}                       → entity relationships (TTL 1h)
  subgraph:{id}:{depth}           → network subgraph (TTL 30m)
  connections:{company}:{type}    → company connections (TTL 1h)
  traverse:{start}:{hops_hash}   → supply chain traversal (TTL 15m)

Falls back gracefully if Redis is unavailable (same pattern as GraphDBClient).
"""
from __future__ import annotations
import hashlib
import json
import logging

from config import RedisConfig

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

# TTLs for different cache key patterns (seconds)
_TTLS = {
    "entity": 3600,       # 1 hour
    "rels": 3600,         # 1 hour
    "subgraph": 1800,     # 30 minutes
    "connections": 3600,  # 1 hour
    "traverse": 900,      # 15 minutes
}


class RedisClient:
    def __init__(self, cfg: RedisConfig):
        self._cfg = cfg
        self._pool: aioredis.Redis | None = None
        self._available = False

    async def connect(self):
        if not HAS_REDIS:
            logger.warning("redis package not installed — Redis cache unavailable")
            return
        try:
            kwargs = {
                "host": self._cfg.host,
                "port": self._cfg.port,
                "db": self._cfg.db,
                "decode_responses": True,
            }
            if self._cfg.password:
                kwargs["password"] = self._cfg.password

            self._pool = aioredis.Redis(**kwargs)
            await self._pool.ping()
            self._available = True
            logger.info(f"Redis connected: {self._cfg.host}:{self._cfg.port}")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}) — caching disabled")

    async def close(self):
        if self._pool:
            await self._pool.aclose()
            logger.info("Redis connection closed")

    @property
    def available(self) -> bool:
        return self._available

    # ── Cache operations ─────────────────────────────────────

    async def get_cached(self, key: str) -> dict | None:
        """Get a cached value by key. Returns None on miss or error."""
        if not self._available:
            return None
        try:
            raw = await self._pool.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.debug(f"Redis GET {key} failed: {e}")
            return None

    async def set_cached(self, key: str, value: dict, ttl: int = None):
        """Set a cached value with TTL. Uses pattern-based default TTL if not specified."""
        if not self._available:
            return
        if ttl is None:
            prefix = key.split(":")[0]
            ttl = _TTLS.get(prefix, self._cfg.default_ttl)
        try:
            await self._pool.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception as e:
            logger.debug(f"Redis SET {key} failed: {e}")

    async def invalidate(self, *keys: str):
        """Delete specific cache keys."""
        if not self._available or not keys:
            return
        try:
            await self._pool.delete(*keys)
        except Exception as e:
            logger.debug(f"Redis DELETE failed: {e}")

    async def invalidate_entity(self, entity_id: str):
        """Invalidate all cache keys related to an entity.

        Deletes: entity:{id}, rels:{id}, subgraph:{id}:*, traverse:* containing the entity.
        Uses SCAN to find pattern-matched keys without blocking.
        """
        if not self._available:
            return
        try:
            keys_to_delete = [
                f"entity:{entity_id}",
                f"rels:{entity_id}",
            ]
            # Scan for subgraph and traverse keys containing this entity
            for pattern in [f"subgraph:{entity_id}:*", f"connections:{entity_id}:*"]:
                async for key in self._pool.scan_iter(match=pattern, count=100):
                    keys_to_delete.append(key)

            if keys_to_delete:
                await self._pool.delete(*keys_to_delete)
                logger.debug(f"Redis invalidated {len(keys_to_delete)} keys for entity {entity_id}")
        except Exception as e:
            logger.debug(f"Redis invalidate_entity {entity_id} failed: {e}")

    # ── Key helpers ──────────────────────────────────────────

    @staticmethod
    def traverse_key(start_id: str, hops: list[str]) -> str:
        """Build a cache key for a traversal result."""
        hops_hash = hashlib.md5(json.dumps(hops).encode()).hexdigest()[:8]
        return f"traverse:{start_id}:{hops_hash}"

    @staticmethod
    def connections_key(company_id: str, connection_type: str) -> str:
        return f"connections:{company_id}:{connection_type}"
