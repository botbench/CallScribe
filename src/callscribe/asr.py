"""mlx-whisper wrapper and hallucination / silence filters.

Thresholds are intentionally hardcoded (plan clarifications): expose in config
only if users need to tune. ``condition_on_previous_text=False`` reduces
Whisper looping on call audio.
"""

from __future__ import annotations

import array
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Hallucination / silence gates (16-bit PCM RMS where noted).
NO_SPEECH_PROB_MAX = 0.6
AVG_LOGPROB_MIN = -1.0
COMPRESSION_RATIO_MAX = 2.4
MIC_RMS_MIN = 50.0  # per-segment; drop quiet mic slices (noise floor / bleed)
CHANNEL_RMS_SILENCE = 20.0  # whole-file; skip ASR entirely on near-digital silence
MIN_SEGMENT_DURATION_S = 0.25
# Phrases Whisper often invents on silence (matched after normalize).
HALLUCINATION_PHRASES = frozenset(
    {
        "thank you",
        "thanks",
        "thanks for watching",
        "thank you for watching",
        "bye",
        "you",
        "字幕by amara.org",
        "subtitles by the amara.org community",
        ".",
        "...",
    }
)


@dataclass(frozen=True)
class Word:
    w: str
    start: float
    end: float
    p: float


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word]
    no_speech_prob: float = 0.0
    avg_logprob: float = 0.0
    compression_ratio: float = 0.0


@dataclass
class AsrResult:
    language: str | None
    segments: list[Segment]
    text: str


def _pcm_rms(samples: array.array) -> float:
    if not samples:
        return 0.0
    mean_sq = sum(s * s for s in samples) / len(samples)
    return mean_sq**0.5


def _read_mono_pcm(path: Path, start: float | None = None, end: float | None = None) -> array.array:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            return array.array("h")
        rate = w.getframerate()
        nch = w.getnchannels()
        nframes = w.getnframes()
        i0 = 0 if start is None else max(0, int(start * rate))
        i1 = nframes if end is None else min(nframes, max(i0 + 1, int(end * rate)))
        w.setpos(i0)
        raw = w.readframes(i1 - i0)
    samples = array.array("h")
    samples.frombytes(raw)
    if nch > 1:
        samples = array.array("h", samples[::nch])
    return samples


def _segment_rms(path: Path, start: float, end: float) -> float:
    """RMS of a time slice in a mono 16-bit WAV (approximate)."""
    return _pcm_rms(_read_mono_pcm(path, start, end))


def channel_rms(path: Path) -> float:
    """Whole-file mono RMS (first channel if multi-channel)."""
    return _pcm_rms(_read_mono_pcm(path))


def channel_is_silent(path: Path, *, threshold: float = CHANNEL_RMS_SILENCE) -> bool:
    if not path.exists() or path.stat().st_size < 44:
        return True
    return channel_rms(path) < threshold


