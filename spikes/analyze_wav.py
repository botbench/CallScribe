#!/usr/bin/env python3
"""Report duration, peak, and RMS for a WAV; exit 1 if effectively silent."""
from __future__ import annotations

import sys
import wave
from pathlib import Path


def analyze(path: Path) -> dict:
    with wave.open(str(path), "rb") as w:
        nch = w.getnchannels()
        sw = w.getsampwidth()
        rate = w.getframerate()
        nframes = w.getnframes()
        raw = w.readframes(nframes)

    if sw != 2:
        raise SystemExit(f"expected 16-bit PCM, got sample width {sw}")

    import array

    samples = array.array("h")
    samples.frombytes(raw)
    if not samples:
        return {
            "path": str(path),
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
    # Digital silence from denied taps is exactly zero; treat near-zero as silent.
    silent = peak < 32 and rms < 1.0
    return {
        "path": str(path),
        "duration_s": nframes / rate,
        "channels": nch,
        "rate": rate,
        "peak": peak,
        "rms": round(rms, 2),
        "silent": silent,
    }


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(f"usage: {sys.argv[0]} <file.wav>")
    info = analyze(Path(sys.argv[1]))
    for k, v in info.items():
        print(f"{k}: {v}")
    raise SystemExit(1 if info["silent"] else 0)


if __name__ == "__main__":
    main()
