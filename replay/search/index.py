"""FAISS index + JSON sidecar for vector storage with atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

import faiss
import numpy as np

from replay.search.embedder import EMBEDDING_DIMENSIONS


@dataclass
class ChunkMetadata:
    """Metadata for a single indexed chunk."""

    chunk_text: str
    command: str
    exit_status: int
    cwd: str
    timestamp: int
    session_id: str


@dataclass
class SearchResult:
    """A single search result with similarity score."""

    score: float
    metadata: ChunkMetadata

    @property
    def score_pct(self) -> int:
        """Score as a percentage (0-100)."""
        return max(0, min(100, int(self.score * 100)))


class SearchIndex:
    """Manages a FAISS index with JSON sidecar for metadata persistence."""

    def __init__(self, index_dir: Path):
        self.index_dir = index_dir
        self.index_path = index_dir / "vectors.faiss"
        self.sidecar_path = index_dir / "metadata.json"
        self.index: Optional[faiss.IndexFlatIP] = None
        self.metadata: List[ChunkMetadata] = []
        self._loaded = False

    def exists(self) -> bool:
        """Check if index files exist on disk."""
        return self.index_path.exists() and self.sidecar_path.exists()

    def load(self) -> None:
        """Load index and sidecar from disk.

        Raises:
            FileNotFoundError: If index files don't exist.
        """
        if not self.exists():
            raise FileNotFoundError(
                f"No index found at {self.index_dir}\n"
                "Run `replay init` to build the index."
            )

        self.index = faiss.read_index(str(self.index_path))
        with open(self.sidecar_path, "r") as f:
            data = json.load(f)
        self.metadata = [ChunkMetadata(**item) for item in data["chunks"]]
        self._loaded = True

    def build(self, embeddings: List[List[float]], metadata: List[ChunkMetadata]) -> None:
        """Build a new index from embeddings and metadata.

        Args:
            embeddings: List of embedding vectors.
            metadata: Corresponding metadata for each embedding.
        """
        if len(embeddings) != len(metadata):
            raise ValueError(
                f"Embeddings ({len(embeddings)}) and metadata ({len(metadata)}) count mismatch"
            )

        if not embeddings:
            raise ValueError("Cannot build index from empty embeddings")

        vectors = np.array(embeddings, dtype=np.float32)
        # Normalize for cosine similarity via inner product
        faiss.normalize_L2(vectors)

        self.index = faiss.IndexFlatIP(EMBEDDING_DIMENSIONS)
        self.index.add(vectors)
        self.metadata = list(metadata)
        self._loaded = True

    def add(self, embeddings: List[List[float]], metadata: List[ChunkMetadata]) -> int:
        """Add new embeddings to an existing index.

        Args:
            embeddings: New embedding vectors to add.
            metadata: Corresponding metadata.

        Returns:
            Total number of vectors in the index after adding.

        Raises:
            RuntimeError: If the index hasn't been loaded or built yet.
        """
        if self.index is None:
            raise RuntimeError("Index not loaded. Call load() or build() first.")

        if not embeddings:
            return self.index.ntotal

        vectors = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(vectors)
        self.index.add(vectors)
        self.metadata.extend(metadata)
        return self.index.ntotal

    def search(self, query_vector: List[float], top_k: int = 5) -> List[SearchResult]:
        """Search the index for similar vectors.

        Args:
            query_vector: The query embedding vector.
            top_k: Number of top results to return.

        Returns:
            List of SearchResult objects sorted by score (highest first).

        Raises:
            RuntimeError: If the index hasn't been loaded or built yet.
        """
        if self.index is None or self.index.ntotal == 0:
            return []

        query = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(query)

        k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue
            results.append(
                SearchResult(
                    score=float(max(0.0, score)),  # Clamp negative scores
                    metadata=self.metadata[idx],
                )
            )

        return results

    def save(self) -> None:
        """Atomically save index and sidecar to disk.

        Uses temp file + rename to prevent corruption on crash.
        """
        if self.index is None:
            raise RuntimeError("No index to save. Call build() first.")

        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Atomic write: FAISS index
        fd, tmp_index = tempfile.mkstemp(
            dir=self.index_dir, suffix=".faiss.tmp"
        )
        os.close(fd)
        try:
            faiss.write_index(self.index, tmp_index)
            os.replace(tmp_index, str(self.index_path))
        except Exception:
            if os.path.exists(tmp_index):
                os.unlink(tmp_index)
            raise

        # Atomic write: JSON sidecar
        fd, tmp_sidecar = tempfile.mkstemp(
            dir=self.index_dir, suffix=".json.tmp"
        )
        os.close(fd)
        try:
            data = {
                "version": 1,
                "embedding_model": "jina-embeddings-v3",
                "embedding_dimensions": EMBEDDING_DIMENSIONS,
                "total_chunks": len(self.metadata),
                "chunks": [asdict(m) for m in self.metadata],
            }
            with open(tmp_sidecar, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_sidecar, str(self.sidecar_path))
        except Exception:
            if os.path.exists(tmp_sidecar):
                os.unlink(tmp_sidecar)
            raise

    def clear(self) -> None:
        """Remove index files from disk."""
        if self.index_path.exists():
            self.index_path.unlink()
        if self.sidecar_path.exists():
            self.sidecar_path.unlink()
        self.index = None
        self.metadata = []
        self._loaded = False

    @property
    def total_chunks(self) -> int:
        """Total number of indexed chunks."""
        if self.index is None:
            return 0
        return self.index.ntotal
