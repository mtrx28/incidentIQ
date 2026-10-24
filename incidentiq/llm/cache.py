"""On-disk record of model replies, one small JSON file per request.

The key is a hash of the model name, the (redacted) messages and the schema name, so a changed
prompt is a different key and replay never returns a stale answer for it.
"""

import hashlib
import json
from pathlib import Path

from incidentiq.config import DATA_DIR
from incidentiq.llm.base import Generation, Message

DEFAULT_DIR = DATA_DIR / "llm_cache"


def cache_key(model: str, messages: list[Message], schema_name: str | None) -> str:
    payload = json.dumps({"model": model, "messages": messages, "schema": schema_name},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or DEFAULT_DIR

    def _path(self, key: str) -> Path:
        return self.directory / key[:2] / f"{key}.json"

    def get(self, key: str) -> Generation | None:
        path = self._path(key)
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        usage = record.get("usage", {})
        return Generation(record["response"], usage.get("prompt_tokens", 0),
                          usage.get("completion_tokens", 0), usage.get("latency_s", 0.0))

    def put(self, key: str, model: str, messages: list[Message], schema_name: str | None,
            reply: Generation) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "key": key, "model": model, "schema": schema_name, "messages": messages,
            "response": reply.text,
            "usage": {"prompt_tokens": reply.prompt_tokens,
                      "completion_tokens": reply.completion_tokens,
                      "latency_s": round(reply.latency_s, 3)},
        }
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
