"""Spawn detached transcription jobs (``callscribe _transcribe``).

Only one transcription at a time (``transcribe.state``). Logs go to
``session/transcribe.log``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from callscribe.state import (
    TranscribeState,
    get_live_transcribe,
    write_transcribe_state,
)


def spawn_detached_transcribe(session_dir: Path) -> int:
    """Start `callscribe _transcribe` detached. Raises if one is already running."""
    live = get_live_transcribe()
    if live:
        raise RuntimeError(
            f"Transcription already running (pid {live.pid}): {live.session_dir}"
        )

    callscribe_bin = shutil.which("callscribe")
    if callscribe_bin:
        cmd = [callscribe_bin, "_transcribe", str(session_dir)]
    else:
        cmd = [sys.executable, "-m", "callscribe", "_transcribe", str(session_dir)]

    log_path = session_dir / "transcribe.log"
    log_f = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        cmd,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        cwd=str(session_dir),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    log_f.close()
    write_transcribe_state(
        TranscribeState(pid=proc.pid, session_dir=str(session_dir.resolve()))
    )
    return proc.pid
