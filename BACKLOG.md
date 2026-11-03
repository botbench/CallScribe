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

**Status:** done (2026-11-03)  
**Added:** 2026-11-02  

**Shipped:**
- `confidence` block on `transcript.json` (`level`, mean/median word `p`, `low_p_ratio`, `warning`, note)
- Line under the title in `transcript.md`; short `· ASR high|medium|low` on the completion notification
- Explicit note: ASR word-probability sanity only — not speaker-label accuracy

**Still optional later:** fold segment `avg_logprob` / `compression_ratio` into the score; config-tunable thresholds.

---

## (empty — add more items below)
