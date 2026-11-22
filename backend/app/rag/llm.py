import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.audit import LLM_PROVIDER_FALLBACK, get_audit_trail
from app.core.metrics import get_metrics

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.portkey.ai/v1"
DEFAULT_MODEL = "Gemini 3 Flash"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_CONCURRENT = 3
MAX_JSON_ATTEMPTS = 3

ModelT = TypeVar("ModelT", bound=BaseModel)


def _record_metric(name: str, *args, **kwargs) -> None:
    try:
        getattr(get_metrics(), name)(*args, **kwargs)
    except Exception:
        pass


def _record_audit(event_type: str, **kwargs) -> None:
    try:
        get_audit_trail().record(event_type, **kwargs)
    except Exception:
        pass


class LLMError(RuntimeError):
    pass


class LLMNotConfiguredError(LLMError):
    pass


class LLMCredentialsError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    slug: str
    model: str
    api_key: str
    timeout: float
    max_concurrent: int
    fallback_slugs: tuple[str, ...] = ()
    config: str = ""
    fallback_models: tuple[str, ...] = ()
    use_responses: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.slug)

    @property
    def providers(self) -> tuple[str, ...]:
        return tuple(slug for slug in (self.slug, *self.fallback_slugs) if slug)

    @property
    def missing_configuration(self) -> str:
        missing = []
        if not self.api_key:
            missing.append("PORTKEY_AI_API")
        if not self.slug:
            missing.append("PORTKEY_SLUGS")
        return ", ".join(missing)


