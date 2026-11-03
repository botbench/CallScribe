"""Pure speaker ↔ word alignment (no I/O, no models).

Takes ASR words and exclusive diarization turns on the *remote* channel, assigns
each word a ``SPEAKER_XX``, then packs consecutive same-speaker words into turns.
Unit-tested; keep this module free of ffmpeg / torch / filesystem side effects.
"""

from __future__ import annotations

from typing import Any

# Plan defaults: nearest-turn fallback window; split turn if gap exceeds this.
NEAREST_TURN_S = 0.5
GAP_SPLIT_S = 2.0


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def assign_speaker_for_word(
    start: float,
    end: float,
    diar_turns: list[tuple[float, float, str]],
    *,
    previous_speaker: str | None = None,
    nearest_s: float = NEAREST_TURN_S,
) -> str | None:
    """Pick speaker for one word interval.

    1) Largest time overlap with a diarization turn
    2) Else nearest turn within nearest_s
    3) Else previous word's speaker
    """
    if not diar_turns:
        return previous_speaker

    best_ov = 0.0
    best_spk: str | None = None
    for t0, t1, spk in diar_turns:
        ov = _overlap(start, end, t0, t1)
        if ov > best_ov:
            best_ov = ov
            best_spk = spk
    if best_spk is not None and best_ov > 0:
        return best_spk

    mid = 0.5 * (start + end)
    best_dist = float("inf")
    nearest_spk: str | None = None
    for t0, t1, spk in diar_turns:
        if mid < t0:
            dist = t0 - mid
        elif mid > t1:
            dist = mid - t1
        else:
            dist = 0.0
        if dist < best_dist:
            best_dist = dist
            nearest_spk = spk
    if nearest_spk is not None and best_dist <= nearest_s:
        return nearest_spk

    return previous_speaker


def words_to_speaker_turns(
    words: list[dict[str, Any]],
    diar_turns: list[tuple[float, float, str]],
    *,
    gap_split_s: float = GAP_SPLIT_S,
    nearest_s: float = NEAREST_TURN_S,
    default_speaker: str = "SPEAKER_00",
) -> list[dict[str, Any]]:
    """Assign speakers to words and group into turns."""
    if not words:
        return []

    labeled: list[tuple[str, dict[str, Any]]] = []
    prev: str | None = None
    for w in words:
        start = float(w["start"])
        end = float(w["end"])
        spk = assign_speaker_for_word(
            start, end, diar_turns, previous_speaker=prev, nearest_s=nearest_s
        )
        if spk is None:
            spk = default_speaker
        labeled.append((spk, w))
        prev = spk

    turns: list[dict[str, Any]] = []
    cur_spk, first = labeled[0]
    cur_words = [first]
    for spk, w in labeled[1:]:
        gap = float(w["start"]) - float(cur_words[-1]["end"])
        if spk != cur_spk or gap > gap_split_s:
            turns.append(_pack_turn(cur_spk, cur_words))
            cur_spk = spk
            cur_words = [w]
        else:
            cur_words.append(w)
    turns.append(_pack_turn(cur_spk, cur_words))
    return turns


def _pack_turn(speaker: str, words: list[dict[str, Any]]) -> dict[str, Any]:
    text = " ".join(str(w.get("w") or "").strip() for w in words).strip()
    text = " ".join(text.split())
    return {
        "speaker": speaker,
        "start": float(words[0]["start"]),
        "end": float(words[-1]["end"]),
        "text": text,
        "words": [
            {
                "w": w["w"],
                "start": float(w["start"]),
                "end": float(w["end"]),
                "p": float(w.get("p") or 0.0),
            }
            for w in words
        ],
    }


def segment_overlaps_diarization(
    start: float,
    end: float,
    diar_turns: list[tuple[float, float, str]],
) -> bool:
    return any(_overlap(start, end, t0, t1) > 0 for t0, t1, _ in diar_turns)
