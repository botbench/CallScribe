# CallScribe — Backlog

Ideas and follow-ups that are in scope later, but not required to finish the current phase. Check items off or move them into the plan when prioritized.

---

## Mic path: wired + AirPods (adaptive)

**Status:** backlog  
**Added:** 2026-10-26  
**Related:** clarifications Q13 (AirPods Pro 3 as daily mic; Bluetooth allowed)

**Intent:** Support **both** wired/USB (or built-in) mics **and** AirPods Pro without forcing one path. At start (and in `doctor`), probe the selected input and adjust behavior.

**Possible approach:**

1. **Classify** the active `mic_device` (Core Audio / avfoundation): built-in, USB/wired, Bluetooth headset (AirPods).
2. **Per class defaults** for capture and mixdown, e.g.:
   - expected sample rate / resample strategy
   - sync tolerance (stricter for wired, looser for Bluetooth/HFP)
   - latency bias or measured offset from a short calibration beep (optional)
3. **Soft guidance** in `doctor`: report class + recommended settings; warn on Bluetooth quality without blocking.
4. **Config override:** allow manual `mic_class` or sync/latency knobs if auto-detect is wrong.
5. **Re-probe** if the device disappears/reconnects mid-session (AirPods common); fail clearly or retarget by name.

**v1 minimum (already decided):** AirPods must work; do not hard-block Bluetooth.  
**This backlog item:** make wired and AirPods **both** first-class via probe-and-adjust, not AirPods-only assumptions.

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
