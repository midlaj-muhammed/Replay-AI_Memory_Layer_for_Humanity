"""Configuration loading for Replay."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG_PATH = Path.home() / ".replay" / "config.toml"
DEFAULT_INDEX_PATH = Path.home() / ".replay" / "index"


@dataclass
class ReplayConfig:
    """Configuration for Replay."""

    openai_api_key: str = ""
    openai_base_url: Optional[str] = None
    index_path: Path = field(default_factory=lambda: DEFAULT_INDEX_PATH)
    embedding_model: str = "jina-embeddings-v3"
    atuin_db_path: Optional[Path] = None  # None = use default Atuin path

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> ReplayConfig:
        """Load config from file, falling back to env vars and defaults.

        Priority: config file > environment variables > defaults.
        """
        config_path = config_path or DEFAULT_CONFIG_PATH
        config = cls()

        # Try loading from config file
        if config_path.exists():
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib  # type: ignore[no-redef]
                except ImportError:
                    tomllib = None  # type: ignore[assignment]

            if tomllib is not None:
                with open(config_path, "rb") as f:
                    data = tomllib.load(f)
                replay_data = data.get("replay", {})
                if "openai_api_key" in replay_data:
                    config.openai_api_key = replay_data["openai_api_key"]
                if "index_path" in replay_data:
                    config.index_path = Path(replay_data["index_path"])
                if "embedding_model" in replay_data:
                    config.embedding_model = replay_data["embedding_model"]

        # Fallback to environment variables
        if not config.openai_api_key:
            # Try JINA_API_KEY first (free), then OPENAI_API_KEY
            config.openai_api_key = os.environ.get("JINA_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
        if not config.openai_base_url:
            base_url = os.environ.get("OPENAI_BASE_URL", "")
            if base_url:
                config.openai_base_url = base_url

        return config

    def validate_api_key(self) -> None:
        """Raise if no API key is configured."""
        if not self.openai_api_key:
            raise ValueError(
                "No API key found.\n"
                "Set JINA_API_KEY (free, recommended) or OPENAI_API_KEY:\n"
                "  export JINA_API_KEY='your-key'  # https://jina.ai\n"
                "  export OPENAI_API_KEY='sk-...'"
            )

    def summary_lines(self) -> list[str]:
        """Return config as display-friendly lines."""
        masked_key = self.openai_api_key[:8] + "..." if self.openai_api_key else "(not set)"
        lines = [
            f"  API key:          {masked_key}",
            f"  Base URL:         {self.openai_base_url or '(default)'}",
            f"  Embedding model:  {self.embedding_model}",
            f"  Index path:       {self.index_path}",
            f"  Atuin DB path:    {self.atuin_db_path or '(default)'}",
            f"  Config file:      {DEFAULT_CONFIG_PATH}",
        ]
        return lines
