"""ASR sanity / confidence summary from per-word Whisper probabilities.

This is a coarse signal for “transcript may be shaky,” not calibrated accuracy
and **not** a measure of speaker-label correctness.
"""

from __future__ import annotations

from typing import Any, Literal

# Defaults (same style as asr.py hallucination gates — not in config.toml for v1).
LOW_WORD_P = 0.45
# Level thresholds on mean word probability.
MEAN_HIGH = 0.78
MEAN_MEDIUM = 0.60
# Also warn if too many words sit below LOW_WORD_P.
LOW_P_RATIO_WARN = 0.35

ConfidenceLevel = Literal["high", "medium", "low", "unknown"]


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def collect_word_probs(turns: list[dict[str, Any]]) -> list[float]:
    """Gather finite word probabilities ``p`` from transcript turns."""
    probs: list[float] = []
    for turn in turns:
        for w in turn.get("words") or []:
            try:
                p = float(w.get("p", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            if p < 0.0 or p > 1.0:
                continue
            probs.append(p)
    return probs


def summarize_confidence(
    turns: list[dict[str, Any]],
    *,
    low_word_p: float = LOW_WORD_P,
    mean_high: float = MEAN_HIGH,
    mean_medium: float = MEAN_MEDIUM,
    low_p_ratio_warn: float = LOW_P_RATIO_WARN,
) -> dict[str, Any]:
    """Build a ``confidence`` object for ``transcript.json``.

    Returns keys: ``level``, ``mean_word_p``, ``median_word_p``, ``low_p_ratio``,
    ``word_count``, ``warning``, ``note``.
    """
    probs = collect_word_probs(turns)
    note = (
        "ASR word-probability sanity check only; not speaker-label accuracy "
        "and not a calibrated error rate."
    )
    if not probs:
        return {
            "level": "unknown",
            "mean_word_p": None,
            "median_word_p": None,
            "low_p_ratio": None,
            "word_count": 0,
            "warning": False,
            "note": note,
        }

    mean_p = sum(probs) / len(probs)
    median_p = _median(probs)
    low_count = sum(1 for p in probs if p < low_word_p)
    low_ratio = low_count / len(probs)

    if mean_p >= mean_high and low_ratio < low_p_ratio_warn:
        level: ConfidenceLevel = "high"
    elif mean_p >= mean_medium and low_ratio < low_p_ratio_warn * 1.25:
        level = "medium"
    else:
        level = "low"

    warning = level == "low" or low_ratio >= low_p_ratio_warn

    return {
        "level": level,
        "mean_word_p": round(mean_p, 4),
        "median_word_p": round(median_p, 4),
        "low_p_ratio": round(low_ratio, 4),
        "word_count": len(probs),
        "warning": warning,
        "note": note,
    }


def format_confidence_line(confidence: dict[str, Any] | None) -> str | None:
    """One markdown / notification line, or None if nothing useful to show."""
    if not confidence:
        return None
    level = str(confidence.get("level") or "unknown")
    if level == "unknown":
        return "ASR confidence: unknown (no word probabilities)."

    mean = confidence.get("mean_word_p")
    low_ratio = confidence.get("low_p_ratio")
    parts = [f"ASR confidence: {level}"]
    if mean is not None:
        parts.append(f"mean p={float(mean):.2f}")
    if low_ratio is not None:
        parts.append(f"low-p share={float(low_ratio):.0%}")
    line = " · ".join(parts)
    if confidence.get("warning"):
        line += " (review recommended)"
    return line


def format_confidence_notify(confidence: dict[str, Any] | None) -> str:
    """Short fragment for macOS notification body."""
    if not confidence:
        return ""
    level = str(confidence.get("level") or "unknown")
    if level == "unknown":
        return ""
    if confidence.get("warning"):
        return f" · ASR {level} ⚠"
    return f" · ASR {level}"
