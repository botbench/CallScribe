# Phase 2 report — Transcription without diarization

Date: 2026-11-02

## Delivered

- `asr.py` — mlx-whisper + hallucination / silence filters  
- `render.py` — pure `transcript.json` → markdown  
- `pipeline.py` — split stereo, ASR both channels, label **Me** / **Remote**, merge turns  
- `callscribe transcribe` (detach or `--foreground`)  
- `auto_transcribe` after `stop` spawns background `_transcribe`  
- Dependency: `mlx-whisper` in main package deps  

## Acceptance

| Criterion | Result |
|---|---|
| Readable transcript from speech fixture | **PASS** (`_phase2_fixtures/speech`) |
| 5 min digital silence → empty transcript | **PASS** (skip ASR when channel RMS is silence; also phrase/duration filters) |
| Unit tests (render / asr filter / config / mixdown) | **PASS** (9 tests) |

### Speech fixture excerpt

```markdown
**Remote** [00:00:00]: Yes I can hear you. This is the remote speaker on the call.
**Me** [00:00:00]: Hello, this is me on the microphone. Can you hear me clearly?
```

### Silence note

Whisper confidently hallucinates “Thank you.” on digital silence (`no_speech_prob` ≈ 0). Phase 2 skips ASR when the whole channel RMS is below threshold; short “Thank you.” segments are also denylisted.

## Next

**Phase 3** — pyannote diarization, `align.py`, `rename`, speaker labels `SPEAKER_00`… on the remote channel.
