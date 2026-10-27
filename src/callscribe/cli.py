"""CallScribe Typer CLI."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer

from callscribe import __version__
from callscribe.config import load_config, write_defaults
from callscribe.devices import list_microphones, resolve_mic_device
from callscribe.doctor import run_doctor
from callscribe.mixdown import MixdownError, mixdown
from callscribe.paths import ensure_home, expand, new_session_dir
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
    help="Local macOS call recorder (Phase 1: recording + mixdown).",
    no_args_is_help=True,
    add_completion=False,
)


def _err(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.RED, err=True)


def _ok(msg: str) -> None:
    typer.echo(msg)


@app.command("setup")
def setup_cmd() -> None:
    """Create config dirs; check ffmpeg. (Model download → Phase 4 / optional extras.)"""
    ensure_home()
    cfg_path = write_defaults()
    _ok(f"Wrote defaults if missing: {cfg_path}")
    if not shutil.which("ffmpeg"):
        _err("ffmpeg not found. Install with: brew install ffmpeg")
        raise typer.Exit(1)
    _ok(f"ffmpeg: {shutil.which('ffmpeg')}")
    _ok(
        "Phase 1 setup OK. Whisper/pyannote download comes with "
        "`pip/uv` extras + Phase 2–4 `setup`."
    )


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


@app.command("transcribe")
def transcribe_cmd(
    target: Path = typer.Argument(..., help="Session directory or call.wav"),
) -> None:
    """Phase 1: recover call.wav via mixdown if raw tracks exist. (Full ASR → Phase 2.)"""
    path = expand(target)
    if path.is_file() and path.name == "call.wav":
        session_dir = path.parent
    elif path.is_dir():
        session_dir = path
    else:
        _err(f"Not a session dir or call.wav: {path}")
        raise typer.Exit(1)

    call = session_dir / "call.wav"
    me = session_dir / "me.wav"
    remote = session_dir / "remote.wav"
    if call.exists():
        _ok(f"Already have {call}")
        _ok("Full transcription pipeline lands in Phase 2.")
        return
    if not (me.exists() and remote.exists()):
        _err("Missing call.wav and raw tracks (me.wav / remote.wav).")
        raise typer.Exit(1)

    meta = load_meta(session_dir)
    try:
        mixdown(me, remote, call, meta)
    except MixdownError as e:
        _err(str(e))
        raise typer.Exit(1) from e
    meta.status = "recorded"
    save_meta(session_dir, meta)
    _ok(f"Recovered {call}")
    _ok("Full transcription pipeline lands in Phase 2.")


@app.command("list")
def list_cmd() -> None:
    """List sessions under output_dir (Phase 4 polish; basic listing now)."""
    cfg = load_config()
    root = cfg.output_dir_path()
    if not root.exists():
        _ok("(no sessions yet)")
        return
    sessions = sorted(
        [p for p in root.iterdir() if p.is_dir() and (p / "meta.json").exists()],
        reverse=True,
    )
    if not sessions:
        _ok("(no sessions yet)")
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
