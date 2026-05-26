#!/usr/bin/env python3
"""Build the FAISS search index using synthetic embeddings for demo.

Generates deterministic, hash-based vectors so the search UI works
without needing an external embedding API. Results are random-ish
but the demo flow is identical to real embeddings.

Run: python scripts/seed_index.py
"""

import hashlib
import json
import struct
import sys
import time
from pathlib import Path

import faiss
import numpy as np

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from replay.capture.atuin import AtuinReader
from replay.processing.cluster import cluster_commands
from replay.processing.chunker import chunk_sessions
from replay.search.index import SearchIndex, ChunkMetadata


def text_to_vector(text: str, dim: int = 1024) -> list[float]:
    """Deterministic hash-based embedding. Same text → same vector."""
    h = hashlib.sha512(text.encode()).digest()
    # Repeat hash to fill dimensions
    raw = h * (dim // len(h) + 1)
    vec = np.array([b / 255.0 * 2 - 1 for b in raw[:dim]], dtype=np.float32)
    # Normalize
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


def main():
    print("Reading Atuin history...")
    reader = AtuinReader(None)
    commands = reader.read_history()
    sessions = cluster_commands(commands)
    chunks = chunk_sessions(sessions)
    print(f"  {len(commands)} commands → {len(chunks)} chunks")

    config_path = Path.home() / ".replay"
    config_path.mkdir(parents=True, exist_ok=True)

    index = SearchIndex(config_path / "index")
    index.clear()

    print(f"Building synthetic embeddings for {len(chunks)} chunks...")
    all_embeddings = []
    all_metadata = []
    for i, c in enumerate(chunks):
        all_embeddings.append(text_to_vector(c.chunk_text))
        all_metadata.append(
            ChunkMetadata(
                chunk_text=c.chunk_text,
                command=c.command.command,
                exit_status=c.command.exit_status,
                cwd=c.command.cwd,
                timestamp=c.command.timestamp,
                session_id=c.session_id,
            )
        )
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(chunks)}")

    index.build(all_embeddings, all_metadata)
    index.save()
    print(f"\nIndex built: {index.total_chunks} chunks from {len(commands)} commands")


if __name__ == "__main__":
    main()
