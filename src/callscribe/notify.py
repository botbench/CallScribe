"""macOS user notifications via osascript (best-effort; never raises)."""

from __future__ import annotations

import subprocess


def notify(title: str, message: str, *, enabled: bool = True) -> None:
    if not enabled:
        return

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script = f'display notification "{esc(message)}" with title "{esc(title)}"'
    # Focus Assist / missing osascript must not fail recording or transcription.
    subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
