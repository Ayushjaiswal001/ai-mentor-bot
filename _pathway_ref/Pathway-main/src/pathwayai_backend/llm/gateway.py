import time
from dataclasses import dataclass

import structlog
from huggingface_hub import AsyncInferenceClient
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from tenacity import retry, stop_after_attempt, wait_exponential

from pathwayai_backend.config import Settings

logger = structlog.get_logger(__name__)


class ModelUnavailableError(RuntimeError):
    """Raised when all configured model providers fail."""


@dataclass(frozen=True)
class ModelResult:
    content: str
    provider: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ModelGateway:
    def __init__(self, settings: Settings, *, call_logger=None) -> None:
        self.settings = settings
        self._call_logger = call_logger

    def set_call_logger(self, call_logger) -> None:
        self._call_logger = call_logger

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback: str | None = None,
        json_mode: bool = False,
    ) -> ModelResult:
        errors: list[str] = []
        for provider in self.settings.model_provider_order:
            started = time.monotonic()
            try:
                if provider == "groq":
                    result = await self._generate_groq(
                        system_prompt, user_prompt, json_mode=json_mode
                    )
                elif provider == "huggingface":
                    result = await self._generate_huggingface(
                        system_prompt, user_prompt, json_mode=json_mode
                    )
                else:
                    continue
            except Exception as exc:
                errors.append(f"{provider}: {type(exc).__name__}")
                logger.warning(
                    "model_provider_failed", provider=provider, exc_info=True
                )
                await self._record_call(
                    provider=provider,
                    model=self._provider_model(provider),
                    success=False,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    error=f"{type(exc).__name__}: {exc}",
                )
                continue
            await self._record_call(
                provider=result.provider,
                model=result.model,
                success=True,
                latency_ms=int((time.monotonic() - started) * 1000),
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )
            return result

        if fallback is not None:
            return ModelResult(
                content=fallback,
                provider="deterministic-fallback",
                model="none",
            )
        raise ModelUnavailableError(
            "No model provider succeeded"
            + (f" ({', '.join(errors)})" if errors else "; configure model credentials")
        )

    def _provider_model(self, provider: str) -> str:
        if provider == "groq":
            return self.settings.groq_model
        if provider == "huggingface":
            return self.settings.huggingface_model
        return "unknown"

    async def _record_call(self, **kwargs) -> None:
        if self._call_logger is None:
            return
        try:
            await self._call_logger(**kwargs)
        except Exception:
            logger.warning("model_call_log_failed", exc_info=True)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4))
    async def _generate_groq(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
    ) -> ModelResult:
        assert self.settings.groq_api_key is not None
        kwargs = {}
        if json_mode:
            kwargs["model_kwargs"] = {
                "response_format": {"type": "json_object"}
            }
        model = ChatGroq(
            model=self.settings.groq_model,
            api_key=self.settings.groq_api_key,
            temperature=self.settings.model_temperature,
            max_tokens=self.settings.model_max_tokens,
            timeout=self.settings.model_timeout_seconds,
            max_retries=0,
            **kwargs,
        )
        response = await model.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        usage = getattr(response, "usage_metadata", None) or {}
        return ModelResult(
            content=str(response.content).strip(),
            provider="groq",
            model=self.settings.groq_model,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
        )

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4))
    async def _generate_huggingface(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
    ) -> ModelResult:
        assert self.settings.huggingface_api_token is not None
        client = AsyncInferenceClient(
            model=self.settings.huggingface_model,
            provider=self.settings.huggingface_provider,
            token=self.settings.huggingface_api_token.get_secret_value(),
            timeout=self.settings.model_timeout_seconds,
        )
        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = await client.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self.settings.model_max_tokens,
            temperature=self.settings.model_temperature,
            **kwargs,
        )
        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        completion_tokens = (
            getattr(usage, "completion_tokens", None) if usage else None
        )
        return ModelResult(
            content=content.strip(),
            provider="huggingface",
            model=self.settings.huggingface_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
