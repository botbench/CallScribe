"""Load Hugging Face token without printing it.

Never persist the token into ``~/.callscribe`` or config.toml — env or a
gitignored repo-root ``.hf_token`` only.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_hf_token() -> str | None:
    """Prefer ``HF_TOKEN`` / ``HUGGING_FACE_HUB_TOKEN``, else repo ``.hf_token``."""
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        val = os.environ.get(key, "").strip()
        if val:
            return val

    # Walk parents from this package file to find a checkout-root `.hf_token`.
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / ".hf_token"
        if candidate.is_file():
            token = candidate.read_text(encoding="utf-8").strip()
            if token:
                return token
        # stop at filesystem root
        if parent == parent.parent:
            break
    # Also check cwd (when run from repo)
    cwd_token = Path.cwd() / ".hf_token"
    if cwd_token.is_file():
        token = cwd_token.read_text(encoding="utf-8").strip()
        if token:
            return token
    return None
