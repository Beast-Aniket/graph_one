import json
import logging
from typing import Any
import httpx
from graphone.config import get_settings
from graphone.services.chunking import semantic_chunks

logger = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _merge(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for key, value in incoming.items():
        if key not in existing or existing[key] in (None, "", [], {}):
            existing[key] = value
        elif isinstance(existing[key], dict) and isinstance(value, dict):
            existing[key] = _merge(existing[key], value)
    return existing


class LlmOrchestrator:
    """Grounded JSON extraction with ordered provider fallback and small semantic payloads."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.settings = get_settings()
        self.client = client or httpx.AsyncClient(timeout=self.settings.crawler_timeout_seconds)
        self.owns_client = client is None

    async def close(self) -> None:
        if self.owns_client:
            await self.client.aclose()

    async def extract(self, record_type: str, text: str) -> tuple[dict[str, Any] | None, str | None]:
        chunks = semantic_chunks(text, self.settings.llm_max_chunk_chars)
        for provider in ("gemini", "groq", "deepseek"):
            if not getattr(self.settings, f"{provider}_api_key"):
                continue
            try:
                merged: dict[str, Any] = {}
                for chunk in chunks:
                    result = await self._call_provider(provider, record_type, chunk)
                    merged = _merge(merged, result)
                if merged:
                    return merged, provider.upper()
            except ExtractionError as exc:
                logger.warning("llm_provider_failed", extra={"context": {"provider": provider, "status": exc.status_code, "message": str(exc)}})
        return None, None

    async def _call_provider(self, provider: str, record_type: str, chunk: str) -> dict[str, Any]:
        prompt = (
            f"Extract one {record_type} record as JSON from this source text. Use only explicit source facts. "
            "For missing data use null. Do not add explanation or markdown.\n\nSOURCE:\n" + chunk
        )
        if provider == "gemini":
            response = await self.client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_model}:generateContent",
                params={"key": self.settings.gemini_api_key},
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}},
            )
            self._raise_for_provider_response(response)
            data = response.json()
            payload = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        else:
            key = self.settings.groq_api_key if provider == "groq" else self.settings.deepseek_api_key
            model = self.settings.groq_model if provider == "groq" else self.settings.deepseek_model
            url = "https://api.groq.com/openai/v1/chat/completions" if provider == "groq" else "https://api.deepseek.com/chat/completions"
            response = await self.client.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
            )
            self._raise_for_provider_response(response)
            payload = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        try:
            result = json.loads(payload.removeprefix("```json").removesuffix("```").strip())
        except (TypeError, json.JSONDecodeError) as exc:
            raise ExtractionError("Provider returned malformed JSON.") from exc
        if not isinstance(result, dict):
            raise ExtractionError("Provider JSON is not an object.")
        return result

    @staticmethod
    def _raise_for_provider_response(response: httpx.Response) -> None:
        if response.status_code in {413, 429}:
            raise ExtractionError(f"Provider returned HTTP {response.status_code}.", response.status_code)
        if response.is_error:
            raise ExtractionError(f"Provider returned HTTP {response.status_code}.", response.status_code)

