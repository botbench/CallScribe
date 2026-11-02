from __future__ import annotations

from callscribe.align import assign_speaker_for_word, words_to_speaker_turns
from callscribe.asr import merge_neighbor_turns


def test_overlap_choice() -> None:
    diar = [(0.0, 2.0, "SPEAKER_00"), (2.0, 4.0, "SPEAKER_01")]
    assert assign_speaker_for_word(0.5, 1.0, diar) == "SPEAKER_00"
    assert assign_speaker_for_word(2.5, 3.0, diar) == "SPEAKER_01"


def test_nearest_turn_fallback() -> None:
    diar = [(0.0, 1.0, "SPEAKER_00"), (3.0, 4.0, "SPEAKER_01")]
    # Word in the gap, closer to second turn, within 0.5s of it
    assert assign_speaker_for_word(2.6, 2.7, diar, nearest_s=0.5) == "SPEAKER_01"
    # Too far from both → previous speaker
    assert (
        assign_speaker_for_word(1.8, 1.9, diar, previous_speaker="SPEAKER_00", nearest_s=0.5)
        == "SPEAKER_00"
    )


def test_gap_splitting_same_speaker() -> None:
    diar = [(0.0, 10.0, "SPEAKER_00")]
    words = [
        {"w": "hello", "start": 0.0, "end": 0.4, "p": 1.0},
        {"w": "again", "start": 3.0, "end": 3.4, "p": 1.0},  # gap > 2s
    ]
    turns = words_to_speaker_turns(words, diar, gap_split_s=2.0)
    assert len(turns) == 2
    assert turns[0]["text"] == "hello"
    assert turns[1]["text"] == "again"


def test_same_speaker_merge() -> None:
    turns = [
        {
            "speaker": "SPEAKER_00",
            "start": 0.0,
            "end": 1.0,
            "text": "hi",
            "words": [],
        },
        {
            "speaker": "SPEAKER_00",
            "start": 1.2,
            "end": 2.0,
            "text": "there",
            "words": [],
        },
        {
            "speaker": "SPEAKER_01",
            "start": 3.0,
            "end": 4.0,
            "text": "yo",
            "words": [],
        },
    ]
    merged = merge_neighbor_turns(turns, max_gap_s=1.5)
    assert len(merged) == 2
    assert merged[0]["text"] == "hi there"
    assert merged[1]["speaker"] == "SPEAKER_01"
