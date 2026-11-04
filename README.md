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

`setup` creates `~/.callscribe/`, writes default config, checks ffmpeg, warms Whisper + pyannote into the **Hugging Face Hub cache** (network allowed here only), and installs the Cursor **personal** operator skill to `~/.cursor/skills/callscribe/`. Transcription then runs with Hub offline flags. `diarization_dir` in config is an optional local snapshot override (only used if it contains `config.yaml`); otherwise Hub cache is canonical.

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
mic_class         = "auto"               # or airpods|bluetooth|builtin|usb
# mic_latency_bias_ms          = 100     # optional; default from mic_class
# mixdown_duration_tolerance_s = 2.0     # optional; looser for AirPods
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

Each transcript includes an **ASR confidence** sanity check (`high` / `medium` / `low`) from Whisper word probabilities — useful as a “maybe shaky” flag, not a calibrated accuracy % and not a speaker-label score. Shown in `transcript.md` and the completion notification.

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
| Transcription fails offline | Re-run `setup` on the network so Hub cache has the models (`~/.cache/huggingface/hub`) |
| Wrong language | `transcribe … --foreground --language en` (or set `language` in config) |
| Session path errors | Use a real folder from `list`, not a `YYYY-MM-DD_HHMM` placeholder |
| AirPods / Bluetooth sound thin | Expected on HFP/SCO; `doctor` shows adaptive mic profile (tolerance + latency bias) |
| Mic drops mid-call (AirPods) | Recorder re-probes by name, or rotates a new `me_NNN.wav` segment if ffmpeg stalls; segments are concatenated on stop |
| Stop hangs / no transcript after a long call | Mic ffmpeg is stopped with q→TERM→KILL; stderr goes to `mic_ffmpeg.log` (no pipe deadlock). If stop still errors, recorder tries to salvage mixdown from existing tracks |

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
uv run pytest                 # unit tests (skips @pytest.mark.slow)
uv run pytest --slow          # + silence / say-voice / model pipeline smokes
# or: RUN_SLOW=1 uv run pytest
uv run ruff check src tests
```

Slow tests need `ffmpeg`, macOS `say`, and a prior `callscribe setup` (Hub model cache). They are not a quality benchmark for synthetic TTS.

### Cursor agent skill

CallScribe ships an **operator skill**: short instructions so Cursor agents know how to run the CLI (record, transcribe, rename, debug permissions). It is not a second copy of the product.

#### Install the skill

**Project skill (this repo open in Cursor)** — already in the tree; nothing extra to install:

- Path: [`.cursor/skills/callscribe/SKILL.md`](.cursor/skills/callscribe/SKILL.md)
- Applies when you work in this checkout.

**Personal skill (any Cursor chat / other projects)** — install or refresh with setup:

```bash
cd /path/to/CallScribe
uv sync
uv run callscribe setup
```

That copies the skill to `~/.cursor/skills/callscribe/`. Re-run `setup` after pulling skill updates.

| Location | Scope |
|---|---|
| `.cursor/skills/callscribe/` in this repo | Project — when this checkout is open |
| `~/.cursor/skills/callscribe/` | Personal — after `setup`, available everywhere |

Canonical packaged source: `src/callscribe/operator_skill/SKILL.md` (kept in sync with the project skill path).

#### Use the skill

1. Finish normal CallScribe install (`uv sync`, HF token, `setup`, permissions) as above.
2. In Cursor, ask in plain language, for example:
   - “Run `callscribe doctor` and tell me if mic/system audio look OK”
   - “Start a CallScribe recording titled standup”
   - “List recent sessions and show the confidence line for the latest transcript”
   - “Rename SPEAKER_00 to Alice in session …”
3. You can also name it explicitly: “Using the CallScribe skill, …”
4. The agent should drive `uv run callscribe …` (or a PATH-installed `callscribe`), use `list` for real session paths, and follow Terminal.app / WezTerm permission notes in the skill.

This skill does not replace this README for human install steps.
