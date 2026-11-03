"""Small WAV helpers (silence detection, duration).

``silent`` uses a very low peak/RMS gate — suitable for “permission denied /
digital zero” checks after recording, not for ASR energy filtering (see asr.py).
"""

from __future__ import annotations

import array
import wave
from pathlib import Path


def wav_info(path: Path) -> dict[str, float | int | bool]:
    with wave.open(str(path), "rb") as w:
        nch = w.getnchannels()
        sw = w.getsampwidth()
        rate = w.getframerate()
        nframes = w.getnframes()
        raw = w.readframes(nframes)

    if sw != 2:
        # Still compute duration; treat non-16-bit as non-silent if any bytes.
        duration = nframes / rate if rate else 0.0
        return {
            "duration_s": duration,
            "channels": nch,
            "rate": rate,
            "peak": 1 if raw else 0,
            "rms": 1.0 if raw else 0.0,
            "silent": not bool(raw),
        }

    samples = array.array("h")
    samples.frombytes(raw)
    if not samples:
        return {
            "duration_s": 0.0,
            "channels": nch,
            "rate": rate,
            "peak": 0,
            "rms": 0.0,
            "silent": True,
        }

    peak = max(abs(s) for s in samples)
    mean_sq = sum(s * s for s in samples) / len(samples)
    rms = mean_sq**0.5
    # Near-digital-zero only; real quiet speech usually exceeds this.
    silent = peak < 32 and rms < 1.0
    return {
        "duration_s": nframes / rate,
        "channels": nch,
        "rate": rate,
        "peak": peak,
        "rms": round(rms, 2),
        "silent": silent,
    }


def is_silent_wav(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 44:
        return True
    return bool(wav_info(path)["silent"])
