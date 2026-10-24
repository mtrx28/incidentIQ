"""LLM clients. INCIDENTIQ_LLM selects replay (default), live or mock."""

from incidentiq.config import load_config
from incidentiq.llm.base import CacheMiss, LLMClient, LLMOutputError, Message
from incidentiq.llm.cache import ResponseCache
from incidentiq.llm.live import LiveLLM, QuotaExhausted, openai_transport
from incidentiq.llm.mock import MockLLM
from incidentiq.llm.replay import ReplayLLM

__all__ = ["CacheMiss", "LLMClient", "LLMOutputError", "LiveLLM", "Message", "MockLLM",
           "QuotaExhausted", "ReplayLLM", "get_llm"]


def get_llm(mode: str | None = None) -> LLMClient:
    cfg = load_config()
    mode = mode or cfg.llm_mode
    if mode == "replay":
        return ReplayLLM(cfg.llm_model)
    if mode == "live":
        return LiveLLM(cfg.llm_model, openai_transport(cfg), ResponseCache(),
                       min_interval_s=cfg.llm_min_interval_s)
    if mode == "mock":
        return MockLLM()
    raise ValueError(f"unknown LLM mode {mode!r}")
