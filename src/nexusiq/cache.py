"""Version- and identity-aware caching with Redis and graceful in-memory fallback."""
import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("nexusiq.cache")


def compute_cache_key(
    tenant_id: str,
    role: str,
    query: str,
    corpus_version: str = "v1",
    retriever_version: str = "default",
    namespace: str = "search",
) -> str:
    """Compute secure cache key incorporating access-control identity and versions.

    Formula from Blueprint § 10:
    cache_key = hash(tenant_id + user_role + normalized_query + corpus_version + retriever_version)
    """
    normalized_query = re.sub(r"\s+", " ", query.strip().lower())
    payload = f"{namespace}:{tenant_id}:{role}:{normalized_query}:{corpus_version}:{retriever_version}"
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()[:24]
    return f"nexusiq:{namespace}:{tenant_id}:{fingerprint}"


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    tenant_id: str


class InMemoryCache:
    """Thread-safe TTL cache with explicit tenant invalidation."""
    def __init__(self, max_entries: int = 1000):
        self._entries: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if time.time() > entry.expires_at:
                del self._entries[key]
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int = 300, tenant_id: str = "atlascloud") -> None:
        with self._lock:
            # Evict expired entries if approaching capacity
            if len(self._entries) >= self._max_entries:
                now = time.time()
                expired = [k for k, e in self._entries.items() if now > e.expires_at]
                for k in expired:
                    del self._entries[k]
                if len(self._entries) >= self._max_entries:
                    # Evict oldest entry
                    first_key = next(iter(self._entries))
                    del self._entries[first_key]

            self._entries[key] = CacheEntry(
                value=value,
                expires_at=time.time() + ttl_seconds,
                tenant_id=tenant_id,
            )

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._entries.pop(key, None) is not None

    def invalidate_tenant(self, tenant_id: str) -> int:
        with self._lock:
            to_delete = [k for k, e in self._entries.items() if e.tenant_id == tenant_id]
            for k in to_delete:
                del self._entries[k]
            return len(to_delete)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


class NexusCache:
    """Unified cache engine with Redis support and automatic in-memory fallback."""
    def __init__(
        self,
        redis_url: Optional[str] = None,
        default_ttl_seconds: int = 300,
        enable_redis: bool = True,
    ):
        self.default_ttl = default_ttl_seconds
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.invalidations = 0
        self._lock = threading.Lock()
        self._memory = InMemoryCache()
        self._redis = None
        self._redis_available = False

        url = redis_url or os.environ.get("REDIS_URL")
        host = os.environ.get("REDIS_HOST")
        if enable_redis and (url or host):
            try:
                import redis
                if url:
                    self._redis = redis.Redis.from_url(url, socket_timeout=1.0, socket_connect_timeout=1.0)
                else:
                    port = int(os.environ.get("REDIS_PORT", "6379"))
                    self._redis = redis.Redis(host=host, port=port, socket_timeout=1.0, socket_connect_timeout=1.0)
                self._redis.ping()
                self._redis_available = True
                logger.info("Connected to Redis cache successfully.")
            except Exception as exc:
                logger.warning("Redis unavailable (%s); falling back to in-memory cache.", exc)
                self._redis_available = False

    @property
    def is_redis(self) -> bool:
        return self._redis_available

    def get(self, key: str) -> Optional[Any]:
        if self._redis_available and self._redis is not None:
            try:
                raw = self._redis.get(key)
                if raw is not None:
                    with self._lock:
                        self.hits += 1
                    return json.loads(raw)
            except Exception as exc:
                logger.warning("Redis GET failed (%s); reading from memory.", exc)

        val = self._memory.get(key)
        with self._lock:
            if val is not None:
                self.hits += 1
            else:
                self.misses += 1
        return val

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
        tenant_id: str = "atlascloud",
    ) -> bool:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        with self._lock:
            self.sets += 1

        self._memory.set(key, value, ttl_seconds=ttl, tenant_id=tenant_id)

        if self._redis_available and self._redis is not None:
            try:
                serialized = json.dumps(value)
                self._redis.setex(key, ttl, serialized)
                return True
            except Exception as exc:
                logger.warning("Redis SET failed (%s); retained in memory.", exc)

        return True

    def delete(self, key: str) -> bool:
        deleted = self._memory.delete(key)
        if self._redis_available and self._redis is not None:
            try:
                self._redis.delete(key)
            except Exception:
                pass
        return deleted

    def invalidate_tenant(self, tenant_id: str) -> int:
        count = self._memory.invalidate_tenant(tenant_id)
        with self._lock:
            self.invalidations += count

        if self._redis_available and self._redis is not None:
            try:
                # Find all keys matching the tenant pattern
                pattern = f"nexusiq:*:{tenant_id}:*"
                keys = self._redis.keys(pattern)
                if keys:
                    self._redis.delete(*keys)
                    with self._lock:
                        self.invalidations += len(keys)
            except Exception as exc:
                logger.warning("Redis tenant invalidation failed (%s)", exc)

        return count

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            hit_rate = round(self.hits / total, 4) if total > 0 else 0.0
            return {
                "backend": "redis" if self._redis_available else "in_memory",
                "hits": self.hits,
                "misses": self.misses,
                "sets": self.sets,
                "invalidations": self.invalidations,
                "hit_rate": hit_rate,
                "entries_in_memory": self._memory.size(),
            }

    def clear(self) -> None:
        self._memory.clear()
        if self._redis_available and self._redis is not None:
            try:
                self._redis.flushdb()
            except Exception:
                pass
        with self._lock:
            self.hits = 0
            self.misses = 0
            self.sets = 0
            self.invalidations = 0
