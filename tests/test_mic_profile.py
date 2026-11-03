"""Adaptive mic profiles and latency bias in mixdown delays."""

from __future__ import annotations

from callscribe.config import Config
from callscribe.devices import MicDevice
from callscribe.mic_profile import profile_for_class, resolve_mic_class, resolve_mic_profile
from callscribe.session import SessionMeta, start_delay_seconds


def test_resolve_mic_class_auto_airpods() -> None:
    d = MicDevice(index=2, name="XS AirPods Pro 3")
    assert resolve_mic_class(d, override="auto") == "airpods"


def test_resolve_mic_class_override() -> None:
    d = MicDevice(index=0, name="MacBook Pro Microphone")
    assert resolve_mic_class(d, override="usb") == "usb"


def test_airpods_profile_looser_than_builtin() -> None:
    air = profile_for_class("airpods")
    wired = profile_for_class("usb")
    assert air.duration_tolerance_s > wired.duration_tolerance_s
    assert air.me_latency_bias_ms > wired.me_latency_bias_ms


def test_config_overrides_bias_and_tolerance() -> None:
    d = MicDevice(index=1, name="Blue Yeti USB")
    cfg = Config(
        mic_class="auto",
        mic_latency_bias_ms=50.0,
        mixdown_duration_tolerance_s=3.0,
    )
    p = resolve_mic_profile(d, cfg)
    assert p.mic_class == "usb"
    assert p.me_latency_bias_ms == 50.0
    assert p.duration_tolerance_s == 3.0


def test_latency_bias_delays_remote() -> None:
    meta = SessionMeta(
        me_start_monotonic=1.0,
        remote_start_monotonic=1.0,
        me_latency_bias_ms=100.0,
    )
    me_ms, remote_ms = start_delay_seconds(meta)
    assert me_ms == 0.0
    assert remote_ms == 100.0


def test_latency_bias_absorbs_into_existing_me_delay() -> None:
    # Me started 80ms later + 100ms path bias → me delay 0, remote gets 20.
    meta = SessionMeta(
        me_start_monotonic=1.08,
        remote_start_monotonic=1.0,
        me_latency_bias_ms=100.0,
    )
    me_ms, remote_ms = start_delay_seconds(meta)
    assert abs(me_ms - 0.0) < 1e-6
    assert abs(remote_ms - 20.0) < 1e-6
