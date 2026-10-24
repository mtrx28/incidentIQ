"""Text embedders. The default is a small local sentence-transformers model (no API key)."""

from functools import lru_cache
from typing import Protocol

from incidentiq.config import load_config


class Embedder(Protocol):
    name: str  # stored in the database so two embedders are never mixed
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    def __init__(self, name: str, dim: int):
        # Imported here so the rest of the package works without the heavy dependency.
        from sentence_transformers import SentenceTransformer

        self.name = name
        self._model = SentenceTransformer(name)
        # Newer sentence-transformers renamed this method.
        get_dim = getattr(self._model, "get_embedding_dimension", None) or \
            self._model.get_sentence_embedding_dimension
        actual = get_dim()
        if actual != dim:
            raise ValueError(f"{name} produces {actual}-dim vectors but EMBEDDING_DIM={dim}")
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Normalised vectors, so cosine distance and dot product agree.
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    cfg = load_config()
    return SentenceTransformerEmbedder(cfg.embedding_model, cfg.embedding_dim)
