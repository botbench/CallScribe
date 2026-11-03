"""Slow / model-heavy pipeline smokes (skipped unless ``--slow`` or ``RUN_SLOW=1``)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from callscribe.audio_util import wav_info
from callscribe.config import load_config
from callscribe.pipeline import run_pipeline
from tests.audio_fixtures import (
    build_two_speaker_conversation,
    join_stereo,
    make_session_dir,
    require_ffmpeg,
    require_say,
    say_to_wav,
    silence_mono,
    write_silence_wav,
)

pytestmark = pytest.mark.slow


def _models_ready() -> bool:
    """True if Whisper/pyannote are likely cached (setup has been run)."""
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    if not hub.exists():
        return False
    names = " ".join(p.name for p in hub.iterdir())
    return "whisper" in names.lower() or "pyannote" in names.lower()


@pytest.fixture(scope="module")
def cfg():
    require_ffmpeg()
    if not _models_ready():
        pytest.skip("HF model cache empty; run `uv run callscribe setup` first")
    loaded = load_config()
    loaded.notify = False
    loaded.auto_transcribe = False
    return loaded


def test_five_minute_silence_empty_transcript(tmp_path: Path, cfg) -> None:
    """Plan §8: 5 minutes of digital silence → empty transcript (no hallucinations)."""
    call = write_silence_wav(tmp_path / "call.wav", duration_s=300.0, channels=2)
    info = wav_info(call)
    assert float(info["duration_s"]) >= 299.0
    assert info["silent"] is True

    session = make_session_dir(tmp_path, call_wav=call, title="silence5m")
    rc = run_pipeline(session, cfg=cfg, language="en")
    assert rc == 0

    tj = json.loads((session / "transcript.json").read_text(encoding="utf-8"))
    turns = tj.get("turns") or []
    assert turns == [], f"expected empty turns on silence, got {turns!r}"
    md = (session / "transcript.md").read_text(encoding="utf-8")
    assert "No speech detected" in md


def test_say_two_voice_diarization_smoke(tmp_path: Path, cfg) -> None:
    """Plan §8: synthetic two-voice remote → distinct SPEAKER labels (loose)."""
    require_say()
    work = tmp_path / "say"
    remote = build_two_speaker_conversation(work)
    me = silence_mono(work / "me.wav", duration_s=float(wav_info(remote)["duration_s"]))
    call = join_stereo(me, remote, work / "call.wav")

    session = make_session_dir(tmp_path, call_wav=call, title="say_dialog")
    rc = run_pipeline(session, cfg=cfg, language="en", min_speakers=2, max_speakers=2)
    assert rc == 0

    tj = json.loads((session / "transcript.json").read_text(encoding="utf-8"))
    turns = tj.get("turns") or []
    assert turns, "expected some ASR turns from synthetic speech"
    speakers = {str(t["speaker"]) for t in turns}
    remote_speakers = {s for s in speakers if s.startswith("SPEAKER_")}
    assert len(remote_speakers) >= 2, (
        f"expected ≥2 SPEAKER_XX labels, got {speakers} turns={turns!r}"
    )

    blob = " ".join(str(t.get("text") or "") for t in turns).lower()
    hits = sum(
        1 for w in ("koala", "alice", "bob", "eucalyptus", "leaves", "tomorrow") if w in blob
    )
    assert hits >= 1, f"expected at least one dialogue keyword in {blob!r}"


def test_speech_fixture_asr_smoke(tmp_path: Path, cfg) -> None:
    """Short single-voice remote speech → non-empty transcript (ASR path)."""
    require_say()
    work = tmp_path / "one"
    work.mkdir()
    remote = say_to_wav(
        "The quick brown fox jumps over the lazy dog near the river.",
        "Fred",
        work / "remote.wav",
    )
    me = silence_mono(work / "me.wav", duration_s=float(wav_info(remote)["duration_s"]))
    call = join_stereo(me, remote, work / "call.wav")
    session = make_session_dir(tmp_path, call_wav=call, title="asr_smoke")
    rc = run_pipeline(session, cfg=cfg, language="en", num_speakers=1)
    assert rc == 0
    tj = json.loads((session / "transcript.json").read_text(encoding="utf-8"))
    turns = tj.get("turns") or []
    assert turns
    blob = " ".join(str(t.get("text") or "") for t in turns).lower()
    assert any(w in blob for w in ("fox", "dog", "river", "quick", "lazy")), blob
    conf = tj.get("confidence") or {}
    assert conf.get("level") in {"high", "medium", "low", "unknown"}
