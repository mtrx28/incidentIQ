"""Split runbook markdown into one chunk per section. Pure Python: no database or model needed."""

import re
from dataclasses import dataclass
from pathlib import Path

from incidentiq.config import DATA_DIR

_TITLE = re.compile(r"^# Runbook (\d+): (.+)$", re.MULTILINE)
_SECTION = re.compile(r"^## (\d+)\. (.+)\n\n(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    runbook_id: int
    section_id: str  # evidence ID, e.g. R-02-5
    title: str
    heading: str
    text: str

    @property
    def embed_text(self) -> str:
        """Title and heading are prepended so a short section keeps its context."""
        return f"{self.title} - {self.heading}: {self.text}"


def chunk_runbook(markdown: str) -> list[Chunk]:
    title_match = _TITLE.search(markdown)
    if not title_match:
        raise ValueError("runbook has no '# Runbook NN: title' line")
    number, title = int(title_match.group(1)), title_match.group(2)
    return [
        Chunk(number, f"R-{number:02d}-{int(n)}", title, heading, body.strip())
        for n, heading, body in _SECTION.findall(markdown)
    ]


def chunk_directory(directory: Path | None = None) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted((directory or DATA_DIR / "runbooks").glob("*.md")):
        chunks += chunk_runbook(path.read_text(encoding="utf-8"))
    return chunks
