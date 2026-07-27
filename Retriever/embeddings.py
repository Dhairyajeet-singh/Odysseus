"""Text embedding, behind one interface — same pattern as the LLM providers.

    OpenAIEmbedder             real semantic vectors, needs OPENAI_API_KEY
    SentenceTransformerEmbedder real, local, if the package is installed
    HashingEmbedder            deterministic, offline, no deps — for tests

Why an interface rather than calling an embedding API inline: the retriever's
fusion logic (combining exact-match and semantic scores) has to be testable
without a key or a network, and swapping embedding backends must not touch the
retriever. The hashing embedder is not semantically meaningful — it exists so
the *plumbing* can be asserted offline. Real semantic quality comes from the
OpenAI or sentence-transformers backends, which is stated plainly rather than
implied by green tests.
"""

from __future__ import annotations

import hashlib
import os
import re
from abc import ABC, abstractmethod
from typing import List, Optional

import numpy as np

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.\-]*")


class Embedder(ABC):
    dim: int = 0

    @abstractmethod
    def embed(self, texts: List[str]) -> np.ndarray:
        """Return an (n, dim) L2-normalised matrix so dot product == cosine."""
        ...


def _l2_normalise(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


class HashingEmbedder(Embedder):
    """Dependency-free deterministic embedder for offline tests.

    Hashes character 3-grams and word tokens into a fixed-dimensional vector.
    This captures crude lexical overlap — enough to verify that fusion,
    ranking and thresholding behave — but it is NOT a semantic model and must
    not be mistaken for one in production.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        low = text.lower()
        tokens = _TOKEN.findall(low)
        grams = [low[i:i + 3] for i in range(max(0, len(low) - 2))]
        for feat in tokens + grams:
            h = int(hashlib.md5(feat.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0
        return v

    def embed(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return _l2_normalise(np.vstack([self._vec(t) for t in texts]))


class OpenAIEmbedder(Embedder):
    """Real semantic embeddings via OpenAI. Batches to limit round-trips."""

    def __init__(self, model: str = "text-embedding-3-small",
                 api_key: Optional[str] = None, batch_size: int = 128):
        self.model = model
        self.batch_size = batch_size
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.dim = 1536 if "small" in model else 3072
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

    def embed(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("pip install openai") from exc
        client = OpenAI(api_key=self.api_key)
        out: List[List[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = [t if t.strip() else " " for t in texts[i:i + self.batch_size]]
            resp = client.embeddings.create(model=self.model, input=batch)
            out.extend(d.embedding for d in resp.data)
        return _l2_normalise(np.array(out, dtype=np.float32))


class SentenceTransformerEmbedder(Embedder):
    """Real, local, free — if sentence-transformers is installed."""

    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("pip install sentence-transformers") from exc
        self._model = SentenceTransformer(model)
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vecs = self._model.encode(texts, convert_to_numpy=True,
                                  normalize_embeddings=True)
        return vecs.astype(np.float32)


def get_embedder(name: str = "auto") -> Embedder:
    """Factory. 'auto' prefers a real backend, falls back to the offline stub."""
    name = name.lower()
    if name == "openai":
        return OpenAIEmbedder()
    if name in ("st", "sentence-transformers", "local"):
        return SentenceTransformerEmbedder()
    if name == "hashing":
        return HashingEmbedder()
    if name == "auto":
        if os.environ.get("OPENAI_API_KEY"):
            return OpenAIEmbedder()
        try:
            return SentenceTransformerEmbedder()
        except Exception:
            return HashingEmbedder()
    raise ValueError(f"unknown embedder: {name}")
