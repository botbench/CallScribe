"""Background dual-track recorder (system/app tap + microphone)."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import catap

from callscribe import __version__
from callscribe.audio_util import is_silent_wav, wav_info
from callscribe.config import Config, load_config
from callscribe.devices import resolve_mic_device
from callscribe.mixdown import MixdownError, mixdown
from callscribe.notify import notify
from callscribe.session import load_meta, save_meta
from callscribe.state import clear_recorder_state


def host_app_hint() -> str:
    """Best-effort name of the app that owns TCC permissions for this capture."""
    # Prefer hint from the CLI that spawned the detached recorder.
    env_hint = os.environ.get("CALLSCRIBE_HOST_APP", "").strip()
    if env_hint:
        base = env_hint
    else:
        try:
            ppid = os.getppid()
            out = subprocess.run(
                ["ps", "-p", str(ppid), "-o", "comm="],
                capture_output=True,
                text=True,
                check=False,
            )
            name = (out.stdout or "").strip() or "the terminal app"
            base = Path(name).name
        except OSError:
            base = "the terminal app"
    if base in {"launchd", "init", "1"}:
        base = "Terminal (or the app that ran `callscribe start`)"
    if "WezTerm" in base or "wezterm" in base.lower():
        return (
            f"{base} (WezTerm often cannot prompt for System Audio Recording — "
            "prefer Terminal.app)"
        )
    return base


_SKIP_HOST_NAMES = {
    "python",
    "python3",
    "uv",
    "callscribe",
    "zsh",
    "-zsh",
    "bash",
    "-bash",
    "sh",
    "login",
    "login.exe",
}


def detect_host_app_for_cli() -> str:
    """Host app as seen from the interactive `callscribe start` process."""
    try:
        pid = os.getpid()
        for _ in range(8):
            out = subprocess.run(
                ["ps", "-p", str(pid), "-o", "ppid=,comm="],
                capture_output=True,
                text=True,
                check=False,
            )
            parts = (out.stdout or "").strip().split(None, 1)
            if len(parts) < 2:
                break
            ppid_s, comm = parts[0], parts[1]
            base = Path(comm).name
            if base.lower() not in _SKIP_HOST_NAMES and not base.startswith("-"):
                return base
            # Still useful: Terminal / iTerm / WezTerm even if weird naming
            low = base.lower()
            if any(x in low for x in ("terminal", "iterm", "wezterm", "cursor")):
                return base
            pid = int(ppid_s)
            if pid <= 1:
                break
    except (OSError, ValueError):
        pass
    return "Terminal (or the app that ran callscribe start)"


def _start_remote(cfg: Config, remote_path: Path):
    capture = cfg.capture
    if capture == "system":
        return catap.record_system_audio(
            output_path=str(remote_path),
            exclude=list(cfg.exclude_apps) or (),
        )
    if capture.startswith("app:"):
        app_name = capture.split(":", 1)[1].strip()
        if not app_name:
            raise RuntimeError('capture app: name is empty (use e.g. "app:Firefox")')
        return catap.record_process(app_name, output_path=str(remote_path))
    raise RuntimeError(f"Unsupported capture mode: {capture!r}")


def _start_mic(mic_index: int, me_path: Path) -> subprocess.Popen[str]:
    # avfoundation: "video:audio" — none for video, index for audio.
    return subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-f",
            "avfoundation",
            "-i",
            f":{mic_index}",
            "-ac",
            "1",
            str(me_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def run_recorder(session_dir: Path, cfg: Config | None = None) -> int:
    """Foreground recorder loop for `callscribe _recorder <session-dir>`."""
    cfg = cfg or load_config()
    session_dir = session_dir.resolve()
    me_path = session_dir / "me.wav"
    remote_path = session_dir / "remote.wav"
    call_path = session_dir / "call.wav"

    meta = load_meta(session_dir)
    host = host_app_hint()
    meta.host_app_hint = host
    meta.tool_versions = {
        "callscribe": __version__,
        "catap": getattr(catap, "__version__", "unknown"),
    }

    mic = resolve_mic_device(cfg.mic_device)
    meta.mic_device_resolved = f"{mic.index}:{mic.name}"

    stop_requested = False

    def _on_signal(signum: int, frame: object) -> None:  # noqa: ARG001
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    remote_session = None
    mic_proc: subprocess.Popen[str] | None = None

    try:
        remote_session = _start_remote(cfg, remote_path)
        t_remote_mono = time.monotonic()
        remote_session.start()
        meta.remote_start_utc = datetime.now(UTC).isoformat()
        meta.remote_start_monotonic = t_remote_mono

        mic_proc = _start_mic(mic.index, me_path)
        t_me_mono = time.monotonic()
        meta.me_start_utc = datetime.now(UTC).isoformat()
        meta.me_start_monotonic = t_me_mono
        meta.status = "recording"
        save_meta(session_dir, meta)

        while not stop_requested:
            if mic_proc.poll() is not None:
                err = ""
                if mic_proc.stderr:
                    err = mic_proc.stderr.read()[-500:]
                raise RuntimeError(
                    f"Microphone ffmpeg exited early (code {mic_proc.returncode}). {err}"
                )
            if remote_session.capture_failed:
                raise RuntimeError("System/app audio capture failed (catap).")
            time.sleep(0.2)

        # Graceful stop
        remote_session.stop()
        silence_remote = bool(remote_session.captured_only_silence)

        if mic_proc.poll() is None and mic_proc.stdin:
            try:
                mic_proc.stdin.write("q")
                mic_proc.stdin.flush()
            except BrokenPipeError:
                pass
            try:
                mic_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                mic_proc.terminate()
                mic_proc.wait(timeout=5)

        meta.stopped_utc = datetime.now(UTC).isoformat()
        if me_path.exists():
            meta.me_duration_s = float(wav_info(me_path)["duration_s"])
        if remote_path.exists():
            meta.remote_duration_s = float(wav_info(remote_path)["duration_s"])
            if not silence_remote:
                silence_remote = is_silent_wav(remote_path)

        if silence_remote or is_silent_wav(remote_path):
            meta.status = "failed"
            meta.error = (
                f"System/app audio recording looks silent. Grant "
                f'"Screen & System Audio Recording" to {host} in '
                f"System Settings → Privacy & Security, then restart that app. "
                f"(WezTerm often cannot show the prompt — use Terminal.app.)"
            )
            save_meta(session_dir, meta)
            notify("CallScribe", meta.error, enabled=cfg.notify)
            return 1

        if is_silent_wav(me_path):
            meta.status = "failed"
            meta.error = (
                f"Microphone track is silent ({meta.mic_device_resolved}). "
                f"Grant Microphone permission to {host}, check mute, and confirm "
                f"the device with `callscribe devices` (AirPods / built-in)."
            )
            save_meta(session_dir, meta)
            notify("CallScribe", meta.error, enabled=cfg.notify)
            return 1

        try:
            mixdown(me_path, remote_path, call_path, meta)
        except MixdownError as e:
            meta.status = "failed"
            meta.error = str(e)
            save_meta(session_dir, meta)
            notify("CallScribe", f"Mixdown failed: {e}", enabled=cfg.notify)
            return 1

        if call_path.exists():
            meta.duration_s = float(wav_info(call_path)["duration_s"])

        if not cfg.keep_raw_tracks:
            me_path.unlink(missing_ok=True)
            remote_path.unlink(missing_ok=True)

        # Phase 1: recording only. Full ASR pipeline arrives in Phase 2+.
        meta.status = "recorded"
        meta.error = None
        if cfg.auto_transcribe:
            # Leave a breadcrumb; do not spawn models yet.
            meta.tool_versions["auto_transcribe"] = "deferred-until-phase-2"
        save_meta(session_dir, meta)
        notify(
            "CallScribe",
            f"Recording saved ({meta.duration_s:.0f}s): {session_dir.name}",
            enabled=cfg.notify,
        )
        return 0

    except Exception as e:
        meta.status = "failed"
        meta.error = str(e)
        meta.stopped_utc = datetime.now(UTC).isoformat()
        save_meta(session_dir, meta)
        notify("CallScribe", f"Recording failed: {e}", enabled=cfg.notify)
        return 1
    finally:
        if mic_proc is not None and mic_proc.poll() is None:
            mic_proc.kill()
        if remote_session is not None:
            try:
                if remote_session.is_recording or remote_session.needs_cleanup:
                    remote_session.stop()
            except Exception:
                pass
            try:
                remote_session.close()
            except Exception:
                pass
        clear_recorder_state()


def spawn_detached_recorder(session_dir: Path) -> int:
    """Start `callscribe _recorder` as a detached process; return PID."""
    callscribe_bin = shutil.which("callscribe")
    if callscribe_bin:
        cmd = [callscribe_bin, "_recorder", str(session_dir)]
    else:
        cmd = [sys.executable, "-m", "callscribe", "_recorder", str(session_dir)]

    log_path = session_dir / "recorder.log"
    log_f = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "CALLSCRIBE_HOST_APP": detect_host_app_for_cli(),
    }
    proc = subprocess.Popen(
        cmd,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        cwd=str(session_dir),
        env=env,
    )
    # File handle kept open by child; parent can close its copy.
    log_f.close()
    return proc.pid
