"""Hardened one-time setup (the only command allowed to use the network).

Warms Whisper + pyannote into the Hugging Face Hub cache. Transcription later
sets ``HF_HUB_OFFLINE`` and must not download. Errors include fix hints
(ffmpeg, token, gated license).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from callscribe.config import load_config, write_defaults
from callscribe.diarize import COMMUNITY_MODEL
from callscribe.hf_token import load_hf_token
from callscribe.logging_util import log_exception, log_line
from callscribe.paths import ensure_home, ensure_output_dir, models_dir


class SetupError(RuntimeError):
    """User-facing setup failure with fix hint already in the message."""


def run_setup(*, echo) -> None:
    """Perform setup. `echo` is a callable like typer.echo / print."""

    def ok(msg: str) -> None:
        echo(msg)
        log_line("setup", msg)

    def fail(msg: str) -> None:
        log_line("setup", msg, level="ERROR")
        raise SetupError(msg)

    ensure_home()
    cfg_path = write_defaults()
    cfg = load_config()
    out = ensure_output_dir(cfg.output_dir_path())
    models_dir().mkdir(parents=True, exist_ok=True)

    ok(f"Config: {cfg_path}")
    ok(f"Sessions: {out}")
    ok(f"Logs: {ensure_home() / 'logs'}")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        fail("ffmpeg not found on PATH. Install with: brew install ffmpeg")
    ok(f"ffmpeg: {ffmpeg}")

    try:
        import mlx_whisper
    except ImportError as e:
        fail(f"mlx-whisper not installed ({e}). Run: uv sync")

    token = load_hf_token()
    if not token:
        fail(
            "Hugging Face token missing. Create a Read token at "
            "https://huggingface.co/settings/tokens , accept the model terms at "
            f"https://huggingface.co/{COMMUNITY_MODEL} , then either:\n"
            "  export HF_TOKEN=hf_...\n"
            "or put the token in a gitignored .hf_token file at the repo root."
        )
    ok("HF token: present (not printed)")

    # Setup may use the network
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        os.environ.pop(key, None)
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    with tempfile.TemporaryDirectory(prefix="callscribe-setup-") as tmp:
        silent = Path(tmp) / "silent.wav"
        proc = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=16000:cl=mono",
                "-t",
                "1",
                str(silent),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            fail(f"ffmpeg failed to create test audio: {(proc.stderr or '')[-400:]}")

        ok(f"Warming Whisper: {cfg.whisper_model}")
        try:
            mlx_whisper.transcribe(
                str(silent),
                path_or_hf_repo=cfg.whisper_model,
                word_timestamps=False,
            )
        except Exception as e:
            log_exception("setup", "Whisper download/warm failed", e)
            fail(
                f"Could not download/run Whisper model {cfg.whisper_model}: {e}. "
                "Check network access and the model id in config.toml."
            )
        ok("Whisper: OK")

        ok(f"Loading pyannote: {COMMUNITY_MODEL}")
        try:
            from pyannote.audio import Pipeline

            pipe = Pipeline.from_pretrained(COMMUNITY_MODEL, token=token)
            if pipe is None:
                fail(
                    f"pyannote returned no pipeline. Accept the gated license at "
                    f"https://huggingface.co/{COMMUNITY_MODEL} and ensure the token "
                    "can access gated repos."
                )
            del pipe
        except Exception as e:
            log_exception("setup", "pyannote download failed", e)
            err = str(e).lower()
            if "403" in err or "401" in err or "gated" in err or "restricted" in err:
                fail(
                    f"Cannot access gated model {COMMUNITY_MODEL}. "
                    "Open that page while logged in, accept the user conditions, "
                    "and use a valid HF token with access to gated repos."
                )
            fail(f"pyannote setup failed: {e}")
        ok("pyannote: OK (Hub cache)")

    hub_cache = _hub_cache_dir()
    ok(f"Model cache (canonical offline store): {hub_cache}")
    dest = cfg.diarization_dir_path()
    dest.mkdir(parents=True, exist_ok=True)
    marker = dest / "README.txt"
    marker.write_text(
        f"CallScribe loads pyannote from the Hugging Face Hub cache by default "
        f"({COMMUNITY_MODEL}).\n"
        f"Hub cache: {hub_cache}\n\n"
        "Optional override: place a full local snapshot here (must include "
        "config.yaml). Then set diarization_dir in config.toml to this path.\n",
        encoding="utf-8",
    )
    ok(
        f"Optional local diarization override dir: {dest} "
        "(unused unless it contains config.yaml)"
    )
    ok("Setup complete. Transcription can run offline after this.")


def _hub_cache_dir() -> Path:
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        return Path(HF_HUB_CACHE).expanduser()
    except Exception:
        return Path("~/.cache/huggingface/hub").expanduser()
