"""List and resolve ffmpeg avfoundation microphone devices."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Literal

MicClass = Literal["airpods", "bluetooth", "builtin", "usb", "unknown"]


@dataclass(frozen=True)
class MicDevice:
    index: int
    name: str


def classify_mic(name: str) -> MicClass:
    """Heuristic mic class from an avfoundation device name.

    Feeds adaptive profiles (sync tolerance / latency bias) via ``mic_profile``.
    """
    n = name.lower()
    if "airpods" in n:
        return "airpods"
    if any(k in n for k in ("bluetooth", "hands-free", "headset", "hfp", "sco")):
        return "bluetooth"
    if any(
        k in n
        for k in (
            "macbook",
            "imac",
            "built-in",
            "builtin",
            "internal",
            "microphone array",
        )
    ):
        return "builtin"
    if any(k in n for k in ("usb", "yeti", "snowball", "rode", "fifine", "hyperx")):
        return "usb"
    return "unknown"


def mic_class_tip(mic_class: MicClass) -> str | None:
    """Optional quality caveat for doctor output."""
    if mic_class == "airpods":
        return (
            "AirPods / Bluetooth headset mic: supported, but HFP/SCO may drop to "
            "~16–24 kHz and add sync skew vs wired. Prefer this over laptop speakers."
        )
    if mic_class == "bluetooth":
        return (
            "Bluetooth mic: supported without hard-block; quality and latency can be "
            "worse than wired/USB. Prefer headphones so remote audio is not re-mic'd."
        )
    if mic_class == "builtin":
        return (
            "Built-in mic: fine for quiet rooms; use headphones/AirPods so system "
            "audio does not leak into the Me channel."
        )
    return None


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


def resolve_mic_by_exact_name(name: str) -> MicDevice:
    """Resolve by exact device name (case-insensitive). Used for mid-session re-probe."""
    devices = list_microphones()
    if not devices:
        raise RuntimeError(
            "No avfoundation audio input devices found. Is ffmpeg installed?"
        )
    lowered = name.strip().lower()
    matches = [d for d in devices if d.name.lower() == lowered]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous mic name {name!r}: {[d.name for d in matches]}")
    raise RuntimeError(
        f"Microphone {name!r} not found (disconnected?). "
        "Reconnect AirPods/USB mic or run `callscribe devices`."
    )
