# Phase 4 report — Hardening

Date: 2026-11-02

## Delivered

- **`setup`** — clear failures for missing ffmpeg, mlx-whisper, HF token, gated-license / Hub errors; warms Whisper + loads pyannote community-1 (`setup_cmd.py`)
- **Logs** — append-only `~/.callscribe/logs/callscribe-YYYY-MM-DD.log` from setup, recorder, pipeline, and `start`
- **`list`** — status, duration, transcript presence, rename count, title, error snippet
- **README** — install, HF token, permissions (WezTerm caveat), workflow, troubleshooting table, known limits

## Acceptance

| Criterion | Result |
|---|---|
| `setup` clear errors (token, license, ffmpeg) | **PASS** (message + fix hint; logged) |
| Logs under `~/.callscribe/logs/` | **PASS** |
| `list` command | **PASS** (polished) |
| README install / permissions / troubleshooting / limits | **PASS** |

## Notes

- Transcription still forces Hub offline env; only `setup` may use the network.
- Session-local `recorder.log` remains for the detached recorder process stderr/stdout.
