"""Mock mode: a deterministic rule-based stub for unit tests. No network, no cache."""

from incidentiq.llm.base import Generation, LLMClient, Message
from incidentiq.redaction import Redactor


class MockLLM(LLMClient):
    """Returns the reply of the first rule whose text appears anywhere in the conversation.

    rules: list of (substring, reply). A reply may be a string, or a list of strings that are
    returned one per call (the last one repeats), which lets a test script a bad reply followed
    by a good one. If no rule matches, `default` is returned.
    """

    def __init__(self, rules: list[tuple[str, str | list[str]]] | None = None,
                 default: str = "{}", redactor: Redactor | None = None):
        super().__init__(redactor)
        self.rules = rules or []
        self.default = default
        self._used: dict[int, int] = {}

    def generate(self, messages: list[Message], schema_name: str | None) -> Generation:
        conversation = "\n".join(m["content"] for m in messages)
        for i, (needle, reply) in enumerate(self.rules):
            if needle in conversation:
                if isinstance(reply, str):
                    return Generation(reply)
                n = self._used.get(i, 0)
                self._used[i] = n + 1
                return Generation(reply[min(n, len(reply) - 1)])
        return Generation(self.default)
