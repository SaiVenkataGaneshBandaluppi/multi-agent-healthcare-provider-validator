"""
MIT License
Async NPPES CMS API client with Redis caching and retry logic.
"""
import asyncio
import json
import logging
from typing import Optional

import httpx
import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 86400  # 24 hours


class NPPESNotFoundError(Exception):
    pass


class NPPESAPIError(Exception):
    pass


class NPPESRateLimitError(Exception):
    pass


class NPPESClient:
    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self._redis = redis_client
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    def _cache_key(self, npi: str) -> str:
        return f"nppes:npi:{npi}"

    async def _get_cached(self, npi: str) -> Optional[dict]:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(self._cache_key(npi))
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis cache read failed: %s", exc)
        return None

    async def _set_cached(self, npi: str, data: dict) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.setex(
                self._cache_key(npi),
                CACHE_TTL_SECONDS,
                json.dumps(data),
            )
        except Exception as exc:
            logger.warning("Redis cache write failed: %s", exc)

    async def lookup_npi(self, npi: str) -> dict:
        cached = await self._get_cached(npi)
        if cached is not None:
            return cached

        result = await self._fetch_with_retry(npi)
        await self._set_cached(npi, result)
        return result

    async def _fetch_with_retry(self, npi: str, max_attempts: int = 3) -> dict:
        last_exc: Optional[Exception] = None
        for attempt in range(max_attempts):
            try:
                client = await self._get_http_client()
                response = await client.get(
                    settings.NPPES_BASE_URL,
                    params={"number": npi, "version": "2.1"},
                    timeout=10.0,
                )
                if response.status_code == 429:
                    raise NPPESRateLimitError("NPPES API rate limit exceeded")
                if response.status_code == 404:
                    raise NPPESNotFoundError(f"NPI {npi} not found in registry")
                if response.status_code != 200:
                    raise NPPESAPIError(
                        f"NPPES API returned status {response.status_code}"
                    )
                data = response.json()
                result_count = data.get("result_count", 0)
                if result_count == 0:
                    raise NPPESNotFoundError(f"NPI {npi} not found in registry")
                return data.get("results", [{}])[0]
            except (NPPESNotFoundError, NPPESRateLimitError):
                raise
            except NPPESAPIError:
                raise
            except Exception as exc:
                last_exc = exc
                wait_seconds = 2 ** attempt
                logger.warning(
                    "NPPES lookup attempt %d failed for NPI %s: %s. Retrying in %ds.",
                    attempt + 1, npi, exc, wait_seconds,
                )
                if attempt < max_attempts - 1:
                    await asyncio.sleep(wait_seconds)

        raise NPPESAPIError(f"NPPES API failed after {max_attempts} attempts: {last_exc}")

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()


_client_instance: Optional[NPPESClient] = None


async def get_nppes_client() -> NPPESClient:
    global _client_instance
    if _client_instance is None:
        try:
            redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            _client_instance = NPPESClient(redis_client=redis_client)
        except Exception:
            _client_instance = NPPESClient(redis_client=None)
    return _client_instance
