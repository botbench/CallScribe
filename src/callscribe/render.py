"""Pure transcript rendering (no I/O)."""

from __future__ import annotations

from typing import Any


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_duration_human(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    total = max(0, int(round(seconds)))
    if total < 60:
        return f"{total} s"
    mins = total // 60
    rem = total % 60
    if mins < 60:
        return f"{mins} min" if rem == 0 else f"{mins} min {rem} s"
    hours = mins // 60
    mins = mins % 60
    return f"{hours} h {mins} min"


def apply_speaker_map(
    transcript: dict[str, Any],
    mapping: dict[str, str],
) -> dict[str, Any]:
    """Return a shallow copy with turn speaker labels remapped for display.

    Does not mutate the original labels used for JSON persistence.
    """
    out = dict(transcript)
    out["turns"] = [
        {**t, "speaker": mapping.get(str(t["speaker"]), str(t["speaker"]))}
        for t in transcript.get("turns") or []
    ]
    return out


def render_markdown(
    transcript: dict[str, Any],
    *,
    title: str | None = None,
    created_local: str | None = None,
    speaker_map: dict[str, str] | None = None,
) -> str:
    """Build transcript.md body from transcript.json structure."""
    data = apply_speaker_map(transcript, speaker_map) if speaker_map else transcript
    duration = data.get("duration_s")
    when = created_local or "unknown time"
    # Prefer "YYYY-MM-DD HH:MM" from ISO-ish local string
    if created_local and "T" in created_local:
        when = created_local.replace("T", " ")[:16]
    head_title = title or "Call"
    lines = [
        f"# {head_title} — {when} ({format_duration_human(duration)})",
        "",
    ]
    turns = data.get("turns") or []
    if not turns:
        lines.append("_No speech detected._")
        lines.append("")
        return "\n".join(lines)

    for t in turns:
        speaker = t.get("speaker", "?")
        start = format_timestamp(float(t.get("start", 0.0)))
        text = str(t.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"**{speaker}** [{start}]: {text}")
        lines.append("")
    return "\n".join(lines)
