"""Mic segment concat (restart / append path)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from callscribe.audio_util import wav_info
from callscribe.recorder import _concat_wavs


def _sine(path: Path, *, duration: float, rate: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-ar",
            str(rate),
            "-ac",
            "1",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_concat_mixed_rates(tmp_path: Path) -> None:
    a = tmp_path / "me_001.wav"
    b = tmp_path / "me_002.wav"
    out = tmp_path / "me.wav"
    _sine(a, duration=0.3, rate=24000)
    _sine(b, duration=0.4, rate=48000)
    _concat_wavs([a, b], out, sample_rate=48000)
    info = wav_info(out)
    assert info["channels"] == 1
    assert abs(float(info["duration_s"]) - 0.7) < 0.15
