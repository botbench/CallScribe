"""Transcription pipeline: split stereo → diarize remote → ASR both → merge turns.

Invariant: ``call.wav`` is stereo with **left = me (mic)** and **right = remote**.
Remote speakers become ``SPEAKER_XX`` via exclusive pyannote diarization + word
alignment; the mic channel is always labeled ``my_name`` (default ``Me``).

Must run offline after ``setup`` (Hub offline env vars). Only ``setup`` downloads.
"""

from __future__ import annotations

import gc
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from callscribe.align import words_to_speaker_turns
from callscribe.asr import (
    channel_is_silent,
    filter_segments,
    merge_neighbor_turns,
    segments_to_turns,
    transcribe_wav,
)
from callscribe.audio_util import wav_info
from callscribe.confidence import format_confidence_notify, summarize_confidence
from callscribe.config import Config, load_config
from callscribe.diarize import diarize_wav
from callscribe.logging_util import log_exception, log_line
from callscribe.mixdown import MixdownError, mixdown
from callscribe.notify import notify
from callscribe.render import render_markdown
from callscribe.session import load_meta, save_meta
from callscribe.state import clear_transcribe_state


def _set_offline_env() -> None:
    # Force cache-only Hub access so a flaky network cannot phone home mid-call.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def _split_stereo(call_wav: Path, me_out: Path, remote_out: Path) -> None:
    """Split stereo call.wav: L→me, R→remote (mono 16 kHz)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    r1 = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(call_wav),
            "-af",
            "pan=mono|c0=c0",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(me_out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if r1.returncode != 0:
        raise RuntimeError(f"ffmpeg split L failed: {(r1.stderr or '')[-800:]}")
    r2 = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(call_wav),
            "-af",
            "pan=mono|c0=c1",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(remote_out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if r2.returncode != 0:
        raise RuntimeError(f"ffmpeg split R failed: {(r2.stderr or '')[-800:]}")


def _language_arg(cfg: Config, override: str | None) -> str | None:
    lang = (override or cfg.language or "auto").strip()
    if not lang or lang.lower() == "auto":
        return None
    return lang


def _ensure_call_wav(session_dir: Path, cfg: Config) -> Path:
    """Use existing call.wav, or rebuild from raw tracks (crash / keep_raw recovery)."""
    call = session_dir / "call.wav"
    if call.exists():
        return call
    me = session_dir / "me.wav"
    remote = session_dir / "remote.wav"
    if me.exists() and remote.exists():
        meta = load_meta(session_dir)
        mixdown(me, remote, call, meta)
        return call
    raise FileNotFoundError(
        f"No call.wav (and no me.wav/remote.wav to merge) in {session_dir}"
    )


def _words_from_segments(segments) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for seg in segments:
        for w in seg.words:
            words.append({"w": w.w, "start": w.start, "end": w.end, "p": w.p})
    return words


def run_pipeline(
    session_dir: Path,
    *,
    cfg: Config | None = None,
    language: str | None = None,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> int:
    """Transcribe a session. Returns process exit code."""
    cfg = cfg or load_config()
    session_dir = session_dir.resolve()
    _set_offline_env()

    meta = load_meta(session_dir)
    meta.status = "transcribing"
    meta.error = None
    save_meta(session_dir, meta)
    timings: dict[str, Any] = {}
    log_line("pipeline", f"start {session_dir}")

    try:
        t0 = time.monotonic()
        call = _ensure_call_wav(session_dir, cfg)
        timings["prepare_s"] = time.monotonic() - t0

        lang = _language_arg(cfg, language)
        my_name = cfg.my_name or "Me"
        diar_dir = cfg.diarization_dir_path()

        with tempfile.TemporaryDirectory(prefix="callscribe-asr-") as tmp:
            tmp_path = Path(tmp)
            me_16k = tmp_path / "me_16k.wav"
            remote_16k = tmp_path / "remote_16k.wav"
            _split_stereo(call, me_16k, remote_16k)

            detected_lang: str | None = None
            diar_turns: list[tuple[float, float, str]] = []

            # Remote first: diarization is exclusive on this channel only (no Me).
            # Skip silent channels — Whisper often invents "Thank you" on digital silence.
            t_d = time.monotonic()
            if channel_is_silent(remote_16k):
                remote_turns = []
                timings["diarize_s"] = 0.0
                timings["remote_asr_s"] = 0.0
                timings["remote_skipped"] = "silent_channel"
            else:
                diar_turns, diar_device = diarize_wav(
                    remote_16k,
                    diarization_dir=diar_dir,
                    num_speakers=num_speakers,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers,
                )
                timings["diarize_s"] = time.monotonic() - t_d
                timings["diarize_device"] = diar_device
                gc.collect()

                t1 = time.monotonic()
                remote_result = transcribe_wav(
                    remote_16k,
                    model=cfg.whisper_model,
                    language=lang,
                    initial_prompt=cfg.initial_prompt,
                )
                # Drop ASR that falls outside any diarization turn (hallucination aid).
                remote_segs = filter_segments(
                    remote_result.segments,
                    diar_turns=diar_turns if diar_turns else None,
                )
                words = _words_from_segments(remote_segs)
                if diar_turns:
                    remote_turns = words_to_speaker_turns(words, diar_turns)
                else:
                    remote_turns = segments_to_turns(remote_segs, "SPEAKER_00")
                detected_lang = remote_result.language
                del remote_result
                gc.collect()
                timings["remote_asr_s"] = time.monotonic() - t1

            # Mic: one speaker label; reuse remote-detected language when language=auto.
            t2 = time.monotonic()
            if channel_is_silent(me_16k):
                me_turns = []
                timings["me_asr_s"] = 0.0
                timings["me_skipped"] = "silent_channel"
            else:
                me_result = transcribe_wav(
                    me_16k,
                    model=cfg.whisper_model,
                    language=lang or detected_lang,
                    initial_prompt=cfg.initial_prompt,
                )
                me_segs = filter_segments(
                    me_result.segments,
                    wav_path=me_16k,
                    require_mic_energy=True,
                )
                me_turns = segments_to_turns(me_segs, my_name)
                if not detected_lang:
                    detected_lang = me_result.language
                del me_result
                gc.collect()
                timings["me_asr_s"] = time.monotonic() - t2

        # Interleave Me + remote turns by start time; merge short same-speaker gaps.
        turns = merge_neighbor_turns(remote_turns + me_turns)
        duration = float(wav_info(call)["duration_s"])

        speakers: dict[str, dict[str, str]] = {my_name: {"channel": "left"}}
        for t in turns:
            spk = str(t["speaker"])
            if spk != my_name:
                speakers[spk] = {"channel": "right"}

        # speakers.json remaps labels in markdown only; JSON keeps SPEAKER_XX stable.
        speaker_map_path = session_dir / "speakers.json"
        speaker_map: dict[str, str] | None = None
        if speaker_map_path.exists():
            speaker_map = json.loads(speaker_map_path.read_text(encoding="utf-8"))

        confidence = summarize_confidence(turns)

        transcript: dict[str, Any] = {
            "version": 1,
            "duration_s": duration,
            "language": detected_lang or lang or "unknown",
            "speakers": speakers,
            "turns": turns,
            "timings": timings,
            "confidence": confidence,
            "phase": 3,  # pipeline feature level (diarization), not git phase
        }

        (session_dir / "transcript.json").write_text(
            json.dumps(transcript, indent=2) + "\n",
            encoding="utf-8",
        )
        md = render_markdown(
            transcript,
            title=meta.title or "Call",
            created_local=meta.created_local or None,
            speaker_map=speaker_map,
        )
        (session_dir / "transcript.md").write_text(md, encoding="utf-8")

        meta.status = "done"
        meta.duration_s = duration
        meta.tool_versions = {
            **(meta.tool_versions or {}),
            "pipeline": "phase3-diarize",
            "whisper_model": cfg.whisper_model,
            "diarize_device": str(timings.get("diarize_device", "")),
        }
        meta.error = None
        save_meta(session_dir, meta)
        log_line(
            "pipeline",
            f"done {session_dir.name} turns={len(turns)} "
            f"asr_confidence={confidence.get('level')} "
            f"diarize_s={timings.get('diarize_s')} me_asr_s={timings.get('me_asr_s')}",
        )
        conf_bit = format_confidence_notify(confidence)
        notify(
            "CallScribe",
            f"Transcript ready: {session_dir.name} ({len(turns)} turns){conf_bit}",
            enabled=cfg.notify,
        )
        return 0

    except MixdownError as e:
        meta.status = "failed"
        meta.error = f"Mixdown before ASR failed: {e}"
        save_meta(session_dir, meta)
        log_exception("pipeline", meta.error, e)
        notify("CallScribe", meta.error, enabled=cfg.notify)
        return 1
    except Exception as e:
        meta.status = "failed"
        meta.error = str(e)
        save_meta(session_dir, meta)
        log_exception("pipeline", f"failed {session_dir.name}", e)
        notify("CallScribe", f"Transcription failed: {e}", enabled=cfg.notify)
        return 1
    finally:
        clear_transcribe_state()
        gc.collect()


def re_render_transcript(session_dir: Path, cfg: Config | None = None) -> None:
    """Re-write transcript.md from transcript.json + speakers.json (no ASR)."""
    cfg = cfg or load_config()
    session_dir = session_dir.resolve()
    meta = load_meta(session_dir)
    tj = session_dir / "transcript.json"
    if not tj.exists():
        raise FileNotFoundError(f"No transcript.json in {session_dir}")
    transcript = json.loads(tj.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    sp = session_dir / "speakers.json"
    if sp.exists():
        mapping = json.loads(sp.read_text(encoding="utf-8"))
    md = render_markdown(
        transcript,
        title=meta.title or "Call",
        created_local=meta.created_local or None,
        speaker_map=mapping or None,
    )
    (session_dir / "transcript.md").write_text(md, encoding="utf-8")
