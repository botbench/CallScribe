# CallScribe

Local macOS tool: record a call (system/app audio + microphone) to one stereo WAV, then produce a speaker-labeled transcript with Whisper + pyannote — all on-device after `setup`.

**Stereo layout:** left = you (mic), right = remote (system/app).

See [`callscribe-plan.md`](callscribe-plan.md), [`callscribe-plan-clarifications.md`](callscribe-plan-clarifications.md), and [`SPIKES.md`](SPIKES.md).

## Requirements

- Apple Silicon Mac, macOS 14.2+
- Homebrew `ffmpeg`
- Python 3.12+ (`uv` recommended)
- **Terminal.app** (or iTerm) for System Audio Recording — WezTerm often cannot show the TCC prompt
- Hugging Face account + Read token, with the pyannote community-1 license accepted

## Install

```bash
cd /path/to/CallScribe
brew install ffmpeg
uv sync
```

### Hugging Face token

1. Create a [Read token](https://huggingface.co/settings/tokens).
2. Open [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1), accept the user conditions while logged in.
3. Either:
   - `export HF_TOKEN=hf_...` in your shell, or
   - put the token in a **gitignored** `.hf_token` file at the repo root (never commit it).

```bash
uv run callscribe setup
```

`setup` creates `~/.callscribe/`, writes default config, checks ffmpeg, warms the Whisper model, and downloads pyannote (network allowed here only). After that, transcription runs with Hub offline flags set.

Optional PATH install: `uv tool install -e .` from this repo.

## Permissions

Grant these to the **app that launches CallScribe** (Terminal.app recommended):

1. **Screen & System Audio Recording** — System Settings → Privacy & Security
2. **Microphone** — same pane
3. **Quit and reopen** that app after granting access

If you start CallScribe from Shortcuts, Raycast, or another launcher, **that** app needs the permissions — not Terminal.

**WezTerm:** system-audio capture is often silently empty (no permission prompt). Use Terminal.app for recording.

## Config

Created at `~/.callscribe/config.toml` on first run:

```toml
output_dir        = "~/CallScribe"
my_name           = "Me"
mic_device        = "XS AirPods Pro 3"   # from `callscribe devices`; or "default"
capture           = "system"             # or "app:Firefox"
exclude_apps      = []
language          = "auto"
whisper_model     = "mlx-community/whisper-large-v3-turbo"
initial_prompt    = ""                   # optional vocabulary hints
keep_raw_tracks   = true
auto_transcribe   = true
notify            = true
```

Logs: `~/.callscribe/logs/callscribe-YYYY-MM-DD.log`

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
uv run callscribe transcribe ~/CallScribe/2026-11-02_1317_my-call
uv run callscribe transcribe ~/CallScribe/2026-11-02_1317_my-call --foreground --language en
uv run callscribe rename ~/CallScribe/2026-11-02_1317_my-call SPEAKER_00=Alice SPEAKER_01=Bob
uv run callscribe --version
```

Session folders are stamped at record time (`YYYY-MM-DD_HHMM[_title]`). Use `list` to find them — do not invent placeholder paths.

`rename` updates `speakers.json` and re-renders `transcript.md` without re-running ASR. JSON keeps original `SPEAKER_XX` labels.

## Typical workflow

1. Put on headphones / AirPods (avoid laptop speakers → echo on the mic channel).
2. `callscribe doctor` once after granting permissions.
3. `callscribe start --title meet` → join the call → `callscribe stop`.
4. Wait for the transcript notification (or `status` / `list`).
5. `callscribe rename … SPEAKER_00=Name` if needed.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Remote / system track silent | Grant System Audio Recording to the **host app**; prefer Terminal.app over WezTerm; restart the app |
| Mic track silent | Grant Microphone; unmute; `devices` and set `mic_device` (AirPods name changes when connected) |
| `setup` fails on HF / 403 / gated | Accept the pyannote model license; use a valid Read token in `HF_TOKEN` or `.hf_token` |
| `ffmpeg not found` | `brew install ffmpeg` |
| Transcription fails offline | Re-run `setup` on the network so models are cached |
| Wrong language | `transcribe … --foreground --language en` (or set `language` in config) |
| Session path errors | Use a real folder from `list`, not a `YYYY-MM-DD_HHMM` placeholder |

Inspect logs under `~/.callscribe/logs/` and `meta.json` / `recorder.log` inside the session folder.

## Known limits

- Prefer headphones or a headset over loudspeakers so the mic does not pick up remote speech.
- AirPods Pro are supported (HFP/SCO, possible rate changes); quality can be lower than a wired mic.
- Permissions are tied to the launching app.
- System capture records notifications and other sounds; use `exclude_apps` or `app:` mode to narrow.
- Speaker labels start as `Me` / `SPEAKER_XX`; rename is manual.
- Several people on one mic can be split by diarization, but overlapping speech is harder.
- Code-switching may confuse Whisper; set `language` explicitly if needed.
- Track sync is best-effort from start timestamps (see Phase 0 sync notes in `SPIKES.md`).

## Development

```bash
uv run pytest
uv run ruff check src tests
```
