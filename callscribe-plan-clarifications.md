# CallScribe — Plan validation & clarifications

Companion to [`callscribe-plan.md`](./callscribe-plan.md).  
Created after reviewing the plan against current library docs (catap, mlx-whisper, pyannote.audio / community-1, Apple Core Audio taps).

**Status:** validation complete; **all §4 suggested defaults accepted** (2026-10-23). Amend this file if decisions change.

---

## 0a. Environment (user)

| Fact | Detail |
|---|---|
| Terminal | **WezTerm** (`/Applications/WezTerm.app`, version 0.1.0) |
| `NSMicrophoneUsageDescription` | Present — mic permission prompt can appear |
| `NSAudioCaptureUsageDescription` | **Missing** — macOS will not prompt for System Audio Recording when capture is launched from WezTerm; taps often deliver silence with no way to grant access in Settings for a never-prompted app |

**Implication for Phase 0 / `doctor` / README:** document WezTerm as a known host problem. Practical workarounds for system-audio spikes and daily use:

1. Run `callscribe` / Phase 0 capture scripts from **Terminal.app** or **iTerm** (apps that can prompt), or
2. Patch WezTerm’s `Info.plist` to add `NSAudioCaptureUsageDescription` and re-sign (fragile across updates), or
3. Wait for upstream WezTerm to ship the key.

Mic-only spikes can still run from WezTerm. System-audio spikes should use a capable host until WezTerm is fixed.

**Agent instruction (2026-10-23):** Prefer launching system-audio capture / Phase 0 spikes via **Terminal.app** when WezTerm cannot prompt.

---

## 0. Doc location note

- The plan lives at the **repo root** (`callscribe-plan.md`), not under `docs/`.
- `docs/` exists but is empty.
- This clarifications file is next to the plan at the repo root.

---

## 1. What validates cleanly

| Claim in the plan | Verdict |
|---|---|
| Core Audio process taps need **macOS 14.2+** | Confirmed (Apple docs; catap targets the same). |
| **`catap`** captures system / per-app audio without a loopback driver; writes WAV; supports `--system`, exclude apps, `app:Name` | Confirmed (PyPI / README). Python ≥3.11; wheels include universal2 dylib. |
| Silent capture when System Audio Recording permission is missing | Confirmed. Use `session.captured_only_silence` (not a separate “silence check” helper name). |
| Permissions attach to the **host app** (Terminal, iTerm, Shortcuts, Raycast, …) | Confirmed. Host may need `NSAudioCaptureUsageDescription` or no prompt ever appears (e.g. some third-party terminals). |
| **Stereo layout L=me / R=remote** as a diarization shortcut | Sound architecture; matches the exclusive-diarization + per-channel ASR design. |
| **`mlx-whisper`** + `mlx-community/whisper-large-v3-turbo` + `word_timestamps=True` | Confirmed. |
| **`pyannote/speaker-diarization-community-1`** + exclusive diarization for ASR alignment | Confirmed (`output.exclusive_speaker_diarization`; `num_speakers` / `min_speakers` / `max_speakers`). |
| Offline after setup via `HF_HUB_OFFLINE` etc.; never store HF token | Sound and matches pyannote offline guidance. |
| Avoid `whisperx` / `mlx-whisperx` / WhisperLiveKit; hand-roll ~100 lines of align | Reasonable dependency hygiene. |
| Non-goals (no live STT, no GUI v1, no LLM summaries, no AEC) | Internally consistent with the CLI + dual-file design. |
| Phased spikes (Phase 0) before packaging | Good risk order; Firefox helper processes + sync offset are the right unknowns. |

---

## 2. Risks / corrections (do not block Phase 0, but update the plan)

### 2.1 pyannote on MPS is unreliable

The plan says: load on `mps`, fall back to `cpu`.

Reality: official examples show **CUDA**; maintainers have repeatedly said MPS is not production-ready for pyannote. There are open crash reports (e.g. Metal shader assertions during embedding) where CPU works and MPS fails.

