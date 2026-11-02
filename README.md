# CallScribe

Personal macOS tool: record a call (system/app audio + microphone) to one stereo WAV, then (later phases) make a local speaker-labeled transcript.

**Phase 3 (current):** recording + Whisper + pyannote diarization (`Me` / `SPEAKER_XX`, then `rename`).

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

## Commands

```bash
uv run callscribe setup
uv run callscribe devices
uv run callscribe doctor          # 3s system + mic probe
uv run callscribe start --title meet
# … call …
uv run callscribe stop            # mixdown; auto-transcribe if enabled
uv run callscribe status
uv run callscribe list
uv run callscribe list
uv run callscribe transcribe ~/CallScribe/2026-11-02_1317_my-call
uv run callscribe transcribe ~/CallScribe/2026-11-02_1317_my-call --foreground --language en
uv run callscribe rename ~/CallScribe/2026-11-02_1317_my-call SPEAKER_00=Alice SPEAKER_01=Bob
```

`setup` / `start` / `list` / `doctor` create `output_dir` (default `~/CallScribe`) if it does not exist. Session folder names are stamped at record time — use `callscribe list` to find them.


Stereo `call.wav`: **left = you (mic)**, **right = remote (system/app)**.

## Permissions

1. **Screen & System Audio Recording** → the app that launches CallScribe (Terminal.app recommended)
2. **Microphone** → same app
3. Restart that app after granting access

## Known limits

See plan §10. AirPods Pro are supported (24 kHz headset mode is OK; we resample). Prefer headphones/AirPods over laptop speakers to avoid echo on the mic channel.

## Hugging Face token (later phases)

Keep a gitignored `.hf_token` in the repo root (never commit). Phase 2+ `setup` will use it for pyannote.
