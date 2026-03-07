"""Search service — global full-text search with Redis LRU cache."""
from __future__ import annotations

import json
import hashlib
import logging

from repositories.base import AbstractSearchRepository

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, search_repo: AbstractSearchRepository,
                 redis_client=None, search_ttl: int = 300,
                 search_max_keys: int = 200):
        self._repo = search_repo
        self._redis = redis_client
        self._ttl = search_ttl
        self._max_keys = search_max_keys
        self._cache_prefix = "search:"

    def search(self, q: str = None, industry: str = None,
               sort_by: str = None, limit: int = 50) -> dict:
        cache_key = self._cache_key(q, industry, sort_by, limit)

        # Try cache first
        cached = self._cache_get(cache_key)
        if cached is not None:
            return {"data": cached, "total": len(cached), "cached": True}

        # Miss — query Neo4j
        results = self._repo.search(q=q, industry=industry, sort_by=sort_by, limit=limit)

        self._cache_set(cache_key, results)
        return {"data": results, "total": len(results), "cached": False}

    def resolve_adhoc(self, name: str = None, ein: str = None,
                      city: str = None, state: str = None,
                      industry: str = None) -> dict:
        return {"data": self._repo.resolve_adhoc(
            name=name, ein=ein, city=city, state=state, industry=industry,
        )}

    # ── Cache helpers ─────────────────────────────────────

    def _cache_key(self, q, industry, sort_by, limit) -> str:
        raw = f"{(q or '').lower().strip()}|{industry or ''}|{sort_by or ''}|{limit}"
        h = hashlib.md5(raw.encode()).hexdigest()[:12]
        return f"{self._cache_prefix}{h}"

    def _cache_get(self, key: str):
        if not self._redis:
            return None
        try:
            data = self._redis.get(key)
            if data is None:
                return None
            # Touch key to refresh TTL (LRU behavior)
            self._redis.expire(key, self._ttl)
            return json.loads(data)
        except Exception as e:
            logger.debug("Redis cache get failed: %s", e)
            return None

    def _cache_set(self, key: str, results: list):
        if not self._redis:
            return
        try:
            self._redis.setex(key, self._ttl, json.dumps(results, default=str))
            self._evict_if_over_limit()
        except Exception as e:
            logger.debug("Redis cache set failed: %s", e)

    def _evict_if_over_limit(self):
        """Evict oldest keys when cache exceeds max_keys (LRU approximation)."""
        try:
            keys = list(self._redis.scan_iter(f"{self._cache_prefix}*"))
            if len(keys) <= self._max_keys:
                return
            # Get TTLs — keys with lowest TTL are oldest (least recently used)
            key_ttls = []
            for k in keys:
                ttl = self._redis.ttl(k)
                key_ttls.append((k, ttl if ttl > 0 else 0))
            key_ttls.sort(key=lambda x: x[1])
            to_remove = len(keys) - self._max_keys
            for k, _ in key_ttls[:to_remove]:
                self._redis.delete(k)
            logger.info("Evicted %d search cache keys (had %d, max %d)",
                        to_remove, len(keys), self._max_keys)
        except Exception as e:
            logger.debug("Redis eviction failed: %s", e)
