"""Shared HTTP helper with retry and rate-limit handling.

Every source module calls `request()` rather than `requests.get()` directly so
that retry / backoff / caching behavior is consistent across APIs.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import requests

from src import cache

_SESSION = requests.Session()


def request(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    cache_key: Optional[str] = None,
    cache_ttl: int = 3600,  # 1 hour default
    max_retries: int = 3,
    base_sleep: float = 2.0,
) -> Any:
    """GET `url` with retry on 429/5xx and optional on-disk caching.

    Returns parsed JSON (dict or list). Raises RuntimeError on final failure.
    """
    if cache_key is not None:
        cached = cache.get(cache_key, ttl_seconds=cache_ttl)
        if cached is not None:
            return cached

    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            resp = _SESSION.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code == 429:
                sleep = base_sleep * (2 ** attempt)
                time.sleep(sleep)
                continue
            resp.raise_for_status()
            # Some free endpoints return HTML error pages with 200 status
            # (e.g. DeFiLlama's "Upgrade to paid"). Guard against that.
            text = resp.text
            if text.startswith("Upgrade"):
                raise RuntimeError(f"Endpoint paywalled: {url}\n{text[:200]}")
            data = resp.json()
        except requests.HTTPError as e:
            last_error = e
            if resp.status_code >= 500 and attempt < max_retries - 1:
                time.sleep(base_sleep * (2 ** attempt))
                continue
            raise RuntimeError(f"HTTP {resp.status_code} from {url}: {resp.text[:200]}") from e
        except requests.RequestException as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(base_sleep * (2 ** attempt))
                continue
            raise RuntimeError(f"Request failed for {url}: {e}") from e
        else:
            if cache_key is not None:
                cache.set(cache_key, data)
            return data

    raise RuntimeError(f"Exhausted retries for {url}: {last_error}")
