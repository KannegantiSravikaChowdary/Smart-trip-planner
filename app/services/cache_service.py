import collections
import hashlib
import json
import os
import time
from typing import Any, Callable, Optional


class SimpleCache:
    """
    A lightweight file-based cache for storing API responses.
    Default expiry is 24 hours.
    """

    def __init__(self, cache_dir: str = "instance/cache", default_expiry: int = 86400):
        self.cache_dir = cache_dir
        self.default_expiry = default_expiry
        os.makedirs(self.cache_dir, exist_ok=True)
        # In-memory secondary cache for extreme speed within the same process
        self._memory_cache = {}

    def _get_cache_path(self, key: str) -> str:
        hashed_key = hashlib.md5(key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{hashed_key}.json")

    def get(self, key: str) -> Optional[Any]:
        # Try memory first
        if key in self._memory_cache:
            val, expiry = self._memory_cache[key]
            if expiry > time.time():
                return val

        # Try disk
        path = self._get_cache_path(key)
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                val = data.get("value")
                expiry = data.get("expiry")
                if expiry and expiry > time.time():
                    # Update memory cache
                    self._memory_cache[key] = (val, expiry)
                    return val
                else:
                    # Expired
                    os.remove(path)
                    return None
        except (json.JSONDecodeError, IOError):
            return None

    def set(self, key: str, value: Any, expiry_seconds: Optional[int] = None):
        expiry = time.time() + (expiry_seconds or self.default_expiry)
        self._memory_cache[key] = (value, expiry)

        path = self._get_cache_path(key)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"value": value, "expiry": expiry}, f)
        except IOError:
            pass

    def memoize(self, key_prefix: str, expiry_seconds: Optional[int] = None):
        """Decorator for memoizing function results."""

        def decorator(func: Callable):
            def wrapper(*args, **kwargs):
                # Simple string representation of args for the key
                key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(kwargs)}"
                cached = self.get(key)
                if cached is not None:
                    return cached
                result = func(*args, **kwargs)
                self.set(key, result, expiry_seconds)
                return result

            return wrapper

        return decorator


# Singleton instance
api_cache = SimpleCache()
