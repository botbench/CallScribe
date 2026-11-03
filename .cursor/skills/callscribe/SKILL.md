---
name: callscribe
description: >-
  Operate the CallScribe macOS CLI (record system+mic audio, local Whisper ASR,
  pyannote diarization, rename speakers). Use when the user asks to record a
  call, start/stop/toggle CallScribe, run doctor/setup, list sessions,
  transcribe, rename SPEAKER_XX labels, inspect transcripts/confidence, or
  debug silent tracks / permissions / AirPods.
---

# CallScribe operator

Personal **local** macOS call recorder + transcript CLI. Prefer `uv run callscribe …`
from the CallScribe checkout (or a PATH install of `callscribe`). Do not invent
session paths — use `callscribe list`.

**Skill install (humans):** project copy ships at `.cursor/skills/callscribe/` in the
repo; `uv run callscribe setup` also installs/refreshes the personal copy at
`~/.cursor/skills/callscribe/`. See repo `README.md` → “Cursor agent skill”.

Install / permissions / troubleshooting for the CLI itself: CallScribe repo `README.md`.

## Hard rules

- **Host app:** System Audio Recording + Microphone attach to the app that launches CallScribe. Prefer **Terminal.app** (or iTerm). **WezTerm** often cannot prompt → silent remote track.
- **Network:** Only `setup` may download models. Pipeline sets Hub offline flags.
- **Never** print or commit HF tokens (`.hf_token` / `HF_TOKEN`).
- **Stereo:** `call.wav` L=me (mic), R=remote (system/app).
- **ASR confidence** = word-probability sanity only — not speaker-label accuracy.

## Commands

```bash
uv run callscribe setup
uv run callscribe doctor
uv run callscribe devices
uv run callscribe start --title meet
uv run callscribe stop
uv run callscribe status
uv run callscribe list
uv run callscribe toggle --title meet          # Shortcuts / Raycast
uv run callscribe transcribe SESSION [--foreground] [--language en] [--speakers N]
uv run callscribe rename SESSION SPEAKER_00=Name SPEAKER_01=Name
```

Config: `~/.callscribe/config.toml`. Logs: `~/.callscribe/logs/`. Sessions: `~/CallScribe/YYYY-MM-DD_HHMM[_title]/` (or `output_dir`).

## Typical workflows

### First-time / broken permissions

1. `uv run callscribe setup` (needs HF token + pyannote license accepted).
2. From Terminal.app: `uv run callscribe doctor`.
3. If remote silent → grant Screen & System Audio Recording to host app, restart it.
4. If mic silent → Microphone permission; `devices` + set `mic_device` (AirPods name changes when connected).

### Record a call

1. Headphones/AirPods preferred (avoid speaker echo on Me).
2. `start --title …` → join call → `stop`.
3. Wait for notification / `status` / `list` (`auto_transcribe` default true).
4. `rename SESSION SPEAKER_00=…` if needed (re-renders md only).

### Inspect a session

- `meta.json` — status, errors, mic class / latency bias
- `transcript.md` / `transcript.json` — turns + `confidence`
- `speakers.json` — rename map
- `recorder.log` / `transcribe.log` — process logs
- `~/.callscribe/logs/callscribe-YYYY-MM-DD.log`

### Agent behavior

- Run CLI via the shell; quote paths with spaces.
- After `start`, remind the user permissions are on the **host terminal**, not Cursor’s sandbox alone if capture is silent.
- For “is this transcript bad?” read `confidence` and per-speaker word `p`; do not claim calibrated WER.
- Mid-call AirPods drop: recorder re-probes by device name briefly; otherwise start a new session.

## Mic profiles (adaptive)

`mic_class = "auto"` (or force `airpods`/`bluetooth`/`builtin`/`usb`). AirPods/BT → looser mixdown tolerance + Me latency bias. Overrides: `mic_latency_bias_ms`, `mixdown_duration_tolerance_s`.
