"""Recorder / transcribe state files under ~/.callscribe."""

from __future__ import annotations

import json
import os
import signal
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from callscribe.paths import recorder_state_path, transcribe_state_path


@dataclass
class RecorderState:
    pid: int
    session_dir: str


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_recorder_state(path: Path | None = None) -> RecorderState | None:
    path = path or recorder_state_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return RecorderState(pid=int(data["pid"]), session_dir=str(data["session_dir"]))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def write_recorder_state(state: RecorderState, path: Path | None = None) -> None:
    path = path or recorder_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")


def clear_recorder_state(path: Path | None = None) -> None:
    path = path or recorder_state_path()
    if path.exists():
        path.unlink()


def get_live_recorder() -> RecorderState | None:
    """Return state if the recorder PID is alive; clear stale files."""
    state = read_recorder_state()
    if state is None:
        return None
    if not _pid_alive(state.pid):
        clear_recorder_state()
        return None
    return state


def signal_recorder_stop(state: RecorderState) -> None:
    os.kill(state.pid, signal.SIGTERM)


# --- transcribe concurrency (Phase 1 stub state) ---


@dataclass
class TranscribeState:
    pid: int
    session_dir: str


def get_live_transcribe() -> TranscribeState | None:
    path = transcribe_state_path()
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        state = TranscribeState(pid=int(data["pid"]), session_dir=str(data["session_dir"]))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        path.unlink(missing_ok=True)
        return None
    if not _pid_alive(state.pid):
        path.unlink(missing_ok=True)
        return None
    return state
