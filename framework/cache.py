from __future__ import annotations
import collections
import hashlib
import json
import threading
import time
import logging
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger(__name__)


class ParamCache:
    """Memoization cache: same parameters → cached result.

    Results are cached based on a hash of the input parameters.
    Supports TTL (time-to-live) for automatic expiration.
    """

    def __init__(self, ttl: Optional[float] = None, max_size: int = 1000) -> None:
        self._ttl = ttl
        self._max_size = max_size
        self._cache: collections.OrderedDict[str, Tuple[Any, float]] = (
            collections.OrderedDict()
        )
        self._lock = threading.Lock()
        self._hits: int = 0
        self._misses: int = 0

    def get(self, params: Dict[str, Any]) -> Optional[Any]:
        key = self._make_key(params)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            result, timestamp = entry
            if self._ttl is not None and (time.time() - timestamp) > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None
            self._cache.move_to_end(key)
            self._hits += 1
            return result

    def set(self, params: Dict[str, Any], result: Any) -> None:
        key = self._make_key(params)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self._max_size:
                oldest_key, _ = self._cache.popitem(last=False)
                log.debug("ParamCache: evicted oldest entry '%s'", oldest_key[:16])
            self._cache[key] = (result, time.time())

    def invalidate(self, params: Dict[str, Any]) -> bool:
        key = self._make_key(params)
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "size": len(self._cache),
                "max_size": self._max_size,
            }

    def _make_key(self, params: Dict[str, Any]) -> str:
        try:
            serialized = json.dumps(params, sort_keys=True, default=str)
        except (TypeError, ValueError):
            log.warning("ParamCache: unserializable params, falling back to repr()")
            serialized = repr(params)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
