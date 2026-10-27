"""macOS user notifications via osascript."""

from __future__ import annotations

import subprocess


def notify(title: str, message: str, *, enabled: bool = True) -> None:
    if not enabled:
        return
    # Escape for AppleScript strings.
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script = (
        f'display notification "{esc(message)}" with title "{esc(title)}"'
    )
    subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
