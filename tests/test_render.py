from __future__ import annotations

from callscribe.render import format_timestamp, render_markdown


def test_format_timestamp() -> None:
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(65) == "00:01:05"
    assert format_timestamp(3661) == "01:01:01"


def test_render_markdown_empty() -> None:
    md = render_markdown(
        {"duration_s": 12.0, "turns": []},
        title="Call",
        created_local="2026-10-27T10:00:00",
    )
    assert "Call — 2026-10-27 10:00" in md
    assert "No speech detected" in md


def test_render_markdown_turns_and_remap() -> None:
    transcript = {
        "duration_s": 120.0,
        "turns": [
            {
                "speaker": "Me",
                "start": 3.0,
                "end": 5.0,
                "text": "Hello",
                "words": [],
            },
            {
                "speaker": "Remote",
                "start": 8.0,
                "end": 10.0,
                "text": "Hi there",
                "words": [],
            },
        ],
    }
    md = render_markdown(transcript, title="Standup", created_local="2026-10-27T09:00:00")
    assert "**Me** [00:00:03]: Hello" in md
    assert "**Remote** [00:00:08]: Hi there" in md

    remapped = render_markdown(
        transcript,
        title="Standup",
        created_local="2026-10-27T09:00:00",
        speaker_map={"Remote": "Alice"},
    )
    assert "**Alice** [00:00:08]: Hi there" in remapped
    assert "**Remote**" not in remapped
