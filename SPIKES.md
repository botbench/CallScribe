# CallScribe — Phase 0 spike results

Date: 2026-10-23  
Machine: Apple Silicon (`arm64`), macOS 27.0.1  
Tools installed for spikes: Homebrew `ffmpeg` 9.0.2, `uv` 0.13.5, CPython 3.12.15  
Spike env: `spikes-env/` (`catap` 0.6.0, `mlx-whisper` 0.4.3, `pyannote.audio` 4.0.7)  
Artifacts: `spikes/out/`

Host note: **WezTerm lacks `NSAudioCaptureUsageDescription`**. System-audio spikes were run via **Terminal.app** (`.command` files). Cursor/agent shells get silent system capture.

---

## Summary

| # | Spike | Result |
|---|---|---|
| 1 | `catap record --system` | **PASS** (via Terminal.app) |
| 2 | `catap record Firefox` | **PASS** (via Terminal.app) |
| 3 | Meet-like call in Firefox (narrator + self) | **PASS** (2026-10-27) |
| 4 | `ffmpeg` microphone (AirPods Pro 3) | **PASS** (2026-10-27; Terminal.app, device `:3`) |
| 5 | Sync offset me vs remote (AirPods) | **PASS with limits** (2026-10-27) — see §5 |
| 6 | mlx-whisper + pyannote on sample | **PASS** (2026-10-27; short ~20 s sample — not yet 10‑minute) |
| 7 | Offline after setup | **PASS** (2026-10-27; `HF_HUB_OFFLINE=1` + cached models) |

Exit criteria from plan: 1, 3, 4, 6, 7 must pass. **All required spikes PASS** (item 5 recorded with limits). Phase 0 complete pending your go-ahead for Phase 1.

---

## 1. System capture (`catap --system`) — PASS

- Host: Terminal.app
- Command: `uv run catap record --system -d 8 -o spikes/out/spike1_system.wav`
- Audio during capture: `say` + `afplay` beep
- Result: 8.0 s, 48 kHz stereo, peak 24862, RMS ~3439, **not silent**
- Same command from Cursor: **silent** (`captured_only_silence` warning) — expected without host permission

## 2. Firefox app tap — PASS

- Opened YouTube in Firefox, then `catap record Firefox -d 10`
- Result: ~10 s, peak 24173, RMS ~3280, **not silent**
- `list-apps` was empty at start of the script; recording by name still found Firefox (PID matched) and captured audio

**Implication:** `capture = "app:Firefox"` is viable on this machine for browser media. Still verify on a live Meet (spike 3) in case Meet uses a helper process.

## 3. Meet-like call (narrator video + self) — PASS (2026-10-27)

Setup (user): Firefox call with narrated video in one tab (local mute as needed) and self in another; narrator = remote audio, AirPods = me.

| Capture | Result |
|---|---|
| `catap record Firefox` 30 s | **PASS** — 48 kHz stereo, peak 18920, RMS ~1823, not silent → `spike3_remote_firefox.wav` |
| `catap record --system` 30 s | **PASS** — peak 28273, RMS ~2301 → `spike3_remote_system.wav` |
| AirPods mic (retry `:3`, 10 s) | **PASS** — 24 kHz, peak 9990, not silent → `spike3_me.wav` (first dual-run mic failed: bad index parse) |

**Implication:** Firefox process tap captures Meet/call remote audio on this machine — `app:Firefox` remains viable; `system` also works as fallback.

## 4. Microphone (`ffmpeg` + AirPods Pro 3) — PASS (2026-10-27)

Earlier built-in mic (`:0`) was silent from Terminal/Cursor. With **XS AirPods Pro 3** connected:

- avfoundation index **`:3`** (`XS AirPods Pro 3`)
- Host: Terminal.app
- Result: 8.0 s, **24 kHz** mono, peak 14094, RMS ~594, **not silent**
- Artifact: `spikes/out/spike4_airpods.wav`