def _normalize_phrase(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    return " ".join(cleaned.split())


def is_hallucinated_segment(seg: Segment) -> bool:
    if seg.no_speech_prob > NO_SPEECH_PROB_MAX:
        return True
    if seg.avg_logprob < AVG_LOGPROB_MIN:
        return True
    if seg.compression_ratio > COMPRESSION_RATIO_MAX:
        return True
    text = seg.text.strip()
    if not text:
        return True
    dur = max(0.0, seg.end - seg.start)
    if dur < MIN_SEGMENT_DURATION_S and len(text.split()) <= 3:
        return True
    phrase = _normalize_phrase(text)
    if phrase in HALLUCINATION_PHRASES:
        return True
    return False


def filter_segments(
    segments: list[Segment],
    *,
    wav_path: Path | None = None,
    require_mic_energy: bool = False,
    diar_turns: list[tuple[float, float, str]] | None = None,
) -> list[Segment]:
    """Drop likely hallucinations; optional mic RMS and diarization overlap gates."""
    from callscribe.align import segment_overlaps_diarization

    kept: list[Segment] = []
    for seg in segments:
        if is_hallucinated_segment(seg):
            continue
        if require_mic_energy and wav_path is not None:
            if _segment_rms(wav_path, seg.start, seg.end) < MIC_RMS_MIN:
                continue
        if diar_turns is not None and not segment_overlaps_diarization(
            seg.start, seg.end, diar_turns
        ):
            continue
        kept.append(seg)
    return kept


def transcribe_wav(
    path: Path,
    *,
    model: str,
    language: str | None,
    initial_prompt: str = "",
) -> AsrResult:
    """Run mlx-whisper with word timestamps (needed for diarization alignment)."""
    import mlx_whisper

    kwargs: dict[str, Any] = {
        "path_or_hf_repo": model,
        "word_timestamps": True,
        "condition_on_previous_text": False,
    }
    if language:
        kwargs["language"] = language
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt

    raw = mlx_whisper.transcribe(str(path), **kwargs)
    segments: list[Segment] = []
    for s in raw.get("segments") or []:
        words: list[Word] = []
        for wd in s.get("words") or []:
            token = str(wd.get("word") or wd.get("text") or "").strip()
            if not token:
                continue
            words.append(
                Word(
                    w=token,
                    start=float(wd.get("start", s.get("start", 0.0))),
                    end=float(wd.get("end", s.get("end", 0.0))),
                    p=float(wd.get("probability", wd.get("p", 0.0)) or 0.0),
                )
            )
        segments.append(
            Segment(
                start=float(s.get("start", 0.0)),
                end=float(s.get("end", 0.0)),
                text=str(s.get("text") or "").strip(),
                words=words,
                no_speech_prob=float(s.get("no_speech_prob") or 0.0),
                avg_logprob=float(s.get("avg_logprob") or 0.0),
                compression_ratio=float(s.get("compression_ratio") or 0.0),
            )
        )
    return AsrResult(
        language=raw.get("language"),
        segments=segments,
        text=str(raw.get("text") or "").strip(),
    )


def segments_to_turns(
    segments: list[Segment],
    speaker: str,
    *,
    gap_split_s: float = 2.0,
) -> list[dict[str, Any]]:
    """Group filtered ASR segments into turns for one speaker label."""
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for seg in segments:
        words_payload = [
            {"w": w.w, "start": w.start, "end": w.end, "p": w.p} for w in seg.words
        ]
        if current is None:
            current = {
                "speaker": speaker,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "words": words_payload,
            }
            continue
        gap = seg.start - float(current["end"])
        if gap > gap_split_s:
            turns.append(_finalize_turn(current))
            current = {
                "speaker": speaker,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "words": words_payload,
            }
        else:
            current["end"] = seg.end
            joiner = " " if current["text"] and seg.text else ""
            current["text"] = f"{current['text']}{joiner}{seg.text}".strip()
            current["words"].extend(words_payload)

    if current is not None:
        turns.append(_finalize_turn(current))
    return turns


def _finalize_turn(turn: dict[str, Any]) -> dict[str, Any]:
    turn["text"] = " ".join(str(turn["text"]).split())
    return turn


def merge_neighbor_turns(
    turns: list[dict[str, Any]],
    *,
    max_gap_s: float = 1.5,
) -> list[dict[str, Any]]:
    """Sort by start; merge adjacent same-speaker turns if gap < max_gap_s."""
    if not turns:
        return []
    ordered = sorted(turns, key=lambda t: float(t["start"]))
    merged: list[dict[str, Any]] = [dict(ordered[0])]
    merged[0]["words"] = list(ordered[0].get("words") or [])
    for nxt in ordered[1:]:
        cur = merged[-1]
        gap = float(nxt["start"]) - float(cur["end"])
        if cur["speaker"] == nxt["speaker"] and gap < max_gap_s:
            cur["end"] = float(nxt["end"])
            joiner = " " if cur["text"] and nxt["text"] else ""
            cur["text"] = f"{cur['text']}{joiner}{nxt['text']}".strip()
            cur["text"] = " ".join(cur["text"].split())
            cur["words"] = list(cur.get("words") or []) + list(nxt.get("words") or [])
        else:
            merged.append(
                {
                    "speaker": nxt["speaker"],
                    "start": float(nxt["start"]),
                    "end": float(nxt["end"]),
                    "text": nxt["text"],
                    "words": list(nxt.get("words") or []),
                }
            )
    return merged
