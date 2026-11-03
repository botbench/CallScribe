"""ASR confidence / sanity summary."""

from __future__ import annotations

from callscribe.confidence import (
    format_confidence_line,
    format_confidence_notify,
    summarize_confidence,
)


def _turn(*probs: float) -> dict:
    return {
        "speaker": "Me",
        "start": 0.0,
        "end": 1.0,
        "text": "x",
        "words": [{"w": "w", "start": 0.0, "end": 0.1, "p": p} for p in probs],
    }


def test_empty_turns_unknown() -> None:
    c = summarize_confidence([])
    assert c["level"] == "unknown"
    assert c["word_count"] == 0
    assert c["warning"] is False


def test_high_confidence() -> None:
    c = summarize_confidence([_turn(0.95, 0.9, 0.92, 0.88)])
    assert c["level"] == "high"
    assert c["warning"] is False
    assert c["mean_word_p"] is not None and c["mean_word_p"] > 0.85


def test_low_confidence_warns() -> None:
    c = summarize_confidence([_turn(0.2, 0.3, 0.25, 0.4)])
    assert c["level"] == "low"
    assert c["warning"] is True
    assert c["low_p_ratio"] is not None and c["low_p_ratio"] > 0.5


def test_medium_band() -> None:
    # Around 0.65–0.75 mean with few low-p words → medium
    c = summarize_confidence([_turn(0.7, 0.68, 0.72, 0.65, 0.7)])
    assert c["level"] == "medium"


def test_format_line_and_notify() -> None:
    c = summarize_confidence([_turn(0.2, 0.3)])
    line = format_confidence_line(c)
    assert line is not None
    assert "ASR confidence: low" in line
    assert "review recommended" in line
    assert "ASR low" in format_confidence_notify(c)
