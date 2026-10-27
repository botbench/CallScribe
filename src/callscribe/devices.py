"""List and resolve ffmpeg avfoundation microphone devices."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class MicDevice:
    index: int
    name: str


_AUDIO_HEADER = re.compile(r"AVFoundation audio devices:", re.I)
_DEVICE_LINE = re.compile(r"\[(\d+)\]\s+(.+)$")


def list_microphones() -> list[MicDevice]:
    """Parse `ffmpeg -f avfoundation -list_devices true -i ""` audio section."""
    proc = subprocess.run(
        ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True,
        text=True,
        check=False,
    )
    # ffmpeg writes the device list to stderr and exits non-zero.
    text = (proc.stderr or "") + "\n" + (proc.stdout or "")
    devices: list[MicDevice] = []
    in_audio = False
    for line in text.splitlines():
        if _AUDIO_HEADER.search(line):
            in_audio = True
            continue
        if in_audio and "AVFoundation video devices" in line:
            break
        if not in_audio:
            continue
        m = _DEVICE_LINE.search(line)
        if m:
            devices.append(MicDevice(index=int(m.group(1)), name=m.group(2).strip()))
    return devices


def resolve_mic_device(spec: str) -> MicDevice:
    """Resolve config mic_device ('default', index, or name substring) to a device."""
    devices = list_microphones()
    if not devices:
        raise RuntimeError(
            "No avfoundation audio input devices found. Is ffmpeg installed?"
        )

    spec = spec.strip()
    if spec.lower() in {"default", ""}:
        return devices[0]

    if spec.isdigit():
        idx = int(spec)
        for d in devices:
            if d.index == idx:
                return d
        raise RuntimeError(
            f"No microphone with index {idx}. Run `callscribe devices`."
        )

    # Prefer exact (case-insensitive), then substring.
    lowered = spec.lower()
    exact = [d for d in devices if d.name.lower() == lowered]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise RuntimeError(f"Ambiguous mic name {spec!r}: {[d.name for d in exact]}")

    partial = [d for d in devices if lowered in d.name.lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise RuntimeError(
            f"Ambiguous mic name {spec!r} matches: {[d.name for d in partial]}"
        )
    raise RuntimeError(
        f"No microphone matching {spec!r}. Run `callscribe devices`."
    )
