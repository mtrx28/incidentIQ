"""Replay mode: answer from recorded responses only. No network, no API key."""

from incidentiq.llm.base import CacheMiss, Generation, LLMClient, Message
from incidentiq.llm.cache import ResponseCache, cache_key
from incidentiq.redaction import Redactor


class ReplayLLM(LLMClient):
    def __init__(self, model: str, cache: ResponseCache | None = None,
                 redactor: Redactor | None = None):
        super().__init__(redactor)
        self.model = model
        self.cache = cache or ResponseCache()

    def generate(self, messages: list[Message], schema_name: str | None) -> Generation:
        key = cache_key(self.model, messages, schema_name)
        reply = self.cache.get(key)
        if reply is None:
            last = messages[-1]["content"].replace("\n", " ")[:120]
            raise CacheMiss(
                f"No recorded response for this request (key {key[:12]}, model {self.model}, "
                f"last message: {last!r}). Replay mode only serves recorded answers. To record it, "
                f"set INCIDENTIQ_LLM=live and LLM_API_KEY, and rerun; the answer is saved to "
                f"{self.cache.directory} for later offline replay.")
        return reply