**Product notes:** AirPods input often arrives at 24 kHz (headset/HFP-style). Mixdown must resample to 16 kHz. Prefer device **name** match (`XS AirPods Pro 3`) over a fixed index (indices shift).

## 5. Sync offset (AirPods + system) — PASS with limits (2026-10-27)

Dual start in Terminal: `catap --system` + `ffmpeg -i :3`.

| Metric | Value |
|---|---|
| `me` start − `remote` start | **+0.0012 s** (~1.2 ms) |
| Click/`say` play at | ~2.51 s wall |
| `spike5_me.wav` | 8.0 s, 24 kHz, **not silent** (peak clipped) |
| `spike5_remote.wav` | ~8.07 s, 48 kHz stereo, **not silent** |
| Peak in remote (1.5–4.5 s window) | ~**2.89 s** (playback) |
| Peak in me (same window) | ~**3.46 s** (likely speech / reaction, not the in-ear click) |
| me − remote peak | ~**+0.57 s** |

**Interpretation:** Process spawn skew is negligible. In-ear AirPods playback does **not** reliably couple the click into the mic, so the ~570 ms peak delta is **not** a pure clock offset (includes reaction time + BT path). For v1, keep wall-clock `adelay` using start timestamps; expect Bluetooth latency bias on the order of tens–hundreds of ms and allow a looser mixdown duration check. Optional backlog: calibration beep / probe-and-adjust (`BACKLOG.md`).

## 6. mlx-whisper + pyannote — PASS (2026-10-27)

Token via gitignored `.hf_token`. Sample: `spikes/out/spike6_short.wav` (~20.6 s, two `say` voices). Report: `spikes/out/spike6_pyannote_report.json`.

### Whisper — PASS

- Model: `mlx-community/whisper-large-v3-turbo`, `word_timestamps=True`
- First run (incl. download, 2026-10-23): **~36 s** wall; peak RSS ~**2.4 GB**
- Cached re-run (offline spike 7): **~3.0 s**
- Transcript quality: accurate; 4 segments, 48 words, language `en`

### pyannote community-1 — PASS

- `torch` 2.14.1; MPS available
- Load (first after token): ~12 s
- Inference on ~20 s audio:
  - **MPS:** 7.1 s — 2 speakers, 4 exclusive turns (correct A/B alternation)
  - **CPU:** 5.7 s — identical turns (CPU slightly faster on this short clip)
- Peak RSS for combined run (~load + MPS + CPU): ~**4.1 GB**
- Policy confirmed: try MPS, fall back to CPU — both work on this Mac for community-1

**Note:** Plan asked for a 10‑minute timing sample; not run yet. Optional follow-up before Phase 4 README numbers.

## 7. Offline — PASS (2026-10-27)

With `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1` and models already cached:

- Whisper: OK (~3.0 s)
- pyannote CPU: OK (~5.8 s, same 2 speakers / 4 turns)

Report: `spikes/out/spike7_offline_report.json`.  
(Did not physically toggle Wi‑Fi; Hub offline env vars prove no network fetch.)

---

## What we learned for the product

1. Prefer **Terminal.app** (or iTerm) as the recorder host until WezTerm ships `NSAudioCaptureUsageDescription`.
2. `catap` silence warning + `captured_only_silence` matches the plan’s doctor behavior.
3. Firefox process tap works for browser playback on this Mac.
4. Dual-process start skew is tiny (~2 ms); wall-clock `adelay` remains the right v1 approach once mic works.
5. Whisper + pyannote work offline after `setup`; load token from gitignored `.hf_token` (never commit).
6. On this machine, pyannote MPS works; CPU can be as fast or faster on short audio — still keep MPS-first + CPU fallback.

---

## Resume checklist (for you)

1. ~~Mic / AirPods spikes 4–5~~ done.
2. ~~HF token / community-1 license~~ done (`.hf_token`).
3. ~~Spike 3 Meet/call capture~~ done.
4. Optional: 10‑minute ASR+diarization timing for README.
5. ~~Phase 1 recording CLI~~ started 2026-10-27 — see README.
