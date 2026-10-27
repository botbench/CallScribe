# CallScribe

Personal macOS tool: record a call (system/app audio + microphone) to one stereo WAV, then (later phases) make a local speaker-labeled transcript.

**Phase 1 (current):** recording CLI — `start` / `stop` / mixdown / `doctor` / `devices`.

See [`callscribe-plan.md`](callscribe-plan.md), [`callscribe-plan-clarifications.md`](callscribe-plan-clarifications.md), and [`SPIKES.md`](SPIKES.md).

## Requirements

- Apple Silicon Mac, macOS 14.2+
- Homebrew `ffmpeg`, Python 3.12+ (`uv` recommended)
- **Terminal.app** (or iTerm) for System Audio Recording — WezTerm often cannot prompt

## Install

```bash
cd /path/to/CallScribe
uv sync
uv run callscribe setup
```

Optional: put CallScribe on your PATH with `uv tool install -e .` (from this repo).

## Config

Created at `~/.callscribe/config.toml` on first run. Useful keys:

```toml
mic_device = "XS AirPods Pro 3"   # from `callscribe devices`; or "default"
capture    = "system"             # or "app:Firefox"
output_dir = "~/CallScribe"
```

## Commands (Phase 1)

```bash
uv run callscribe devices
uv run callscribe doctor          # 3s system + mic probe
uv run callscribe start --title meet
# … call …
uv run callscribe stop
uv run callscribe status
uv run callscribe list
uv run callscribe transcribe ~/CallScribe/YYYY-MM-DD_HHMM   # mixdown recovery only
```

Stereo `call.wav`: **left = you (mic)**, **right = remote (system/app)**.

## Permissions

1. **Screen & System Audio Recording** → the app that launches CallScribe (Terminal.app recommended)
2. **Microphone** → same app
3. Restart that app after granting access

## Known limits

See plan §10. AirPods Pro are supported (24 kHz headset mode is OK; we resample). Prefer headphones/AirPods over laptop speakers to avoid echo on the mic channel.

## Hugging Face token (later phases)

Keep a gitignored `.hf_token` in the repo root (never commit). Phase 2+ `setup` will use it for pyannote.
