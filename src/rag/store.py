"""Vector store: embeddings in a NumPy matrix, cosine similarity, category filter,
relevance threshold (FR14). Persisted to disk (vectors.npy + chunks.json).

Why not Chroma/FAISS: ~1-2k chunks fit in memory and exact cosine search takes
milliseconds; NumPy avoids native-wheel issues across Python versions. The interface
(build/search) is small, so swapping in Chroma or FAISS later is a one-file change."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import numpy as np

Embedder = Callable[[list[str]], list[list[float]]]


class VectorStore:
    def __init__(self, chunks: list[dict], vectors: np.ndarray):
        self.chunks = chunks
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        self.vectors = vectors / np.where(norms == 0, 1, norms)

    @classmethod
    def build(cls, chunks: list[dict], embed: Embedder, batch: int = 64) -> "VectorStore":
        vecs: list[list[float]] = []
        for i in range(0, len(chunks), batch):
            vecs.extend(embed([c["text"] for c in chunks[i:i + batch]]))
        return cls(chunks, np.array(vecs, dtype=np.float32))

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self.vectors)
        (directory / "chunks.json").write_text(json.dumps(self.chunks), encoding="utf-8")

    @classmethod
    def load(cls, directory: Path) -> "VectorStore | None":
        v, c = directory / "vectors.npy", directory / "chunks.json"
        if not (v.exists() and c.exists()):
            return None
        return cls(json.loads(c.read_text(encoding="utf-8")), np.load(v))

    def search(self, query_vec: list[float], k: int = 4, category: str | None = None,
               min_score: float = 0.0) -> list[dict]:
        q = np.asarray(query_vec, dtype=np.float32)
        q = q / (np.linalg.norm(q) or 1)
        scores = self.vectors @ q
        idx = np.argsort(-scores)
        out = []
        for i in idx:
            c = self.chunks[int(i)]
            if category and c["category"] != category:
                continue
            s = float(scores[int(i)])
            if s < min_score:
                break
            out.append({**c, "score": round(s, 3)})
            if len(out) >= k:
                break
        return out
