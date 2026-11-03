"""Merge me.wav + remote.wav into stereo call.wav (L=me, R=remote).

Sync is best-effort: delay the track that started later using timestamps from
``meta.json`` (monotonic preferred). Output is always 16 kHz 16-bit PCM stereo.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from callscribe.audio_util import wav_info
from callscribe.session import SessionMeta, start_delay_seconds


class MixdownError(RuntimeError):
    pass


def _require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise MixdownError(
            "ffmpeg not found on PATH. Install with: brew install ffmpeg"
        )
    return path


def mixdown(
    me_wav: Path,
    remote_wav: Path,
    out_wav: Path,
    meta: SessionMeta,
    *,
    sample_rate: int = 16000,
    duration_tolerance_s: float | None = None,
) -> Path:
    """Create 16 kHz 16-bit stereo WAV: left=me, right=remote.

    Duration slack comes from ``meta.mixdown_duration_tolerance_s`` (mic profile)
    when ``duration_tolerance_s`` is not passed explicitly.
    """
    ffmpeg = _require_ffmpeg()
    if not me_wav.exists():
        raise MixdownError(f"Missing mic track: {me_wav}")
    if not remote_wav.exists():
        raise MixdownError(f"Missing remote track: {remote_wav}")

    if duration_tolerance_s is None:
        duration_tolerance_s = (
            float(meta.mixdown_duration_tolerance_s)
            if meta.mixdown_duration_tolerance_s is not None
            else 1.0
        )

    me_info = wav_info(me_wav)
    remote_info = wav_info(remote_wav)
    me_delay_ms, remote_delay_ms = start_delay_seconds(meta)

    # adelay takes ms per channel; for mono we duplicate the value (L|R syntax).
    me_adelay = max(0, int(round(me_delay_ms)))
    remote_adelay = max(0, int(round(remote_delay_ms)))

    with tempfile.TemporaryDirectory(prefix="callscribe-mix-") as tmp:
        tmp_path = Path(tmp)
        staged = tmp_path / "call.wav"
        # Resample → delay later track → pad → join stereo. -t uses the longer
        # (duration + delay) so apad does not leave the join open-ended.
        filter_complex = (
            f"[0:a]aformat=sample_rates={sample_rate}:channel_layouts=mono,"
            f"adelay={me_adelay}|{me_adelay},apad[me];"
            f"[1:a]aformat=sample_rates={sample_rate}:channel_layouts=mono,"
            f"adelay={remote_adelay}|{remote_adelay},apad[remote];"
            f"[me][remote]join=inputs=2:channel_layout=stereo[out]"
        )
        longer = max(
            float(me_info["duration_s"]) + me_delay_ms / 1000.0,
            float(remote_info["duration_s"]) + remote_delay_ms / 1000.0,
        )
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(me_wav),
            "-i",
            str(remote_wav),
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-t",
            f"{longer:.3f}",
            "-acodec",
            "pcm_s16le",
            str(staged),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise MixdownError(
                "ffmpeg mixdown failed:\n"
                + (proc.stderr or proc.stdout or "(no output)")[-2000:]
            )
        if not staged.exists():
            raise MixdownError("ffmpeg mixdown produced no output file")

        out_info = wav_info(staged)
        expected = longer
        if abs(float(out_info["duration_s"]) - expected) > duration_tolerance_s:
            raise MixdownError(
                f"call.wav duration {out_info['duration_s']:.2f}s is not within "
                f"{duration_tolerance_s}s of expected {expected:.2f}s "
                f"(me={me_info['duration_s']:.2f}s remote={remote_info['duration_s']:.2f}s)"
            )
        if int(out_info["channels"]) != 2:
            raise MixdownError(
                f"Expected stereo call.wav, got {out_info['channels']} channels"
            )
        if int(out_info["rate"]) != sample_rate:
            raise MixdownError(
                f"Expected {sample_rate} Hz call.wav, got {out_info['rate']} Hz"
            )

        out_wav.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(out_wav)

    return out_wav
