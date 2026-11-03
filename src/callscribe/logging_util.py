"""Append-only logs under ``~/.callscribe/logs/``.

Logging must never fail the main workflow (permission / disk errors are ignored).
"""

from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path

from callscribe.paths import ensure_home, logs_dir


def _log_file() -> Path:
    ensure_home()
    day = datetime.now().strftime("%Y-%m-%d")
    return logs_dir() / f"callscribe-{day}.log"


def log_line(component: str, message: str, *, level: str = "INFO") -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} [{level}] [{component}] {message}\n"
    try:
        path = _log_file()
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        # Never fail the main workflow because logging is unavailable.
        pass


def log_exception(component: str, message: str, exc: BaseException | None = None) -> None:
    detail = message
    if exc is not None:
        detail = f"{message}: {type(exc).__name__}: {exc}"
    log_line(component, detail, level="ERROR")
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        for row in tb.strip().splitlines():
            log_line(component, row, level="ERROR")