**Recommendation for the plan:** Phase 0 must treat “MPS works for community-1 on *this* Mac” as a spike, not a given. Default runtime should be **CPU if MPS fails or is flaky**, with clear logging of which device was used. Acceptance for Phase 3 should allow CPU-only diarization if MPS fails the spike.

### 2.2 Silence API naming

Plan §6.2: “call catap's silence check.”

Actual API: `session.captured_only_silence` (and `track_captured_only_silence` for multitrack). Doctor/recorder should use that (or equivalent RMS on the WAV).

### 2.3 Optional alternative: catap multitrack + mic

catap now has **experimental** `record_multitrack(..., microphone=True)` with sample-synchronized tracks. The plan deliberately uses **ffmpeg avfoundation** for the mic + separate catap tap + wall-clock `adelay` sync.

That remains a solid, documented path. Multitrack mic is worth a **Phase 0 spike only** if you want better sync; do not make v1 depend on the experimental path unless the spike proves it.

### 2.4 Config gaps vs prose

§6.4 says hallucination thresholds come “from config with sane defaults,” but §5 `config.toml` does **not** list them (`no_speech_prob`, `avg_logprob`, `compression_ratio`, mic RMS silence, align gap 0.5 s / 2.0 s / merge 1.5 s).

**Recommendation:** hardcode defaults in code; optionally expose later. Avoid inventing TOML keys until you care to tune them.

### 2.5 Project layout vs repo today

| Plan | Repo now |
|---|---|
| `PLAN.md` inside `callscribe/` | `callscribe-plan.md` at root |
| Package under `src/callscribe/` | Not created yet (expected) |

Harmless; pick one canonical plan path when scaffolding.

### 2.6 Packaging / entry points unspecified

Plan assumes a `callscribe` CLI and a hidden `_recorder` subprocess, but does not specify:

- install via `uv tool install`, editable `uv sync`, or both;
- console script in `pyproject.toml`;
- whether `_recorder` is a Typer subcommand (hidden) or `python -m callscribe.recorder`.

Worth fixing in Phase 1 scaffolding, not Phase 0.

### 2.7 Terminal / Info.plist caveat for permissions

If the launch app never declares audio-capture usage, macOS may never show the System Audio Recording prompt. Document in README (plan §10 already covers “which app”); add “verify your terminal can prompt” to doctor troubleshooting.

---

## 3. Internal consistency checks (passed)

- Dual-track → stereo mixdown → split channels → diarize remote only → ASR both → merge by time is coherent.
- Crash recovery (`transcribe` merges raw tracks if `call.wav` missing) matches Phase 1 acceptance.
- `rename` re-renders markdown without re-ASR matches non-goal “no auto speaker names.”
- Headphones (or AirPods) + no AEC match the channel-as-speaker design; Bluetooth mic is an accepted quality tradeoff (see §4b).
- `auto_transcribe` after stop + detached pipeline matches “one command” UX for recording; transcription is async (status must cover `transcribing`).

---

## 4. Clarifications (accepted 2026-10-23)

All suggested defaults accepted; amend later if needed.

### Q1 — Where should the plan live?

- [x] Keep at root (`callscribe-plan.md` + this file)

### Q2 — Primary browser / capture target

Keep `capture = "system"` as default; document Firefox `app:` as best-effort after Phase 0.

### Q3 — Diarization device policy

- [x] Try **MPS first**, automatic fallback to CPU on error; log device used

### Q4 — Mic capture strategy

- [x] Stick to plan: **ffmpeg avfoundation** + timestamp `adelay` for v1 (no required catap-mic spike)

### Q5 — Typical use (sizing)

Design for ~1 h calls, 2–4 remote speakers, `language = "auto"`. (Hardware specifics unknown; Phase 0 measures this Mac.)

### Q6 — Default speaker bounds

