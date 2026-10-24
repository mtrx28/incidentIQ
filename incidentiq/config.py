"""Environment handling and constants. Everything tunable lives here."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"

load_dotenv(ROOT / ".env")

LLM_MODES = ("replay", "live", "mock")


@dataclass(frozen=True)
class Config:
    llm_mode: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    llm_min_interval_s: float
    database_url: str
    embedding_model: str
    embedding_dim: int
    max_steps: int


def load_config() -> Config:
    """Read settings from the environment on every call, so tests can override them."""
    mode = os.environ.get("INCIDENTIQ_LLM", "replay")
    if mode not in LLM_MODES:
        raise ValueError(f"INCIDENTIQ_LLM must be one of {LLM_MODES}, got {mode!r}")
    return Config(
        llm_mode=mode,
        llm_base_url=os.environ.get("LLM_BASE_URL", ""),
        llm_model=os.environ.get("LLM_MODEL", "gemini-3.5-flash-lite"),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_min_interval_s=float(os.environ.get("LLM_MIN_INTERVAL_S", "4")),
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql://incidentiq:incidentiq@localhost:5432/incidentiq"
        ),
        embedding_model=os.environ.get(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        ),
        embedding_dim=int(os.environ.get("EMBEDDING_DIM", "384")),
        max_steps=int(os.environ.get("MAX_STEPS", "8")),
    )
