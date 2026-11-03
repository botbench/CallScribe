# CallScribe — Backlog

Ideas and follow-ups that are in scope later, but not required to finish the current phase. Check items off or move them into the plan when prioritized.

---

## Mic path: wired + AirPods (adaptive)

**Status:** done (2026-11-03)  
**Added:** 2026-10-26  
**Related:** clarifications Q13 (AirPods Pro 3 as daily mic; Bluetooth allowed)

**Shipped:**
- Name-based class (`airpods` / `bluetooth` / `builtin` / `usb` / `unknown`) → mixdown duration tolerance + Me latency bias
- Config: `mic_class`, optional `mic_latency_bias_ms`, `mixdown_duration_tolerance_s`
- `doctor` prints profile tip; meta.json stores class / bias / tolerance
- Mid-session re-probe by exact device name (segmented `me_NNN.wav` + concat); clear error if gone

**Still optional later:** calibration beep for measured offset; sample-rate class defaults beyond ffmpeg resample-to-16k.

---

## Transcript sanity / confidence summary

**Status:** backlog  
**Added:** 2026-11-02  

**Intent:** After transcription, expose a simple sanity check so the user can tell if the transcript is likely shaky (without claiming a calibrated accuracy %).

**Notes:**
- Whisper has no single official “overall quality” score.
- We already store per-word `p` in `transcript.json`; segments also have `avg_logprob` / `no_speech_prob` / `compression_ratio` (used in filters, not yet summarized).
- Diarization (pyannote) does not give a reliable global confidence for the whole call in our current path.

**Possible approach:**
1. Aggregate ASR signals into something like  
   `confidence: { mean_word_p, median_word_p, low_p_ratio, warning? }` on `transcript.json`.
2. Surface a short line in `transcript.md` and/or the completion notification (e.g. “ASR confidence: medium”).
3. Optional thresholds in code defaults (same style as hallucination filters); warn when `low_p_ratio` is high or mean `p` is low.
4. Do **not** imply speaker-label correctness from this score.

---

## (empty — add more items below)
