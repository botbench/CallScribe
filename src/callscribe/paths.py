"""Filesystem locations for CallScribe state and sessions."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def expand(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def callscribe_home() -> Path:
    return expand("~/.callscribe")


def config_path() -> Path:
    return callscribe_home() / "config.toml"


def recorder_state_path() -> Path:
    return callscribe_home() / "recorder.state"


def transcribe_state_path() -> Path:
    return callscribe_home() / "transcribe.state"


def logs_dir() -> Path:
    return callscribe_home() / "logs"


def models_dir() -> Path:
    return callscribe_home() / "models"


def ensure_home() -> Path:
    home = callscribe_home()
    home.mkdir(parents=True, exist_ok=True)
    logs_dir().mkdir(parents=True, exist_ok=True)
    return home


_TITLE_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def slugify_title(title: str | None) -> str | None:
    if not title:
        return None
    slug = _TITLE_SAFE.sub("-", title.strip()).strip("-")
    return slug[:80] or None


def new_session_dir(output_dir: str | Path, title: str | None = None) -> Path:
    """Create ~/CallScribe/YYYY-MM-DD_HHMM[_title]/ (local time)."""
    root = expand(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    slug = slugify_title(title)
    name = f"{stamp}_{slug}" if slug else stamp
    path = root / name
    # Avoid collisions if two sessions start in the same minute.
    if path.exists():
        for i in range(2, 100):
            candidate = root / f"{name}_{i}"
            if not candidate.exists():
                path = candidate
                break
    path.mkdir(parents=True, exist_ok=False)
    return path
