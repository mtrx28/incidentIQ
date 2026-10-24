"""The LLM interface shared by the replay, live and mock clients.

    client.complete(messages)                      -> str
    client.complete(messages, response_schema=Cls) -> Cls instance (validated, retried on failure)

Every message is passed through the redactor before it reaches `generate`, and every reply is
redacted before it is returned. That is a second line of defence: the agent already redacts tool
output, and this makes sure nothing slips past it on the way to the model.
"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, TypedDict

from pydantic import BaseModel, ValidationError

from incidentiq.redaction import Redactor

MAX_ATTEMPTS = 3  # the first try plus two retries after a validation failure


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMOutputError(RuntimeError):
    """The model kept returning output that did not match the schema."""


class CacheMiss(RuntimeError):
    """Replay mode has no recorded response for this request."""


@dataclass
class Generation:
    """One raw model reply. Token counts and latency are as recorded when it was live."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0


@dataclass
class LLMStats:
    calls: int = 0
    retries: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    redactions: int = 0  # findings the guard had to redact in prompts or replies


def extract_json(text: str) -> str:
    """Pull the JSON object out of a reply that may be wrapped in a markdown code fence."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text.strip()


def _describe(error: ValidationError | json.JSONDecodeError) -> str:
    """A short, model-readable reason, e.g. 'was not valid JSON' or 'did not match the schema'."""
    if isinstance(error, json.JSONDecodeError):
        return f"was not valid JSON ({error.msg} at position {error.pos})."
    if any(e["type"] == "json_invalid" for e in error.errors()):
        return "was not valid JSON."
    lines = [f"- {'.'.join(str(p) for p in e['loc']) or 'root'}: {e['msg']}"
             for e in error.errors()[:10]]
    return "did not match the schema:\n" + "\n".join(lines)


class LLMClient(ABC):
    def __init__(self, redactor: Redactor | None = None):
        # Share this object with the agent's act node so placeholder numbering never collides.
        self.redactor = redactor or Redactor()
        self.stats = LLMStats()
        self.sent: list[list[Message]] = []  # the exact (redacted) prompts, for tests and audits

    def start_incident(self) -> None:
        """Fresh placeholder numbering for a new incident."""
        self.redactor = Redactor(verhoeff=self.redactor.verhoeff)

    @abstractmethod
    def generate(self, messages: list[Message], schema_name: str | None) -> Generation:
        """One model call (or cache lookup). `messages` are already redacted."""

    def _redact(self, text: str) -> str:
        clean, findings = self.redactor.redact(text)
        self.stats.redactions += len(findings)
        return clean

    def complete(self, messages: list[Message],
                 response_schema: type[BaseModel] | None = None) -> str | BaseModel:
        conversation: list[Message] = [
            {"role": m["role"], "content": self._redact(m["content"])} for m in messages]
        schema_name = response_schema.__name__ if response_schema else None
        error = ""
        for attempt in range(MAX_ATTEMPTS):
            self.sent.append(list(conversation))
            reply = self.generate(conversation, schema_name)
            self.stats.calls += 1
            self.stats.retries += attempt > 0
            self.stats.prompt_tokens += reply.prompt_tokens
            self.stats.completion_tokens += reply.completion_tokens
            self.stats.latency_s += reply.latency_s
            text = self._redact(reply.text)
            if response_schema is None:
                return text
            try:
                return response_schema.model_validate_json(extract_json(text))
            except (ValidationError, json.JSONDecodeError) as exc:
                error = _describe(exc)
                conversation = conversation + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": (
                        f"Your previous reply {error}\nReply again with only the corrected "
                        f"JSON object, with no other text.")},
                ]
        raise LLMOutputError(
            f"no valid {schema_name} after {MAX_ATTEMPTS} attempts; last error: {error}")
