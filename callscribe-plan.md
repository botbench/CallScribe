# CallScribe — Implementation Plan

A personal macOS tool. It records a video call (Google Meet in Firefox, or any other audio source) to one WAV file. After the call, it makes a speaker-labeled transcript. Everything runs on the local machine. No cloud service is used at runtime.

This file is the spec for the AI coding agent (Cursor). Read all of it before you write code.

---

## 1. Goals and non-goals

### Goals
1. One command (or one keyboard shortcut) starts and stops a recording of: (a) the remote people (system audio output) and (b) my own microphone.
2. The result is one stereo WAV: **left = me (microphone), right = remote (system audio)**.
3. After the recording stops, the app makes a transcript with speaker labels: `Me`, `SPEAKER_00`, `SPEAKER_01`, ...
4. All speech-to-text (STT) and diarization run locally on Apple Silicon. They work with the network switched off.
5. I can rename the generic speaker labels afterwards.

### Non-goals (do NOT build these)
- Real-time or live transcription.
- A Firefox extension. (Firefox cannot capture tab audio. The OS-level approach replaces it.)
- Windows or Linux support.
- Summaries, action items, or any LLM feature.
- Automatic speaker names or voice enrollment.
- Echo cancellation (see "Known limits").
- A GUI. Version 1 is a command-line tool (CLI).

