"""
MIT License
Async Groq LLM client wrapper for structured provider enrichment.
"""
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class GroqClientError(Exception):
    pass


class GroqClient:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None
        self._initialize()

    def _initialize(self) -> None:
        try:
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self._api_key)
        except Exception as exc:
            logger.warning("Failed to initialize Groq client: %s", exc)
            self._client = None

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        if self._client is None:
            raise GroqClientError("Groq client not initialized")
        try:
            response = await self._client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=1000,
                temperature=0.1,
                timeout=10.0,
            )
            return response.choices[0].message.content
        except Exception as exc:
            raise GroqClientError(f"Groq API call failed: {exc}") from exc


_groq_instance: Optional[GroqClient] = None


def get_groq_client() -> Optional[GroqClient]:
    global _groq_instance
    if not settings.GROQ_API_KEY:
        return None
    if _groq_instance is None:
        _groq_instance = GroqClient(api_key=settings.GROQ_API_KEY)
    return _groq_instance
