"""Live mode: call a real model through any OpenAI-compatible endpoint and record the reply.

Cache first: a request that was already recorded is answered from disk without an API call, so a
benchmark run that hits the free tier's daily limit can simply be rerun the next day and continues
where it stopped. Calls are spaced out to stay under the per-minute limit.
"""

import time
from collections.abc import Callable

from incidentiq.config import Config
from incidentiq.llm.base import Generation, LLMClient, Message
from incidentiq.llm.cache import ResponseCache, cache_key
from incidentiq.redaction import Redactor, redact

Transport = Callable[[list[Message], bool], Generation]


class RateLimited(Exception):
    """Raised by a transport on a rate-limit or transient server error."""

    def __init__(self, message: str, daily: bool = False, retry_after: float | None = None):
        super().__init__(message)
        self.daily = daily
        self.retry_after = retry_after


class QuotaExhausted(RuntimeError):
    """The provider's quota is used up. Rerun later: everything recorded so far is kept."""


def openai_transport(cfg: Config) -> Transport:
    """Transport for OpenAI-compatible APIs (Gemini, Groq, Ollama, ...)."""
    if not cfg.llm_api_key:
        raise RuntimeError("live mode needs LLM_API_KEY (and LLM_BASE_URL); see .env.example")
    import openai  # imported here so replay and mock never need the SDK

    client = openai.OpenAI(base_url=cfg.llm_base_url or None, api_key=cfg.llm_api_key)
    transient = (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError,
                 openai.InternalServerError)

    def call(messages: list[Message], json_mode: bool) -> Generation:
        extra = {"response_format": {"type": "json_object"}} if json_mode else {}
        started = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=cfg.llm_model, messages=messages, temperature=0, **extra)
        except transient as exc:
            text = str(exc).lower()
            headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
            retry_after = headers.get("retry-after")
            raise RateLimited(
                str(exc), daily=any(w in text for w in ("perday", "per day", "daily")),
                retry_after=float(retry_after) if retry_after else None) from exc
        usage = response.usage
        return Generation(
            response.choices[0].message.content or "",
            usage.prompt_tokens if usage else 0, usage.completion_tokens if usage else 0,
            time.monotonic() - started)

    return call


class LiveLLM(LLMClient):
    def __init__(self, model: str, transport: Transport, cache: ResponseCache | None = None,
                 min_interval_s: float = 4.0, max_retries: int = 5,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, redactor: Redactor | None = None):
        super().__init__(redactor)
        self.model = model
        self.transport = transport
        self.cache = cache or ResponseCache()
        self.min_interval_s = min_interval_s
        self.max_retries = max_retries
        self._sleep, self._clock = sleep, clock
        self._last_call: float | None = None

    def _throttle(self) -> None:
        if self._last_call is not None:
            wait = self.min_interval_s - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def _call(self, messages: list[Message], json_mode: bool) -> Generation:
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                return self.transport(messages, json_mode)
            except RateLimited as exc:
                if exc.daily:
                    raise QuotaExhausted(
                        "Daily quota reached. Rerun tomorrow: replies recorded so far are cached "
                        "and will not be requested again.") from exc
                if attempt == self.max_retries:
                    raise QuotaExhausted(
                        f"Still rate limited after {self.max_retries} retries: {exc}") from exc
                self._sleep(exc.retry_after or min(10 * 2 ** attempt, 120))
        raise AssertionError("unreachable")

    def generate(self, messages: list[Message], schema_name: str | None) -> Generation:
        key = cache_key(self.model, messages, schema_name)
        cached = self.cache.get(key)
        if cached:
            return cached
        reply = self._call(messages, json_mode=schema_name is not None)
        # Record the redacted text, so the committed cache can never hold PII or secrets.
        reply = Generation(redact(reply.text)[0], reply.prompt_tokens, reply.completion_tokens,
                           reply.latency_s)
        self.cache.put(key, self.model, messages, schema_name, reply)
        return reply