### Assumptions (verify in Phase 0)
- Apple Silicon Mac, latest macOS (Core Audio taps need macOS 14.2 or newer).
- Python 3.12, managed with `uv`. `ffmpeg` installed with Homebrew.
- Use is personal. The user informs the call participants (recording consent is the user's responsibility).

---

## 2. Architecture

```
            start / stop / toggle
                     │
          ┌──────────▼──────────┐
          │  recorder process   │  (detached background process)
          │                     │
          │  remote.wav ◄── Core Audio tap (catap)
          │  me.wav     ◄── ffmpeg avfoundation (microphone)
          └──────────┬──────────┘
                     │ on stop
              merge (ffmpeg) ─► call.wav  (stereo, 16 kHz, 16-bit; L=me, R=remote)
                     │
                     ▼  (auto, detached)
          ┌─────────────────────┐
          │ transcribe pipeline │
          │  split channels     │
          │  remote: diarize (pyannote) + ASR (mlx-whisper) + align
          │  me:     ASR (mlx-whisper), label "Me"
          │  merge turns by time
          └──────────┬──────────┘
                     ▼
        transcript.json + transcript.md  (+ macOS notification)
```

### Technology choices (and why)
| Part | Choice | Reason |
|---|---|---|
| System audio capture | `catap` (Python wrapper of Core Audio process taps) | No loopback driver needed. Writes WAV. Can tap all system audio or one app. |
| Microphone capture | `ffmpeg -f avfoundation` as a subprocess | Robust, simple. ffmpeg is needed anyway. |
| STT | `mlx-whisper` with `mlx-community/whisper-large-v3-turbo` | Runs on the Apple GPU. Word timestamps. |
| Diarization | `pyannote.audio` 4.x, model `pyannote/speaker-diarization-community-1` | Best open model. Gives "exclusive" diarization that is easy to align with transcript timestamps. Runs on MPS. |
| CLI | `typer` | Simple. |
| Config | TOML file, read with `tomllib` | No extra dependency. |

Do NOT use `mlx-whisperx`, `whisperx`, or `WhisperLiveKit`. Use `mlx-whisper` and `pyannote.audio` directly and write the alignment step yourself (about 100 lines). Fewer layers means fewer breaking dependencies.

---

## 3. Project layout

```
callscribe/
├── pyproject.toml
├── README.md
├── PLAN.md                    # this file
├── src/callscribe/
│   ├── __init__.py
│   ├── cli.py                 # typer app, all commands
│   ├── config.py              # load/validate config.toml, defaults
│   ├── paths.py               # ~/.callscribe, output dir, session dirs
│   ├── session.py             # Session dataclass, meta.json read/write
│   ├── recorder.py            # background recorder (tap + mic), start/stop logic
│   ├── mixdown.py             # merge me.wav + remote.wav -> call.wav (ffmpeg)
│   ├── asr.py                 # mlx-whisper wrapper, hallucination filter
│   ├── diarize.py             # pyannote wrapper (MPS), returns speech turns
│   ├── align.py               # PURE functions: assign speakers to words, build turns
│   ├── render.py              # transcript.json -> transcript.md
│   ├── pipeline.py            # orchestrates the transcribe steps
│   ├── notify.py              # osascript notification
│   └── doctor.py              # permission + environment checks
└── tests/
    ├── test_align.py
    ├── test_render.py
    ├── test_mixdown.py
    ├── test_config.py
    └── fixtures/              # generated with `say` (see section 8)
```

---

## 4. Commands (CLI)

| Command | Behavior |
|---|---|
| `callscribe setup` | One-time. Check `ffmpeg`. Download the pyannote model to `~/.callscribe/models/` (needs `HF_TOKEN` in the environment, never stored). Download the Whisper model. After this, the app needs no network. |
| `callscribe doctor` | Record 3 seconds of system audio and 3 seconds of microphone. Report if either is silent (permission missing). Print versions and paths. |
| `callscribe devices` | List microphone devices (ffmpeg avfoundation list). |
| `callscribe start [--title TEXT]` | Create a session folder. Spawn the detached recorder. Write a state file. Exit fast. |
| `callscribe stop` | Tell the recorder to stop. Recorder merges and (if `auto_transcribe`) starts the pipeline. |
| `callscribe toggle` | `start` if idle, `stop` if recording. This is for a keyboard shortcut (macOS Shortcuts or Raycast). |
| `callscribe status` | Show: idle / recording (elapsed time, session path) / transcribing. |
| `callscribe transcribe <session-dir or wav> [--speakers N] [--min-speakers N] [--max-speakers N] [--language CODE]` | Run the pipeline. If `call.wav` is missing but raw tracks exist, merge first (crash recovery). |
| `callscribe rename <session-dir> SPEAKER_00="Name" ...` | Write `speakers.json` and re-render `transcript.md`. Do not re-run ASR. |
| `callscribe list` | List sessions with date, duration, transcript status. |

---

## 5. Config file: `~/.callscribe/config.toml`

Create it with these defaults if missing.

```toml
output_dir        = "~/CallScribe"
my_name           = "Me"
mic_device        = "default"      # name from `callscribe devices`
capture           = "system"       # "system" or "app:Firefox"
exclude_apps      = []             # only used when capture = "system"
language          = "auto"         # or "en", "fr", "nl", ...
whisper_model     = "mlx-community/whisper-large-v3-turbo"
diarization_dir   = "~/.callscribe/models/pyannote-speaker-diarization-community-1"
initial_prompt    = ""             # vocabulary hint for Whisper: names, acronyms
keep_raw_tracks   = true
auto_transcribe   = true
notify            = true
```

---

## 6. Detailed behavior

### 6.1 Session folder
`~/CallScribe/YYYY-MM-DD_HHMM[_title]/` contains:
- `me.wav`, `remote.wav` — raw tracks (kept if `keep_raw_tracks`).
- `call.wav` — stereo, 16 kHz, 16-bit PCM. L = me, R = remote.
- `meta.json` — start timestamps of both recorders, durations, tool versions, status (`recording | recorded | transcribing | done | failed`), error text.
- `transcript.json`, `transcript.md`, `speakers.json` (after rename).

### 6.2 Recorder
- `start` spawns `callscribe _recorder <session-dir>` with `start_new_session=True`. It writes `~/.callscribe/recorder.state` (PID, session path).
- The recorder starts the Core Audio tap (catap) and the ffmpeg microphone process **as close in time as possible**. It records a wall-clock timestamp for each start in `meta.json`.
- `stop` sends `SIGTERM` to the recorder. The recorder must stop **gracefully**:
  - Stop the tap so catap finalizes `remote.wav`.
  - Stop ffmpeg by writing `q` to its stdin (not `SIGKILL`) so the WAV header is correct.
- Then merge (6.3). Then, if `auto_transcribe`, spawn the pipeline detached.
- After stop, call catap's silence check. If `remote.wav` is only silence, set status `failed` with a clear message ("System audio recording permission is missing for <terminal app>"), send a notification, and keep the files.
- Capture mode:
  - `system`: tap all processes (optionally exclude apps from `exclude_apps`).
  - `app:<Name>`: tap one app. **Unverified:** Firefox may play audio from helper processes. Test this in Phase 0. If it fails, document it and keep `system` as default.
- Handle double `start` (error: already recording) and `stop` when idle (error: not recording). Clean a stale state file if the PID is dead.

### 6.3 Mixdown
Use ffmpeg:
- Convert both tracks to mono, 16 kHz.
- Apply a delay (`adelay`) to the track that started later, using the timestamps in `meta.json`.
- Pad the shorter track with silence so both have equal length.
- Join as stereo: L = me, R = remote.
- Output `call.wav`. Verify duration is within 1 s of the longer raw track. Fail loudly if not.

### 6.4 Transcribe pipeline (`pipeline.py`)
Run these steps in order. Free model memory between steps (set model objects to `None`, call `gc.collect()`).

1. **Prepare.** Make `call.wav` if missing. Split into `remote_16k.wav` and `me_16k.wav` (temp files).
2. **Remote channel — diarization.** Load pyannote from `diarization_dir` on `mps` (fall back to `cpu`). Use the *exclusive* speaker diarization output. Pass `num_speakers` / `min_speakers` / `max_speakers` if given. Result: a list of turns `(start, end, speaker)`.
3. **Remote channel — ASR.** Run `mlx_whisper.transcribe` with `word_timestamps=True`, `condition_on_previous_text=False`, `initial_prompt` from config, `language` from config (`None` = auto-detect).
4. **Remote channel — filter.** Drop segments that look like hallucinations: high `no_speech_prob`, low `avg_logprob`, high `compression_ratio`, or no overlap with any diarization turn. Use thresholds from config with sane defaults.
5. **Remote channel — align** (`align.py`). For each word, pick the speaker of the turn with the largest time overlap. If no turn overlaps, use the nearest turn within 0.5 s. Else use the previous word's speaker. Group consecutive words of the same speaker into turns. Start a new turn if the gap is larger than 2.0 s.
6. **Mic channel.** Run ASR the same way. Apply the same filter. Drop segments whose RMS level is below a silence threshold. Label every turn with `my_name`.
7. **Merge.** Sort all turns by start time. Merge neighbor turns of the same speaker if the gap is under 1.5 s.
8. **Write.** `transcript.json`, then `transcript.md`. Update `meta.json` (status `done`, timings). Send a notification.

If any step fails: set status `failed`, write the error in `meta.json`, keep all files, send a notification.

### 6.5 Output formats

`transcript.json`:
```json
{
  "version": 1,
  "duration_s": 2843.2,
  "language": "en",
  "speakers": {"Me": {"channel": "left"}, "SPEAKER_00": {"channel": "right"}},
  "turns": [
    {
      "speaker": "SPEAKER_00",
      "start": 8.12,
      "end": 14.50,
      "text": "Full text of the turn.",
      "words": [{"w": "Full", "start": 8.12, "end": 8.40, "p": 0.97}]
    }
  ]
}
```

`transcript.md`:
```markdown
# Call — 2026-10-23 10:00 (47 min)

**Me** [00:00:03]: Hello, can you hear me?

**SPEAKER_00** [00:00:08]: Yes, I can hear you.
```
`rename` replaces labels using `speakers.json` (`{"SPEAKER_00": "Alice"}`) and re-renders. The JSON keeps the original labels.

---

## 7. Phases and acceptance tests

Do the phases in order. After each phase, the tool must work end to end for what that phase covers. Stop and report at the end of each phase.

### Phase 0 — Spikes (small throw-away scripts, no polish)
Goal: prove the risky parts before building. Report results in `SPIKES.md`.
1. `catap record --system` while Firefox plays a video. The file is not silent.
2. Same test in `app:Firefox` mode. Report if audio is captured.
3. A real Google Meet call (or a call with a second person) in Firefox: remote voices are captured in `remote.wav`.
4. `ffmpeg` records the microphone. Permission works from the terminal app used.
5. Sync test: play a click sound while speaking at the same moment. Compare click position in `me.wav` and `remote.wav`. Report the offset.
6. `mlx_whisper` with word timestamps and `pyannote` community-1 on MPS on a 10-minute sample. Report run time and memory.
7. Run the whole of 6 with the network off (Wi-Fi off). It still works after `setup`.

**Exit criteria:** items 1, 3, 4, 6, 7 pass. If item 2 or 5 fails, record the limit and continue.

### Phase 1 — Recording
Build: `config`, `paths`, `session`, `recorder`, `mixdown`, `doctor`, `devices`, `start`, `stop`, `toggle`, `status`.
Accept when:
- `doctor` detects a missing permission (silent capture) and says what to fix.
- `start` → play audio + speak for 60 s → `stop` produces a correct stereo `call.wav` (L has my voice, R has the played audio).
- Killing the recorder with `SIGKILL` and running `transcribe` later still recovers `call.wav` from raw tracks (merge part only in this phase).
- `start` twice and `stop` while idle give clear errors.

### Phase 2 — Transcription without speakers
Build: `asr`, `render`, `pipeline` (no diarization yet: label all remote speech `Remote`).
Accept when:
- A 5-minute test file gives a readable `transcript.md`.
- A 5-minute file of silence gives an **empty** transcript (no hallucinated text).

### Phase 3 — Diarization and alignment
Build: `diarize`, `align`, `rename`, auto-run after `stop`, notifications.
Accept when:
- A two-voice test file (section 8) gives two distinct speaker labels on the right turns.
- `rename` changes labels without running ASR again.
- Unit tests for `align.py` pass (overlap choice, nearest-turn fallback, gap splitting, same-speaker merge).
- Full run works with the network off.

### Phase 4 — Hardening
- `setup` command with clear errors (missing token, license not accepted, no ffmpeg).
- Logs in `~/.callscribe/logs/`.
- `list` command.
- README with install steps, permission steps, troubleshooting, and the Known limits below.

---

## 8. Testing

- **Unit tests (pytest):** `align.py`, `render.py`, `config.py` — pure functions, no audio, no models.
- **Mixdown test:** generate two short WAV files with ffmpeg (`sine` source) with known offsets. Check the output channels and duration.
- **Synthetic speech fixtures:** make them with the macOS `say` command and two different voices, then convert with ffmpeg to 16 kHz WAV, and build a "conversation" with silence between turns. Use this as a smoke test for diarization. Use loose checks (two speakers found, most words in the right turn). Synthetic voices are not a quality benchmark.
- **Silence test:** 5 minutes of digital silence → empty transcript.
- Mark model-heavy tests with `@pytest.mark.slow` and skip them by default.

---

## 9. Rules for the AI coding agent

1. Follow the phases. Do not build features from the Non-goals list.
2. Keep dependencies minimal. Pin versions in `pyproject.toml` after Phase 0.
3. **Do not guess library APIs.** Read the installed package source, `--help`, or official docs. This matters most for `catap`, `mlx_whisper`, and `pyannote.audio` 4.x (its output object differs from 3.x).
4. Keep `align.py` and `render.py` pure (no I/O, no models) so they can be tested.
5. At runtime, make **no network calls**. Set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and `HF_HUB_DISABLE_TELEMETRY=1` in the pipeline. Only `setup` may use the network. Never store the Hugging Face token.
6. Never delete audio files automatically unless the user set `keep_raw_tracks = false`, and only after a successful merge.
7. Errors must be clear and say how to fix the problem (for example, which app needs which macOS permission).
8. Use `ruff` for lint and format. Add type hints.
9. Write the README as you go, not at the end.

---

## 10. Known limits (document in README)

- **Prefer headphones (or a headset) over loudspeakers.** With speakers, the microphone also records the remote voices. The `Me` channel would then repeat remote speech. Echo cancellation is out of scope for version 1. AirPods (output + mic) are a supported headset path — see clarifications.
- **Bluetooth / AirPods Pro are supported as the microphone** (user requirement; overrides the earlier “wired only” note). Design for HFP/SCO quality, possible sample-rate changes when the call audio route engages, and larger sync skew than a built-in or USB mic. Do not refuse or hard-block Bluetooth devices. `doctor` / README may note quality caveats; recording must still work.
- **Permissions are tied to the app that starts the recorder** (for example Terminal or iTerm). If recording is silent, give that app "Microphone" and "System Audio Recording" access in System Settings > Privacy & Security. If you start recording from another tool (Shortcuts, Raycast), that tool needs the permissions.
- **System-wide capture records all system sounds** (notifications, music). Use `exclude_apps` or `app:` mode to reduce this.
- **Speaker labels are generic.** `rename` is manual.
- **Several people on one microphone** (a conference room) count as one participant for the platform, but diarization can still split them by voice. Accuracy is lower with overlapping speech.
- **Code-switching** (two languages in one call): Whisper may mis-handle it. Set `language` explicitly if auto-detect is wrong.
- **Sync** between the two tracks is best effort (start timestamps). The Phase 0 sync test gives the real error.

---

## 11. Open questions (resolve in Phase 0, record answers in SPIKES.md)
1. Does `app:Firefox` capture all Firefox audio, including helper processes?
2. What is the real offset between `me.wav` and `remote.wav`?
3. Does catap work as a pip install on the current macOS and Python (arm64 wheel, bundled dylib)?
4. Which app gets the permission prompts when the recorder is started in the background?
5. How long do a 1-hour transcription and diarization take on this Mac, and how much memory do they use?
