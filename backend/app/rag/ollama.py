
import json
import os
import re
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


class OllamaError(RuntimeError):
    pass


class OllamaUnavailableError(OllamaError):
    pass


class OllamaTimeoutError(OllamaError):
    pass


class OllamaResponseError(OllamaError):
    pass


DEFAULT_NUM_CTX = 8192
DEFAULT_KEEP_ALIVE = "30m"


@dataclass(frozen=True)
class OllamaSettings:
    base_url: str
    model: str
    timeout: float
    # Ollama otherwise sizes the KV cache from the model's maximum context
    # (131072 for llama3.1), which pushes the model into CPU memory and drops
    # generation to a few tokens per second.  Matching prompts fit well inside
    # 8192 tokens, so an explicit window keeps the model fully on the GPU.
    num_ctx: int = DEFAULT_NUM_CTX
    keep_alive: str = DEFAULT_KEEP_ALIVE


def load_ollama_settings() -> OllamaSettings:
    raw_timeout = os.getenv("OLLAMA_TIMEOUT", "120").strip()
    try:
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise ValueError("OLLAMA_TIMEOUT must be a number.") from exc
    if timeout <= 0:
        raise ValueError("OLLAMA_TIMEOUT must be greater than zero.")
    raw_num_ctx = os.getenv("OLLAMA_NUM_CTX", str(DEFAULT_NUM_CTX)).strip()
    try:
        num_ctx = int(raw_num_ctx)
    except ValueError as exc:
        raise ValueError("OLLAMA_NUM_CTX must be an integer.") from exc
    if num_ctx <= 0:
        raise ValueError("OLLAMA_NUM_CTX must be greater than zero.")
    return OllamaSettings(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip().rstrip("/"),
        model=os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip() or "llama3.1:8b",
        timeout=timeout,
        num_ctx=num_ctx,
        keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", DEFAULT_KEEP_ALIVE).strip()
        or DEFAULT_KEEP_ALIVE,
    )


def _extract_json(content: str) -> Any:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(text[start : end + 1])


class OllamaClient:
    def __init__(self, settings: OllamaSettings | None = None) -> None:
        self.settings = settings or load_ollama_settings()

    async def complete_structured(
        self, model_cls: type[ModelT], system_prompt: str, user_prompt: str
    ) -> ModelT:
        schema = model_cls.model_json_schema()
        prompt = (
            f"{user_prompt}\n\nReturn one JSON object with actual matching values, "
            "not a JSON Schema and never a '$schema' key. It must match:\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )
        for attempt in range(2):
            payload = {
                "model": self.settings.model,
                "stream": False,
                # Keep the model resident between page visits instead of paying
                # a multi-second cold load for every match.
                "keep_alive": self.settings.keep_alive,
                # Older Ollama versions cannot compile every Pydantic JSON Schema
                # grammar. JSON mode remains local and is followed by strict
                # Pydantic validation below.
                "format": "json",
                "options": {
                    "temperature": 0,
                    "num_ctx": self.settings.num_ctx,
                },
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            }
            try:
                async with httpx.AsyncClient(timeout=self.settings.timeout) as client:
                    response = await client.post(f"{self.settings.base_url}/api/chat", json=payload)
            except httpx.TimeoutException as exc:
                raise OllamaTimeoutError("Ollama timed out. Please retry.") from exc
            except httpx.HTTPError as exc:
                raise OllamaUnavailableError("Ollama is unavailable. Start Ollama and retry.") from exc

            if response.status_code >= 500:
                raise OllamaUnavailableError("Ollama is unavailable. Start Ollama and retry.")
            if response.status_code >= 400:
                raise OllamaResponseError("Ollama rejected the matching request.")
            try:
                content = response.json()["message"]["content"]
                parsed = _extract_json(content)
                if model_cls.__name__ in {"MatchResult", "OllamaMatchResult"} and not isinstance(parsed.get("match_score"), (int, float)):
                    raise ValueError("match_score is required for matching")
                return model_cls.model_validate(parsed)
            except (KeyError, TypeError, ValueError, ValidationError):
                if attempt == 0:
                    prompt += "\nYour previous answer was invalid. Return only actual field values."

        raise OllamaResponseError("Ollama returned invalid match JSON. Please retry.")


_ollama_client: OllamaClient | None = None


def get_ollama_client() -> OllamaClient:
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client


def reset_ollama_client() -> None:
    global _ollama_client
    _ollama_client = None
