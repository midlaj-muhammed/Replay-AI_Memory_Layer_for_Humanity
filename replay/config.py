"""Configuration loading for Replay."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG_PATH = Path.home() / ".replay" / "config.toml"
DEFAULT_INDEX_PATH = Path.home() / ".replay" / "index"

AVAILABLE_MODELS = {
    "jina-embeddings-v3": {"dimensions": 1024, "provider": "Jina AI (free)"},
    "text-embedding-3-small": {"dimensions": 1536, "provider": "OpenAI"},
    "text-embedding-3-large": {"dimensions": 3072, "provider": "OpenAI"},
    "text-embedding-ada-002": {"dimensions": 1536, "provider": "OpenAI (legacy)"},
}


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
                if "openai_base_url" in replay_data:
                    config.openai_base_url = replay_data["openai_base_url"]

        # Fallback to environment variables
        if not config.openai_api_key:
            jina_key = os.environ.get("JINA_API_KEY", "")
            openai_key = os.environ.get("OPENAI_API_KEY", "")
            if jina_key:
                config.openai_api_key = jina_key
            elif openai_key:
                config.openai_api_key = openai_key
                # Switch to OpenAI model/dimensions if using OpenAI key
                if config.embedding_model == "jina-embeddings-v3":
                    config.embedding_model = "text-embedding-3-small"
        if not config.openai_base_url:
            jina_key = os.environ.get("JINA_API_KEY", "")
            openai_key = os.environ.get("OPENAI_API_KEY", "")
            base_url = os.environ.get("OPENAI_BASE_URL", "")
            if jina_key:
                config.openai_base_url = None  # Embedder will use Jina URL
            elif base_url:
                config.openai_base_url = base_url
            elif openai_key:
                config.openai_base_url = None  # Use OpenAI default

        return config

    def save(self, config_path: Optional[Path] = None) -> None:
        """Save config to TOML file."""
        config_path = config_path or DEFAULT_CONFIG_PATH
        config_path.parent.mkdir(parents=True, exist_ok=True)

        lines = ["[replay]"]
        if self.openai_api_key:
            lines.append(f'openai_api_key = "{self.openai_api_key}"')
        if self.openai_base_url:
            lines.append(f'openai_base_url = "{self.openai_base_url}"')
        if self.embedding_model != "jina-embeddings-v3":
            lines.append(f'embedding_model = "{self.embedding_model}"')
        if self.index_path != DEFAULT_INDEX_PATH:
            lines.append(f'index_path = "{self.index_path}"')
        if self.atuin_db_path:
            lines.append(f'atuin_db_path = "{self.atuin_db_path}"')
        lines.append("")

        config_path.write_text("\n".join(lines))

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
