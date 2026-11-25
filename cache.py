import time
import asyncio
from typing import Any, Optional, Dict

class InMemoryCache:

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self.hits: int = 0
        self.misses: int = 0

    async def get(self, key: str) -> Optional[Any]:

        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None

            now = time.time()
            if entry["expires_at"] and now > entry["expires_at"]:

                del self._store[key]
                self.misses += 1
                return None

            self.hits += 1
            return entry["value"]

    async def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        
        async with self._lock:
            expires_at = time.time() + ttl_seconds if ttl_seconds > 0 else None
            self._store[key] = {
                "value": value,
                "expires_at": expires_at,
                "created_at": time.time()
            }

    async def delete(self, key: str) -> bool:

        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def clear(self) -> None:

        async with self._lock:
            self._store.clear()

    async def cleanup_expired(self) -> int:

        async with self._lock:
            now = time.time()
            expired_keys = [k for k, v in self._store.items() if v["expires_at"] and now > v["expires_at"]]
            for k in expired_keys:
                del self._store[k]
            return len(expired_keys)

    def stats(self) -> Dict[str, Any]:

        total_requests = self.hits + self.misses
        hit_ratio = round((self.hits / total_requests * 100), 1) if total_requests > 0 else 0.0
        return {
            "cached_keys": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio_percent": hit_ratio
        }


app_cache = InMemoryCache()
