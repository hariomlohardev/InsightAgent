import os
import time
import hashlib
import json
from typing import Optional, Any

REDIS_URL = os.getenv("REDIS_URL")
CACHE_TTL = int(os.getenv("CACHE_TTL", "60"))

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not REDIS_URL:
        return None
    try:
        import redis

        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        # ping
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


# In-memory LRU fallback
_memory_cache = {}
_memory_times = {}


def get(key: str) -> Optional[Any]:
    r = _get_redis()
    if r:
        try:
            val = r.get(key)
            if val is not None:
                try:
                    return json.loads(val)
                except:
                    return val
            return None
        except:
            pass
    # memory fallback
    if key in _memory_cache:
        ts, ttl, val = _memory_times.get(key, (0, 0, None))
        if time.time() - ts < ttl:
            return val
        else:
            _memory_cache.pop(key, None)
            _memory_times.pop(key, None)
    return None


def set(key: str, value: Any, ttl: int = None):
    if ttl is None:
        ttl = CACHE_TTL
    r = _get_redis()
    if r:
        try:
            # json serialize
            try:
                s = json.dumps(value)
            except:
                s = json.dumps(str(value))
            r.setex(key, ttl, s)
            return
        except:
            pass
    # memory
    _memory_cache[key] = value
    _memory_times[key] = (time.time(), ttl, value)
    # cap memory to 1000 keys LRU-ish: evict oldest if >1000
    if len(_memory_cache) > 1000:
        oldest = min(_memory_times.items(), key=lambda x: x[1][0])
        _memory_cache.pop(oldest[0], None)
        _memory_times.pop(oldest[0], None)


def clear_prefix(prefix: str):
    r = _get_redis()
    if r:
        try:
            for k in r.scan_iter(match=prefix + "*"):
                r.delete(k)
        except:
            pass
    # memory
    for k in list(_memory_cache.keys()):
        if k.startswith(prefix):
            _memory_cache.pop(k, None)
            _memory_times.pop(k, None)


def cache_key(*parts) -> str:
    # hash long parts
    raw = "|".join(str(p) for p in parts)
    if len(raw) > 120:
        h = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return parts[0] + ":" + h if parts else h
    return raw
