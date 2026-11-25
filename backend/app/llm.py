"""LiteLLM gateway: key pool with ordered failover and built-in response cache."""
import logging
from dataclasses import dataclass

import litellm
from litellm import Cache

from .config import settings

log = logging.getLogger("llm")
litellm.suppress_debug_info = True
litellm.set_verbose = False


class AllProvidersUnavailable(Exception):
    pass


class SimulatedProviderError(Exception):
    def __init__(self, status: int):
        super().__init__(f"simulated provider status {status}")
        self.status_code = status


@dataclass
class LLMResult:
    reply: str
    cached: bool
    model: str
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int


def setup_cache() -> None:
    if settings.cache_type == "disk":
        litellm.cache = Cache(type="disk", disk_cache_dir=settings.cache_dir)
    else:
        litellm.cache = Cache(type="local")


def cache_enabled() -> bool:
    return litellm.cache is not None


def parse_simulation(header: str | None) -> dict[str, int]:
    """'key_1=429,key_2=500' or '*=429' -> {'key_1': 429, ...}. Ignores bad pairs."""
    if not header or not settings.simulation_enabled:
        return {}
    out: dict[str, int] = {}
    for part in header.split(","):
        name, _, status = part.strip().partition("=")
        try:
            code = int(status)
        except ValueError:
            continue
        if name and code in (429, 500, 502, 503):
            out[name.strip()] = code
    return out


def generate(messages: list[dict], simulate: dict[str, int] | None = None) -> LLMResult:
    simulate = simulate or {}
    attempts = 0
    for idx, api_key in enumerate(settings.keys, start=1):
        key_id = f"key_{idx}"
        status = simulate.get(key_id, simulate.get("*"))
        try:
            if status:
                raise SimulatedProviderError(status)
            extra = {}
            if settings.mock_llm:
                extra["mock_response"] = "Mock reply to: " + messages[-1]["content"]
            resp = litellm.completion(
                model=settings.model,
                messages=messages,
                api_key=api_key,
                caching=True,
                num_retries=0,
                timeout=30,
                **extra,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                raise ValueError("empty completion")
        except Exception as exc:  # any provider failure -> next key (never log the key)
            attempts += 1
            log.warning("%s failed (%s): %s", key_id, getattr(exc, "status_code", "-"), type(exc).__name__)
            continue

        cached = bool((getattr(resp, "_hidden_params", None) or {}).get("cache_hit"))
        usage = getattr(resp, "usage", None)
        return LLMResult(
            reply=text,
            cached=cached,
            model=settings.model,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            key_id=None if cached else key_id,
            fallback_attempts=0 if cached else attempts,
        )
    raise AllProvidersUnavailable()
