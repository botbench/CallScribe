---
name: callscribe-summarize
description: >-
  Privacy-first summarization of CallScribe session transcripts into summary.md
  and action items. Prefer Apple on-device Foundation Models (`fm --model system`);
  never upload transcript text to cloud LLMs unless the user explicitly opts in.
  Use when the user asks to summarise/summarize a call, extract todos/action items,
  or produce a meeting notes file from a CallScribe transcript.
---

# CallScribe summarize (privacy-first)

Separate layer from CallScribe record/transcribe. Input is an existing session
`transcript.md` (and optional `transcript.json`). Output stays on disk next to
the session. Do **not** invent session paths — resolve via `callscribe list`.

**Skill install (humans):** project copy at `.cursor/skills/callscribe-summarize/`;
`uv run callscribe setup` also installs/refreshes the personal copy at
`~/.cursor/skills/callscribe-summarize/`.

## Privacy hard rules

1. **Default backend: on-device only.** Prefer Apple Foundation Models via
   `/usr/bin/fm` with **`--model system`** (on-device). Do not pass `--model pcc`
   unless the user explicitly opts into Private Cloud Compute.
2. **Do not paste the full transcript into the Cursor chat** for the model to
   rewrite. That can leave the device depending on Cursor privacy mode. Prefer
   shelling out to `fm` with the transcript on disk; show the user only the
   short summary/actions result (or the written file paths).
3. **Never** send transcript text to third-party cloud APIs (OpenAI, Anthropic,
   Gemini, etc.) unless the user explicitly asks for that backend.
4. **Never** commit summaries that contain sensitive call content unless the
   user asks. Session dirs under `~/CallScribe` are local by default.
5. If on-device backends are unavailable, **stop and say so** — offer local
   fallbacks (below). Do not silently fall through to a cloud model.

## Apple on-device AI (investigation)

On recent macOS (this project targets Apple Silicon; Foundation Models CLI
ships as `/usr/bin/fm` on sufficiently new OS builds):

| Piece | Role |
|---|---|
| `fm` CLI | Scriptable on-device (and optional PCC) generation |
| `--model system` | **On-device** Apple Foundation Model — default; privacy-first |
| `--model pcc` | Apple Private Cloud Compute — leaves device; Apple privacy claims, still not fully local |
| `fm count-tokens` | Size prompts before sending; use to plan chunking |
| `fm models` / `fm quota-usage` | Availability / quota |
| Writing Tools | System UI summarization in apps — not a good CLI pipeline |

**One-time legal gate:** first use requires accepting terms machine-wide:

```bash
sudo fm license
```

Then verify:

```bash
fm models
which fm   # expect /usr/bin/fm
```

If `fm` is missing or license is refused, use a **local** fallback (MLX/Ollama),
not cloud.

**Context limits:** on-device models are small. Always `fm count-tokens` on the
prompt+transcript; if oversized, **map-reduce**: summarize chunks → merge
chunk summaries → final `summary.md`. Prefer speaker-turn chunks from
`transcript.md`, not arbitrary mid-sentence splits.

## Resolve the session

```bash
uv run callscribe list
# or PATH: callscribe list
```

Session dir typically `~/CallScribe/<session_id>/` with `transcript.md`.
If only `SPEAKER_XX` labels exist, ask whether to `callscribe rename` first;
summaries are better with real names.

## Output files (write under the session dir)

| File | Contents |
|---|---|
| `summary.md` | Short meeting summary (see template) |
| `actions.md` | Action items / todos only (checkboxes) |

Do not overwrite without asking if either file already exists (unless the user
said “regenerate” / “overwrite”).

### `summary.md` template

```markdown
# Summary — <session_id or title>

- **When:** <from session id / metadata if known>
- **Participants:** <from speaker labels>
- **Backend:** Apple Foundation Models (on-device) | local mlx/ollama | …

## Overview
<5–10 sentences max>

## Key points
- …

## Decisions
- … (or “None explicit”)

## Open questions
- … (or “None”)
```

### `actions.md` template

```markdown
# Actions — <session_id or title>

- [ ] <owner, if known>: <task> — <due if mentioned>
```

Only include concrete, attributable actions. Do not invent owners or deadlines.

## Preferred backend: `fm` (on-device)

Instructions for the model (pass via `-i` / `--instructions`):

```text
You summarize a call transcript. Be factual and concise. Use only the
transcript; do not invent facts, names, or commitments. Prefer short bullets.
Separate decisions from action items. If something is unclear or low-
confidence ASR, say so briefly rather than guessing.
```

Example (adjust paths; keep transcript out of the Cursor prompt):

```bash
SESSION="$HOME/CallScribe/<session_id>"
TRANSCRIPT="$SESSION/transcript.md"

# Optional: size check (positional prompt; or --transcript for a saved fm chat file)
fm count-tokens "$(cat "$TRANSCRIPT")"

fm --model system respond \
  --no-stream \
  -i "You summarize a call transcript. Be factual and concise. Use only the transcript; do not invent facts, names, or commitments. Prefer short bullets. Separate decisions from action items." \
  --text "Summarize the following CallScribe transcript into: (1) Overview, (2) Key points, (3) Decisions, (4) Open questions. Then list action items as checkbox lines '- [ ] owner: task'." \
  --text "$(cat "$TRANSCRIPT")" \
  > "$SESSION/_fm_raw.md"
```

Then split `_fm_raw.md` into `summary.md` + `actions.md` (or run a second
`fm respond` pass that only extracts actions). Delete `_fm_raw.md` when done
if the user prefers a tidy session folder.

**Structured output:** `fm respond --schema …` may be used when a JSON schema
helps enforce sections; still write the final human-readable markdown files.

**PCC (opt-in only):**

```bash
fm --model pcc respond …   # only if user explicitly requested PCC
```

Label the Backend line in `summary.md` accordingly.

## Local fallbacks (still on-device)

If `fm` is unavailable (older macOS, license not accepted, model download
pending):

1. **Ollama** (if installed): `ollama run <local-model>` with the same
   instructions; keep the transcript on stdin/file, not in Cursor chat.
2. **MLX LM** / other local CLI the user already has — same privacy rules.
3. If nothing local works: report that and stop. Ask the user whether they
   want to accept `sudo fm license`, install a local model, or **explicitly**
   allow a cloud backend for this one session.

## Agent UX

- Confirm which session (id/title) before summarizing.
- Prefer writing files, then tell the user the paths and a short preview of
  actions — not a dump of the whole transcript.
- Cross-link: recording/transcribe/rename stays on the **callscribe** operator
  skill; this skill only summarizes existing transcripts.
- If the user asks for Notion/email export, treat that as a **separate,
  explicit** share step after local files exist.
