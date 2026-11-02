"""CallScribe Typer CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import typer

from callscribe import __version__
from callscribe.config import load_config, write_defaults
from callscribe.devices import list_microphones, resolve_mic_device
from callscribe.doctor import run_doctor
from callscribe.paths import ensure_home, ensure_output_dir, expand, new_session_dir
from callscribe.recorder import run_recorder, spawn_detached_recorder
from callscribe.session import load_meta, new_meta, save_meta
from callscribe.state import (
    RecorderState,
    get_live_recorder,
    get_live_transcribe,
    signal_recorder_stop,
    write_recorder_state,
)

app = typer.Typer(
    name="callscribe",
    help="Local macOS call recorder + local speaker-labeled transcript.",
    no_args_is_help=True,
    add_completion=False,
)


def _err(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.RED, err=True)


def _ok(msg: str) -> None:
    typer.echo(msg)


@app.command("setup")
def setup_cmd() -> None:
    """Create config dirs; check ffmpeg; warm Whisper weights if possible."""
    ensure_home()
    cfg_path = write_defaults()
    cfg = load_config()
    out = ensure_output_dir(cfg.output_dir_path())
    _ok(f"Wrote defaults if missing: {cfg_path}")
    _ok(f"Session folder: {out}")
    if not shutil.which("ffmpeg"):
        _err("ffmpeg not found. Install with: brew install ffmpeg")
        raise typer.Exit(1)
    _ok(f"ffmpeg: {shutil.which('ffmpeg')}")
    try:
        import mlx_whisper
    except ImportError:
        _err("mlx-whisper not installed. Run: uv sync")
        raise typer.Exit(1) from None
    _ok("mlx-whisper: import OK")
    # Allow network during setup only — warm the configured Whisper weights.
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        os.environ.pop(key, None)
    import tempfile
    from pathlib import Path as _P

    with tempfile.TemporaryDirectory() as tmp:
        silent = _P(tmp) / "silent.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=16000:cl=mono",
                "-t",
                "1",
                str(silent),
            ],
            check=True,
            capture_output=True,
        )
        _ok(f"Downloading/warming Whisper: {cfg.whisper_model}")
        mlx_whisper.transcribe(
            str(silent),
            path_or_hf_repo=cfg.whisper_model,
            word_timestamps=False,
        )
    _ok("Setup OK for Phase 2 (ASR). pyannote download arrives in Phase 3–4.")


@app.command("doctor")
def doctor_cmd() -> None:
    """Check permissions with a short system + mic capture."""
    raise typer.Exit(run_doctor())


@app.command("devices")
def devices_cmd() -> None:
    """List microphone devices (ffmpeg avfoundation)."""
    try:
        devices = list_microphones()
    except Exception as e:
        _err(str(e))
        raise typer.Exit(1) from e
    if not devices:
        _err("No audio input devices found.")
        raise typer.Exit(1)
    cfg = load_config()
    resolved = None
    try:
        resolved = resolve_mic_device(cfg.mic_device)
    except RuntimeError:
        pass
    for d in devices:
        mark = " ← config" if resolved and d.index == resolved.index else ""
        typer.echo(f"[{d.index}] {d.name}{mark}")


@app.command("start")
def start_cmd(
    title: str | None = typer.Option(None, "--title", help="Optional session title"),
) -> None:
    """Start a detached dual-track recording session."""
    ensure_home()
    cfg = load_config()
    ensure_output_dir(cfg.output_dir_path())
    live = get_live_recorder()
    if live:
        _err(f"Already recording (pid {live.pid}): {live.session_dir}")
        raise typer.Exit(1)

    try:
        resolve_mic_device(cfg.mic_device)
    except RuntimeError as e:
        _err(str(e))
        raise typer.Exit(1) from e

    session_dir = new_session_dir(cfg.output_dir_path(), title)
    meta = new_meta(
        title=title,
        capture=cfg.capture,
        mic_device=cfg.mic_device,
        keep_raw_tracks=cfg.keep_raw_tracks,
        tool_versions={"callscribe": __version__},
    )
    save_meta(session_dir, meta)

    pid = spawn_detached_recorder(session_dir)
    write_recorder_state(RecorderState(pid=pid, session_dir=str(session_dir)))
    _ok(f"Recording started (pid {pid})")
    _ok(str(session_dir))


@app.command("stop")
def stop_cmd() -> None:
    """Stop the active recorder (graceful SIGTERM → mixdown)."""
    live = get_live_recorder()
    if not live:
        _err("Not recording.")
        raise typer.Exit(1)
    try:
        signal_recorder_stop(live)
    except ProcessLookupError:
        _err("Recorder process already exited; clearing state.")
        from callscribe.state import clear_recorder_state

        clear_recorder_state()
        raise typer.Exit(1) from None
    _ok(f"Stop signaled for pid {live.pid} ({live.session_dir})")
    _ok("Wait a few seconds for mixdown; check `callscribe status` / meta.json.")


@app.command("toggle")
def toggle_cmd(
    title: str | None = typer.Option(None, "--title"),
) -> None:
    """Start if idle, stop if recording (for Shortcuts / Raycast)."""
    if get_live_recorder():
        stop_cmd()
    else:
        start_cmd(title=title)


@app.command("status")
def status_cmd() -> None:
    """Show idle / recording / transcribing."""
    rec = get_live_recorder()
    tr = get_live_transcribe()
    if rec:
        meta = None
        try:
            meta = load_meta(Path(rec.session_dir))
        except OSError:
            pass
        elapsed = ""
        if meta and meta.me_start_utc:
            from datetime import UTC, datetime

            try:
                start = datetime.fromisoformat(meta.me_start_utc)
                elapsed = f" elapsed={ (datetime.now(UTC) - start).total_seconds():.0f}s"
            except ValueError:
                pass
        _ok(f"recording pid={rec.pid}{elapsed}")
        _ok(rec.session_dir)
        return
    if tr:
        _ok(f"transcribing pid={tr.pid}")
        _ok(tr.session_dir)
        return
    _ok("idle")


def _resolve_session_dir(target: Path) -> Path:
    cfg = load_config()
    ensure_output_dir(cfg.output_dir_path())
    path = expand(target)
    if path.is_file() and path.name == "call.wav":
        session_dir = path.parent
    elif path.is_dir():
        session_dir = path
    else:
        _err(f"Session not found: {path}")
        _err(
            "Use a real session folder from `callscribe list` "
            "(names look like 2026-11-02_1317_my-call — "
            "YYYY-MM-DD_HHMM in the docs is only a placeholder)."
        )
        _err(f"Sessions live under: {cfg.output_dir_path()}")
        raise typer.Exit(1)
    if not (session_dir / "meta.json").exists():
        _err(f"Missing meta.json in {session_dir}")
        _err("Record first with `callscribe start`, then `stop`.")
        raise typer.Exit(1)
    return session_dir


@app.command("transcribe")
def transcribe_cmd(
    target: Path = typer.Argument(..., help="Session directory or call.wav"),
    language: str | None = typer.Option(
        None, "--language", help="Language code (default: config / auto)"
    ),
    speakers: int | None = typer.Option(
        None, "--speakers", help="Exact remote speaker count for diarization"
    ),
    min_speakers: int | None = typer.Option(None, "--min-speakers"),
    max_speakers: int | None = typer.Option(None, "--max-speakers"),
    foreground: bool = typer.Option(
        False,
        "--foreground",
        help="Run in this process instead of detaching",
    ),
) -> None:
    """Run ASR + diarization pipeline (Me + SPEAKER_XX on remote)."""
    from callscribe.pipeline import run_pipeline
    from callscribe.spawn_transcribe import spawn_detached_transcribe

    cfg = load_config()
    session_dir = _resolve_session_dir(target)

    live = get_live_transcribe()
    if live and Path(live.session_dir).resolve() != session_dir.resolve():
        _err(f"Transcription already running (pid {live.pid}): {live.session_dir}")
        raise typer.Exit(1)

    needs_fg = foreground or any(
        x is not None for x in (language, speakers, min_speakers, max_speakers)
    )
    if needs_fg:
        _ok(f"Transcribing {session_dir} …")
        raise typer.Exit(
            run_pipeline(
                session_dir,
                cfg=cfg,
                language=language,
                num_speakers=speakers,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )
        )

    try:
        pid = spawn_detached_transcribe(session_dir)
    except RuntimeError as e:
        _err(str(e))
        raise typer.Exit(1) from e
    _ok(f"Transcription started (pid {pid})")
    _ok(str(session_dir))


@app.command("rename")
def rename_cmd(
    session_dir: Path = typer.Argument(..., help="Session directory"),
    mappings: list[str] = typer.Argument(
        ...,
        help='Mappings like SPEAKER_00=Alice SPEAKER_01=Bob',
    ),
) -> None:
    """Update speakers.json and re-render transcript.md (no ASR)."""
    from callscribe.pipeline import re_render_transcript

    path = _resolve_session_dir(session_dir)
    parsed: dict[str, str] = {}
    for item in mappings:
        if "=" not in item:
            _err(f"Expected SPEAKER_00=Name, got: {item}")
            raise typer.Exit(1)
        key, val = item.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if not key or not val:
            _err(f"Bad mapping: {item}")
            raise typer.Exit(1)
        parsed[key] = val

    speakers_path = path / "speakers.json"
    existing: dict[str, str] = {}
    if speakers_path.exists():
        existing = json.loads(speakers_path.read_text(encoding="utf-8"))
    existing.update(parsed)
    speakers_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    re_render_transcript(path)
    _ok(f"Updated {speakers_path}")
    _ok(f"Re-rendered {path / 'transcript.md'}")


@app.command("list")
def list_cmd() -> None:
    """List sessions under output_dir (Phase 4 polish; basic listing now)."""
    cfg = load_config()
    root = ensure_output_dir(cfg.output_dir_path())
    sessions = sorted(
        [p for p in root.iterdir() if p.is_dir() and (p / "meta.json").exists()],
        reverse=True,
    )
    if not sessions:
        _ok(f"(no sessions yet in {root})")
        return
    for s in sessions:
        try:
            meta = load_meta(s)
            dur = f"{meta.duration_s:.0f}s" if meta.duration_s else "?"
            _ok(f"{s.name}  status={meta.status}  duration={dur}")
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            _ok(f"{s.name}  (unreadable meta)")


@app.command("_recorder", hidden=True)
def recorder_cmd(
    session_dir: Path = typer.Argument(..., help="Session directory"),
) -> None:
    """Internal: detached recorder process."""
    raise typer.Exit(run_recorder(expand(session_dir)))


@app.command("_transcribe", hidden=True)
def transcribe_worker_cmd(
    session_dir: Path = typer.Argument(..., help="Session directory"),
) -> None:
    """Internal: detached transcription process."""
    from callscribe.pipeline import run_pipeline

    raise typer.Exit(run_pipeline(expand(session_dir)))


def version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit(0)


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    return


def main() -> None:
    app()


if __name__ == "__main__":
    main()