Unconstrained (pyannote default); CLI flags only when the user knows.

### Q7 — Concurrent jobs

One recorder at a time; allow transcription while idle for recording; reject a second concurrent transcribe with a clear error (simple state file).

### Q8 — Install UX for personal use

- [x] Both documented; Phase 4 README focuses on a global install

### Q9 — Hallucination / align knobs in config?

Code defaults only; add TOML keys only if Phase 2 silence/hallucination tests need tuning.

### Q10 — Session folder timezone

Local time for folder names; store ISO UTC in `meta.json` as well.

### Q11 — Hugging Face setup friction

Document the Hub click-path in README; fail `setup` with the Hub URL if license/token missing.

### Q12 — Scope freeze

Keep Non-goals as written for v1.

### Q13 — Microphone: AirPods Pro (override) — 2026-10-23

**Decision:** The user’s daily mic is **AirPods Pro 3**. Wired/USB mic is **not** required. The original plan §10 “Do not use AirPods…” limit is **rescinded**.

**Design requirements (v1 must handle this):**

1. **First-class device:** `callscribe devices` lists Bluetooth headsets; config `mic_device` may be the AirPods name (or a stable ffmpeg avfoundation index/name). Prefer matching by name when the buds reconnect.
2. **Do not refuse Bluetooth.** No hard error solely because the selected input is Bluetooth / AirPods. Soft warnings in `doctor` / README about possible lower bitrate or narrowband HFP are OK.
3. **Route changes:** When a call starts, macOS often switches the AirPods into headset (HFP/SCO) mode — sample rate and latency can jump. Recorder/mixdown must tolerate mid-session format differences between `me.wav` and `remote.wav` (resample to 16 kHz mono in mixdown as already planned; verify duration/sync with wider tolerance if needed).
4. **Sync:** Expect larger and less stable offset than built-in mic. Keep wall-clock `adelay`; Phase 0 spike 5 should be re-run **with AirPods Pro connected** as the mic device (not built-in).
5. **Echo:** AirPods as output still satisfies the “headphones” guidance (remote audio in-ear, less bleed into the mic). Keep “no AEC” as a non-goal.
6. **Spike / doctor:** Validate that Terminal.app (or the recorder host) can record from the AirPods mic non-silently; document any permission or device-selection quirks.

**Plan edit:** §10 Bluetooth bullet rewritten accordingly in `callscribe-plan.md`.

**Backlog (2026-10-26):** Accommodate **wired and AirPods** in one product by probing the selected mic and adjusting rate / latency / sync per device class — see [`BACKLOG.md`](./BACKLOG.md).

---

## 5. Suggested plan edits (after your answers)

Small text fixes that do not need product decisions:

1. §6.2: say `captured_only_silence` instead of “catap's silence check.”
2. §6.4 / §5: either add threshold keys or say “hardcoded defaults in `asr.py` / `align.py`.”
3. §2 Architecture / Phase 0: add “pyannote MPS may fail; CPU fallback is required for acceptance.”
4. §3 layout: rename `PLAN.md` → `callscribe-plan.md` (or move to `docs/`) to match the repo.
5. §4: document the internal `_recorder` entry point next to public commands.
6. Phase 0 item: explicitly spike pyannote on MPS vs CPU (time + crash or not).

---

## 6. Answers log

| ID | Decision | Date |
|---|---|---|
| Q1–Q12 | Accept all suggested defaults (see §4) | 2026-10-23 |
| Env | Host terminal = WezTerm; lacks `NSAudioCaptureUsageDescription` (verified on this machine) | 2026-10-23 |
| Env | Agent may run system-audio spikes via Terminal.app | 2026-10-23 |
| Q13 | AirPods Pro 3 is the primary mic; Bluetooth supported; wired not required (see §4 / Q13) | 2026-10-23 |
| Backlog | Probe wired vs AirPods and adapt rate/latency/sync (`BACKLOG.md`) | 2026-10-26 |
