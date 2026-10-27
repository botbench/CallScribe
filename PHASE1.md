# Phase 1 report — Recording CLI

Date: 2026-10-27

## Delivered

Package `callscribe` under `src/callscribe/` with:

- `setup`, `doctor`, `devices`, `start`, `stop`, `toggle`, `status`, `list`
- `transcribe` — **mixdown recovery only** (full ASR deferred to Phase 2)
- Hidden `_recorder` detached process
- Config at `~/.callscribe/config.toml` (mic set to `XS AirPods Pro 3` on this machine)
- Stereo `call.wav` @ 16 kHz, L=me / R=remote

## Acceptance

| Criterion | Result |
|---|---|
| `doctor` / silent permission messaging | Implemented (WezTerm warning included) |
| `start` → audio → `stop` → stereo `call.wav` | **PASS** (smoke `phase1-smoke2`) |
| Double `start` / idle `stop` errors | **PASS** |
| `transcribe` recovers mix from raw tracks | Implemented (not separately re-smoked after kill) |
| Unit tests `test_config` / `test_mixdown` | **PASS** (3 tests) |

Smoke session: `~/CallScribe/2026-10-27_0934_phase1-smoke2` — status `recorded`, `call.wav` stereo 16 kHz, remote peak high, mic low but non-silent.

## Notes

- `auto_transcribe` is recorded as deferred until Phase 2 (no model spawn yet).
- Run recording from **Terminal.app** for System Audio Recording TCC.
- Next: **Phase 2** — ASR without diarization (`Remote` label on right channel).
