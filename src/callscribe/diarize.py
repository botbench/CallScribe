"""pyannote speaker diarization (MPS with CPU fallback).

We use *exclusive* diarization (one speaker at a time) so word↔speaker alignment
is a simple interval overlap. MPS is preferred when it works; community-1 can
crash on Metal — fall back to CPU mid-run if inference fails.
"""

from __future__ import annotations

import gc
from pathlib import Path

from callscribe.hf_token import load_hf_token

COMMUNITY_MODEL = "pyannote/speaker-diarization-community-1"


def _load_pipeline(diarization_dir: Path):
    import torch
    from pyannote.audio import Pipeline

    token = load_hf_token()
    # Canonical path: Hub id → HF cache (offline after setup).
    # Optional override: local snapshot dir with config.yaml.
    source: str | Path
    if (diarization_dir / "config.yaml").exists():
        source = diarization_dir
    else:
        source = COMMUNITY_MODEL

    try:
        pipeline = Pipeline.from_pretrained(source, token=token)
    except Exception as e:
        hint = ""
        if token is None:
            hint = (
                " Set HF_TOKEN or place a token in the repo `.hf_token` file, "
                "and accept the model terms at "
                f"https://huggingface.co/{COMMUNITY_MODEL}"
            )
        raise RuntimeError(f"Failed to load diarization model from {source}: {e}.{hint}") from e

    if pipeline is None:
        raise RuntimeError(
            f"Could not load {source}. Accept the gated model license and provide HF_TOKEN."
        )

    device = "cpu"
    if torch.backends.mps.is_available():
        try:
            pipeline.to(torch.device("mps"))
            device = "mps"
        except Exception:
            pipeline.to(torch.device("cpu"))
            device = "cpu"
    else:
        pipeline.to(torch.device("cpu"))

    return pipeline, device


def diarize_wav(
    path: Path,
    *,
    diarization_dir: Path,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> tuple[list[tuple[float, float, str]], str]:
    """Return exclusive diarization turns `(start, end, SPEAKER_XX)` and device used."""
    pipeline, device = _load_pipeline(diarization_dir)

    kwargs: dict = {}
    if num_speakers is not None:
        kwargs["num_speakers"] = num_speakers
    else:
        if min_speakers is not None:
            kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            kwargs["max_speakers"] = max_speakers

    try:
        output = pipeline(str(path), **kwargs)
    except Exception:
        # MPS often fails late (embedding / Metal shaders); retry once on CPU.
        if device == "mps":
            import torch

            pipeline.to(torch.device("cpu"))
            device = "cpu"
            output = pipeline(str(path), **kwargs)
        else:
            raise

    turns: list[tuple[float, float, str]] = []
    # pyannote 4.x: exclusive_speaker_diarization is an Annotation (not 3.x API).
    for turn, _, speaker in output.exclusive_speaker_diarization.itertracks(yield_label=True):
        label = str(speaker)
        if not label.upper().startswith("SPEAKER"):
            label = f"SPEAKER_{label}" if label.isdigit() else label
        turns.append((float(turn.start), float(turn.end), label))

    # Models are large; free before Whisper loads in the same process.
    del output
    del pipeline
    gc.collect()
    try:
        import torch

        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except Exception:
        pass

    return turns, device
