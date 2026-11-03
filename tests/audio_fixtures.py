"""Build synthetic WAVs for pipeline smoke tests (ffmpeg + macOS ``say``)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from callscribe.session import new_meta, save_meta


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not found on PATH")
    return path


def require_say() -> str:
    path = shutil.which("say")
    if not path:
        raise RuntimeError("macOS `say` not found")
    return path


def write_silence_wav(
    path: Path,
    *,
    duration_s: float,
    rate: int = 16000,
    channels: int = 2,
) -> Path:
    """Digital silence WAV (for the plan's empty-transcript check)."""
    ffmpeg = require_ffmpeg()
    layout = "stereo" if channels == 2 else "mono"
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={rate}:cl={layout}",
            "-t",
            str(duration_s),
            "-acodec",
            "pcm_s16le",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError(f"ffmpeg silence failed: {(proc.stderr or '')[-500:]}")
    return path


def say_to_wav(text: str, voice: str, out_wav: Path, *, rate: int = 16000) -> Path:
    say = require_say()
    ffmpeg = require_ffmpeg()
    aiff = out_wav.with_suffix(".aiff")
    proc = subprocess.run(
        [say, "-v", voice, "-o", str(aiff), text],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not aiff.exists():
        raise RuntimeError(
            f"`say -v {voice}` failed: {(proc.stderr or proc.stdout or '')[-400:]}"
        )
    conv = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(aiff),
            "-ac",
            "1",
            "-ar",
            str(rate),
            "-acodec",
            "pcm_s16le",
            str(out_wav),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    aiff.unlink(missing_ok=True)
    if conv.returncode != 0 or not out_wav.exists():
        raise RuntimeError(f"ffmpeg convert say failed: {(conv.stderr or '')[-500:]}")
    return out_wav


def silence_mono(path: Path, *, duration_s: float, rate: int = 16000) -> Path:
    return write_silence_wav(path, duration_s=duration_s, rate=rate, channels=1)


def _concat_wavs(parts: list[Path], out: Path) -> Path:
    ffmpeg = require_ffmpeg()
    list_file = out.parent / f"{out.stem}_list.txt"
    list_file.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in parts),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    list_file.unlink(missing_ok=True)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"ffmpeg concat failed: {(proc.stderr or '')[-500:]}")
    return out


def join_stereo(me: Path, remote: Path, out: Path, *, rate: int = 16000) -> Path:
    """L=me, R=remote mono → stereo 16-bit (same layout as mixdown).

    Caps output length to the longer input — bare ``apad`` otherwise runs forever.
    """
    from callscribe.audio_util import wav_info

    ffmpeg = require_ffmpeg()
    longer = max(float(wav_info(me)["duration_s"]), float(wav_info(remote)["duration_s"]))
    filt = (
        f"[0:a]aformat=sample_rates={rate}:channel_layouts=mono,apad[me];"
        f"[1:a]aformat=sample_rates={rate}:channel_layouts=mono,apad[remote];"
        f"[me][remote]join=inputs=2:channel_layout=stereo[out]"
    )
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(me),
            "-i",
            str(remote),
            "-filter_complex",
            filt,
            "-map",
            "[out]",
            "-t",
            f"{longer:.3f}",
            "-acodec",
            "pcm_s16le",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"ffmpeg stereo join failed: {(proc.stderr or '')[-500:]}")
    return out


def build_two_speaker_conversation(
    work: Path,
    *,
    voice_a: str = "Kathy",
    voice_b: str = "Fred",
    gap_s: float = 0.8,
) -> Path:
    """Remote-channel conversation: A → silence → B → silence → A (16 kHz mono)."""
    work.mkdir(parents=True, exist_ok=True)
    a1 = say_to_wav(
        "Hello Bob. Did the koala eat today?",
        voice_a,
        work / "a1.wav",
    )
    b1 = say_to_wav(
        "Yes Alice. Eleven eucalyptus leaves, then he slept.",
        voice_b,
        work / "b1.wav",
    )
    a2 = say_to_wav(
        "Good. We should check again tomorrow morning.",
        voice_a,
        work / "a2.wav",
    )
    gap = silence_mono(work / "gap.wav", duration_s=gap_s)
    remote = _concat_wavs([a1, gap, b1, gap, a2], work / "remote.wav")
    return remote


def make_session_dir(
    root: Path,
    *,
    call_wav: Path | None = None,
    me_wav: Path | None = None,
    remote_wav: Path | None = None,
    title: str = "fixture",
) -> Path:
    """Create a minimal session folder with meta.json + call.wav (or raw tracks)."""
    session = root / f"session_{title}"
    session.mkdir(parents=True, exist_ok=True)
    meta = new_meta(
        title=title,
        capture="system",
        mic_device="default",
        keep_raw_tracks=True,
        tool_versions={"callscribe": "test"},
    )
    meta.status = "recorded"
    save_meta(session, meta)

    dest_call = session / "call.wav"
    if call_wav is not None:
        dest_call.write_bytes(call_wav.read_bytes())
    elif me_wav is not None and remote_wav is not None:
        join_stereo(me_wav, remote_wav, dest_call)
    else:
        raise ValueError("Provide call_wav or both me_wav and remote_wav")
    return session
