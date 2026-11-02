# Phase 3 report — Diarization + rename

Date: 2026-11-02

## Delivered

- `diarize.py` — pyannote community-1, MPS then CPU fallback  
- `align.py` — pure word↔speaker alignment  
- Pipeline uses exclusive diarization on remote channel → `SPEAKER_XX`  
- `callscribe rename SESSION SPEAKER_00=Name …` → `speakers.json` + re-render md  
- JSON keeps original labels; markdown uses rename map  

## Acceptance

| Criterion | Result |
|---|---|
| Two-voice remote → distinct speaker labels | **PASS** (`koala2` Alice/Bob dialogue) |
| `rename` without re-ASR | **PASS** |
| Unit tests for `align.py` | **PASS** (13 tests total suite) |
| Offline-capable after models cached | Supported via `HF_HUB_OFFLINE` + Hub cache / `.hf_token` |

### koala2 excerpt (after diarization)

```markdown
**Me** [00:00:00]: So this koala stuff sounds very interesting…
**SPEAKER_01** [00:00:06]: Hello, Bob. Did the koala eat today?
**SPEAKER_00** [00:00:09]: Yes, Alice. Eleven eucalyptus leaves, then he slept.
…
```

After `rename SPEAKER_00=Bob SPEAKER_01=Alice`, markdown shows names; `transcript.json` still has `SPEAKER_*`.

Diarization on this clip: ~30 s on **MPS**.

## Next

**Phase 4** — hardening: richer `setup` errors, logs, README polish / troubleshooting.