def _text_env(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc
    return value


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{name} must be a boolean value.")


def load_llm_settings() -> LLMSettings:
    slugs = [
        item.strip()
        for item in _text_env("PORTKEY_SLUGS", "").split(",")
        if item.strip()
    ]

    return LLMSettings(
        base_url=_text_env("PORTKEY_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        slug=slugs[0] if slugs else "",
        model=_text_env("PORTKEY_MODEL", DEFAULT_MODEL),
        api_key=_text_env("PORTKEY_AI_API", ""),
        timeout=_float_env("PORTKEY_TIMEOUT", DEFAULT_TIMEOUT),
        max_concurrent=_int_env("PORTKEY_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENT),
        fallback_slugs=tuple(slugs[1:]),
        config=_text_env("PORTKEY_CONFIG", ""),
        fallback_models=tuple(
            item.strip()
            for item in _text_env("PORTKEY_FALLBACK_MODELS", "").split(",")
            if item.strip()
        ),
        use_responses=_bool_env("PORTKEY_USE_RESPONSES", False),
    )


class LLMClient:
    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or load_llm_settings()
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrent)

    def _headers(self, provider_slug: str) -> dict[str, str]:
        headers = {
            "x-portkey-api-key": self.settings.api_key,
            "x-portkey-provider": f"@{provider_slug}",
            "Content-Type": "application/json",
        }
        if self.settings.config:
            headers["x-portkey-config"] = self.settings.config
        return headers

    def _payload(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        json_mode: bool,
        max_tokens: int | None = None,
        use_responses: bool = False,
        model: str | None = None,
    ) -> dict[str, Any]:
        resolved_model = model or self.settings.model
        if use_responses:
            payload: dict[str, Any] = {
                "model": resolved_model,
                "input": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
            }
            if json_mode:
                payload["text"] = {"format": {"type": "json_object"}}
            if max_tokens is not None:
                payload["max_output_tokens"] = max_tokens
            return payload

        payload = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return payload

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        json_mode: bool = False,
        max_tokens: int | None = None,
        use_responses: bool = False,
    ) -> str:
        if not self.settings.configured:
            raise LLMNotConfiguredError(
                "The AI service is not configured. Missing: "
                f"{self.settings.missing_configuration}."
            )

        call_started = time.perf_counter()
        last_error: LLMError | None = None
        try:
            providers = self.settings.providers
            for index, provider_slug in enumerate(providers):
                if index > 0:
                    _record_metric("record_llm_fallback")
                    _record_audit(
                        LLM_PROVIDER_FALLBACK,
                        detail=f"from={providers[0]} to={provider_slug}",
                    )
                use_responses_attempt = use_responses and index == 0
                endpoint = "/responses" if use_responses_attempt else "/chat/completions"
                attempt_model = (
                    self.settings.model
                    if index == 0
                    else (
                        self.settings.fallback_models[index - 1]
                        if self.settings.fallback_models
                        else self.settings.model
                    )
                )

                try:
                    async with self._semaphore:
                        async with httpx.AsyncClient(timeout=self.settings.timeout) as client:
                            response = await client.post(
                                f"{self.settings.base_url}{endpoint}",
                                headers=self._headers(provider_slug),
                                json=self._payload(
                                    system_prompt,
                                    user_prompt,
                                    temperature,
                                    json_mode,
                                    max_tokens,
                                    use_responses=use_responses_attempt,
                                    model=attempt_model,
                                ),
                            )
                except httpx.TimeoutException as exc:
                    _record_metric("record_llm_provider_failure", provider_slug, timeout=True)
                    last_error = LLMError("The AI service request timed out.")
                    last_error.__cause__ = exc
                    continue
                except httpx.HTTPError as exc:
                    _record_metric("record_llm_provider_failure", provider_slug)
                    last_error = LLMError("The AI service could not be reached.")
                    last_error.__cause__ = exc
                    continue

                logger.info(
                    "llm provider=%s model=%s status=%s",
                    provider_slug,
                    self.settings.model,
                    response.status_code,
                )

                try:
                    self._raise_for_status(response)
                except (LLMCredentialsError, LLMResponseError) as exc:
                    _record_metric("record_llm_provider_failure", provider_slug)
                    logger.warning(
                        "llm provider=%s model=%s failed status=%s error=%s",
                        provider_slug,
                        self.settings.model,
                        response.status_code,
                        str(exc),
                    )
                    raise
                except LLMError as exc:
                    _record_metric("record_llm_provider_failure", provider_slug)
                    logger.warning(
                        "llm provider=%s model=%s failed status=%s error=%s",
                        provider_slug,
                        self.settings.model,
                        response.status_code,
                        str(exc),
                    )
                    last_error = exc
                    continue

                content = self._extract_content(response, use_responses=use_responses_attempt)
                _record_metric(
                    "record_llm_success", (time.perf_counter() - call_started) * 1000
                )
                logger.info(
                    "llm provider=%s model=%s ok duration_ms=%s",
                    provider_slug,
                    self.settings.model,
                    (time.perf_counter() - call_started) * 1000,
                )
                return content

            if last_error is None:
                last_error = LLMError("The AI service is temporarily unavailable.")
            raise last_error
        except (LLMCredentialsError, LLMResponseError, LLMError):
            _record_metric(
                "record_llm_failure", (time.perf_counter() - call_started) * 1000
            )
            raise

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise LLMError("The AI service is rate limited. Please retry shortly.")
        if response.status_code in (401, 403):
            raise LLMCredentialsError(
                "The AI service credentials are invalid. "
                "Please check the AI service configuration."
            )
        if response.status_code >= 500:
            raise LLMError("The AI service is temporarily unavailable.")
        if response.status_code >= 400:
            raise LLMResponseError(
                f"The AI service rejected the request (HTTP {response.status_code})."
            )

    def _responses_text(self, data: Any) -> str | None:
        output = data.get("output") if isinstance(data, dict) else None
        if not isinstance(output, list):
            return None
        content: Any = None
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if (
                    isinstance(part, dict)
                    and part.get("type") == "output_text"
                    and isinstance(part.get("text"), str)
                ):
                    content = part.get("text")
                    break
            if content:
                break
        if not isinstance(content, str) or not content.strip():
            return None
        return content

    def _responses_stream_payload(self, response: httpx.Response) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        text = response.text or ""
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[len("data:") :].strip()
            if not payload:
                continue
            try:
                event = json.loads(payload)
            except ValueError:
                continue
            if isinstance(event, dict):
                events.append(event)
        final: Any = None
        for event in reversed(events):
            if (
                isinstance(event, dict)
                and event.get("type") == "response.completed"
                and isinstance(event.get("response"), dict)
            ):
                final = event["response"]
                break
        if final is None and events:
            final = events[-1]
        return final if isinstance(final, dict) else {}

    def _extract_content(self, response: httpx.Response, use_responses: bool = False) -> str:
        try:
            data: Any = response.json()
        except ValueError:
            data = None

        content: Any = None
        if use_responses:
            source: Any = data if data is not None else self._responses_stream_payload(response)
            content = self._responses_text(source)
            if content is None:
                raise LLMResponseError(
                    "The AI service returned an unexpected response."
                )
        else:
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMResponseError(
                    "The AI service returned an unexpected response."
                ) from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("The AI service returned an empty response.")

        return content

    async def complete_structured(
        self,
        model_cls: Type[ModelT],
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        use_responses: bool = False,
    ) -> ModelT:
        schema = json.dumps(model_cls.model_json_schema(), ensure_ascii=False)
        base_prompt = (
            f"{user_prompt}\n\nReturn only JSON that matches this schema:\n{schema}"
        )
        attempt_prompt = base_prompt

        for attempt in range(MAX_JSON_ATTEMPTS):
            content = await self.complete(
                system_prompt,
                attempt_prompt,
                temperature=temperature,
                json_mode=True,
                max_tokens=max_tokens,
                use_responses=use_responses,
            )
            try:
                parsed = _extract_json(content)
            except ValueError:
                parsed = None

            if parsed is not None:
                try:
                    return model_cls.model_validate(parsed)
                except ValidationError:
                    parsed = None

            attempt_prompt = (
                f"{base_prompt}\n\nThe previous response was not valid JSON for this "
                "schema. Return corrected JSON only, with no extra text."
            )

        raise LLMResponseError("The AI service did not return valid JSON.")


def _extract_json(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

    try:
        return json.loads(text)
    except ValueError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client

    if _llm_client is None:
        _llm_client = LLMClient()

    return _llm_client


def set_llm_client(client: LLMClient | None) -> None:
    global _llm_client
    _llm_client = client


def reset_llm_client() -> None:
    set_llm_client(None)
