from __future__ import annotations

import subprocess
from pathlib import Path

from callscribe.audio_util import wav_info
from callscribe.mixdown import mixdown
from callscribe.session import SessionMeta


def _sine(path: Path, *, freq: int, duration: float, rate: int = 48000) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={freq}:duration={duration}",
            "-ar",
            str(rate),
            "-ac",
            "1",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_mixdown_stereo_and_delay(tmp_path: Path) -> None:
    me = tmp_path / "me.wav"
    remote = tmp_path / "remote.wav"
    out = tmp_path / "call.wav"
    _sine(me, freq=440, duration=1.0, rate=24000)  # AirPods-like rate
    _sine(remote, freq=880, duration=1.2, rate=48000)

    meta = SessionMeta(
        me_start_monotonic=1.05,
        remote_start_monotonic=1.00,  # me started 50ms later
    )
    mixdown(me, remote, out, meta)
    info = wav_info(out)
    assert info["channels"] == 2
    assert info["rate"] == 16000
    assert abs(float(info["duration_s"]) - 1.25) < 0.15  # 1.2 + 0.05
    assert info["silent"] is False
