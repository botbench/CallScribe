from __future__ import annotations

from callscribe.asr import (
    Segment,
    Word,
    filter_segments,
    is_hallucinated_segment,
    merge_neighbor_turns,
    segments_to_turns,
)


def test_hallucination_filter() -> None:
    bad = Segment(
        start=0,
        end=1,
        text="thanks for watching",
        words=[],
        no_speech_prob=0.95,
        avg_logprob=-0.2,
        compression_ratio=1.0,
    )
    assert is_hallucinated_segment(bad)
    thanks = Segment(
        start=0.0,
        end=0.12,
        text="Thank you.",
        words=[],
        no_speech_prob=0.0,
        avg_logprob=-0.3,
        compression_ratio=0.5,
    )
    assert is_hallucinated_segment(thanks)
    good = Segment(
        start=0,
        end=1,
        text="hello world",
        words=[Word("hello", 0, 0.4, 0.9), Word("world", 0.4, 0.8, 0.9)],
        no_speech_prob=0.1,
        avg_logprob=-0.2,
        compression_ratio=1.2,
    )
    assert not is_hallucinated_segment(good)
    assert filter_segments([bad, thanks, good]) == [good]


def test_segments_to_turns_gap_split() -> None:
    segs = [
        Segment(0.0, 1.0, "one", [Word("one", 0.0, 1.0, 1.0)]),
        Segment(4.0, 5.0, "two", [Word("two", 4.0, 5.0, 1.0)]),  # gap 3s > 2s
    ]
    turns = segments_to_turns(segs, "Remote", gap_split_s=2.0)
    assert len(turns) == 2
    assert turns[0]["text"] == "one"
    assert turns[1]["text"] == "two"


def test_merge_neighbor_turns() -> None:
    turns = [
        {"speaker": "Me", "start": 0.0, "end": 1.0, "text": "hi", "words": []},
        {"speaker": "Me", "start": 1.2, "end": 2.0, "text": "there", "words": []},
        {"speaker": "Remote", "start": 3.0, "end": 4.0, "text": "yo", "words": []},
    ]
    merged = merge_neighbor_turns(turns, max_gap_s=1.5)
    assert len(merged) == 2
    assert merged[0]["text"] == "hi there"
    assert merged[1]["speaker"] == "Remote"
