"""Load environment settings for the scripts that run the pipeline.

Libraries only read `os.environ`; loading files is the job of the program
that runs. Two files are read, and a variable already set (in the shell, or
by the first file) is never overridden:

1. the project's `.env`: settings specific to this repository (OpenSearch
   host and index, cache folder);
2. a personal file shared by the P-Data projects, outside any repository:
   credentials of services several projects use (OpenAlex key, Infoscience
   token, LLM endpoint). Default `~/.config/p-data/credentials.env`;
   `P_DATA_CREDENTIALS_FILE` points elsewhere.

Call `load_env()` before importing `edi_pipeline.config`, which reads the
environment at import time. In production neither file exists: the
scheduler sets the variables.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_CREDENTIALS_FILE = "~/.config/p-data/credentials.env"


def credentials_file() -> Path:
    return Path(os.environ.get("P_DATA_CREDENTIALS_FILE") or DEFAULT_CREDENTIALS_FILE).expanduser()


def load_env(project_env: Path | str = ".env") -> None:
    """Load the project's `.env`, then the shared credentials file; missing files are skipped."""
    load_dotenv(Path(project_env))
    load_dotenv(credentials_file())
