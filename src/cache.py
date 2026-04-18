"""Simple on-disk JSON cache with TTL.

Keeps API calls cheap during development — a stale cache hit beats a rate-limit
429. Keys are SHA-1 hashes of the cache-key string, so any string works.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

from src.config import CACHE_DIR


def _cache_path(key: str) -> Path:
    digest = hashlib.sha1(key.encode()).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def get(key: str, ttl_seconds: int) -> Optional[Any]:
    """Return cached value if present and younger than ttl_seconds; else None."""
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            envelope = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    age = time.time() - envelope.get("timestamp", 0)
    if age > ttl_seconds:
        return None
    return envelope.get("value")


def set(key: str, value: Any) -> None:
    """Persist value under key with current timestamp."""
    path = _cache_path(key)
    envelope = {"timestamp": time.time(), "key": key, "value": value}
    with open(path, "w") as f:
        json.dump(envelope, f)


def clear() -> int:
    """Delete every cached entry. Returns number of files removed."""
    count = 0
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
        count += 1
    return count
