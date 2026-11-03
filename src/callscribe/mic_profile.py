"""Adaptive microphone profiles (wired vs AirPods / Bluetooth).

Classification is heuristic from the avfoundation device name. Profiles adjust
mixdown sync tolerance and a small latency bias — they never hard-block Bluetooth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from callscribe.devices import MicClass, MicDevice, classify_mic, mic_class_tip

if TYPE_CHECKING:
    from callscribe.config import Config

# Per-class defaults. Bias: assume Me (mic) lags remote by this many ms → delay remote.
_CLASS_DEFAULTS: dict[MicClass, tuple[float, float]] = {
    # (duration_tolerance_s, me_latency_bias_ms)
    "builtin": (0.75, 0.0),
    "usb": (0.75, 0.0),
    "airpods": (2.0, 100.0),
    "bluetooth": (2.0, 120.0),
    "unknown": (1.0, 0.0),
}

VALID_MIC_CLASSES: frozenset[str] = frozenset(
    {"auto", "airpods", "bluetooth", "builtin", "usb", "unknown"}
)


@dataclass(frozen=True)
class MicProfile:
    """Capture/mixdown knobs derived from mic class (+ optional config overrides)."""

    mic_class: MicClass
    duration_tolerance_s: float
    me_latency_bias_ms: float
    source: str  # "auto:<class>" or "config:<class>"


def resolve_mic_class(
    device: MicDevice,
    *,
    override: str | None = None,
) -> MicClass:
    """Return effective class; ``override`` of ``auto``/empty uses name heuristics."""
    if override and override.strip() and override.strip().lower() != "auto":
        key = override.strip().lower()
        if key not in VALID_MIC_CLASSES - {"auto"}:
            raise ValueError(
                f"Invalid mic_class {override!r}; "
                f"expected one of {sorted(VALID_MIC_CLASSES)}"
            )
        return key  # type: ignore[return-value]
    return classify_mic(device.name)


def profile_for_class(mic_class: MicClass, *, source: str | None = None) -> MicProfile:
    tol, bias = _CLASS_DEFAULTS[mic_class]
    return MicProfile(
        mic_class=mic_class,
        duration_tolerance_s=tol,
        me_latency_bias_ms=bias,
        source=source or f"auto:{mic_class}",
    )


def resolve_mic_profile(device: MicDevice, cfg: Config) -> MicProfile:
    """Build profile from device name + config overrides."""
    mic_class = resolve_mic_class(device, override=cfg.mic_class)
    source = (
        f"config:{mic_class}"
        if cfg.mic_class and cfg.mic_class.lower() != "auto"
        else f"auto:{mic_class}"
    )
    base = profile_for_class(mic_class, source=source)

    tol = base.duration_tolerance_s
    bias = base.me_latency_bias_ms
    if cfg.mixdown_duration_tolerance_s is not None:
        tol = float(cfg.mixdown_duration_tolerance_s)
    if cfg.mic_latency_bias_ms is not None:
        bias = float(cfg.mic_latency_bias_ms)

    return MicProfile(
        mic_class=base.mic_class,
        duration_tolerance_s=tol,
        me_latency_bias_ms=bias,
        source=source,
    )


def profile_tip(profile: MicProfile) -> str:
    """Human summary for doctor / logs."""
    tip = mic_class_tip(profile.mic_class)
    bits = [
        f"class={profile.mic_class} ({profile.source})",
        f"mixdown_tolerance={profile.duration_tolerance_s:.2f}s",
        f"me_latency_bias={profile.me_latency_bias_ms:.0f}ms",
    ]
    line = "; ".join(bits)
    if tip:
        return f"{line}. {tip}"
    return line
