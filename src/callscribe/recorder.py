"""Background dual-track recorder (system/app tap + microphone).

Runs as a detached process (``callscribe _recorder``). Captures in parallel:

* **remote** — Core Audio process tap via ``catap`` (system or one app)
* **me** — microphone via ``ffmpeg`` avfoundation

On SIGTERM: finalize both WAVs, reject silent tracks (usually missing TCC
permissions), mix down to stereo ``call.wav``, optionally spawn transcription.

macOS permissions attach to the *host app* that launched ``start`` (Terminal,
iTerm, …), not to the Python binary — see ``CALLSCRIBE_HOST_APP``.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import catap

from callscribe import __version__
from callscribe.audio_util import is_silent_wav, wav_info
from callscribe.config import Config, load_config
from callscribe.devices import MicDevice, resolve_mic_by_exact_name, resolve_mic_device
from callscribe.logging_util import log_exception, log_line
from callscribe.mic_profile import profile_tip, resolve_mic_profile
from callscribe.mixdown import MixdownError, mixdown
from callscribe.notify import notify
from callscribe.session import load_meta, save_meta
from callscribe.state import clear_recorder_state

# How long to wait for AirPods/USB to reappear after ffmpeg dies mid-call.
_MIC_REPROBE_WAIT_S = 5.0
_MIC_REPROBE_POLL_S = 0.5


def host_app_hint() -> str:
    """Best-effort name of the app that owns TCC permissions for this capture.

    Used in user-facing error text ("grant Microphone to Terminal.app").
    Prefers ``CALLSCRIBE_HOST_APP`` set by ``spawn_detached_recorder``; otherwise
    walks the parent process (often wrong once detached under launchd).
    """
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


# Process names to skip when walking parents from an interactive CLI.
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
    """Walk parents of the interactive ``start`` process to find Terminal/iTerm/etc.

    Result is passed into the detached recorder via ``CALLSCRIBE_HOST_APP``.
    """
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
    # avfoundation input is "video_index:audio_index"; empty video = mic only.
    # stdin kept open so we can send "q" for a clean WAV header on stop.
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


def _stop_mic_gracefully(mic_proc: subprocess.Popen[str] | None) -> None:
    if mic_proc is None or mic_proc.poll() is not None:
        return
    if mic_proc.stdin:
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


def _concat_wavs(parts: list[Path], out: Path) -> None:
    """Concatenate mono mic segments (AirPods reconnect) into ``me.wav``."""
    if not parts:
        raise RuntimeError("No microphone segments to concatenate")
    if len(parts) == 1:
        if parts[0].resolve() != out.resolve():
            out.unlink(missing_ok=True)
            parts[0].replace(out)
        return
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    list_file = out.parent / "me_concat.txt"
    list_file.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in parts),
        encoding="utf-8",
    )
    staged = out.parent / "me_concat_out.wav"
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(staged),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    list_file.unlink(missing_ok=True)
    if proc.returncode != 0 or not staged.exists():
        raise RuntimeError(
            "Failed to concatenate mic segments after reconnect:\n"
            + (proc.stderr or "")[-800:]
        )
    out.unlink(missing_ok=True)
    staged.replace(out)
    for p in parts:
        if p.resolve() != out.resolve():
            p.unlink(missing_ok=True)


def _reprobe_mic_by_name(
    mic_name: str,
    *,
    wait_s: float = _MIC_REPROBE_WAIT_S,
    should_abort: Callable[[], bool] | None = None,
) -> MicDevice:
    """Wait briefly for a disconnected mic (AirPods) to reappear under the same name."""
    deadline = time.monotonic() + wait_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        if should_abort and should_abort():
            raise RuntimeError(
                f"Stop requested while waiting for microphone {mic_name!r} to reconnect."
            )
        try:
            return resolve_mic_by_exact_name(mic_name)
        except RuntimeError as e:
            last_err = e
            time.sleep(_MIC_REPROBE_POLL_S)
    raise RuntimeError(
        f"Microphone {mic_name!r} disappeared mid-recording and did not return "
        f"within {wait_s:.0f}s. Reconnect AirPods/USB, then `callscribe start` again. "
        f"({last_err})"
    )


def run_recorder(session_dir: Path, cfg: Config | None = None) -> int:
    """Foreground recorder loop for ``callscribe _recorder <session-dir>``."""
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
    profile = resolve_mic_profile(mic, cfg)
    meta.mic_device_resolved = f"{mic.index}:{mic.name}"
    meta.mic_name = mic.name
    meta.mic_class = profile.mic_class
    meta.me_latency_bias_ms = profile.me_latency_bias_ms
    meta.mixdown_duration_tolerance_s = profile.duration_tolerance_s
    log_line("recorder", f"mic profile: {profile_tip(profile)}")

    stop_requested = False

    def _on_signal(signum: int, frame: object) -> None:  # noqa: ARG001
        # ``stop`` sends SIGTERM; do not exit immediately — finalize WAVs below.
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    remote_session = None
    mic_proc: subprocess.Popen[str] | None = None
    # Segmented mic capture so AirPods can reconnect at a new avfoundation index.
    me_parts: list[Path] = []
    me_part_i = 1

    try:
        # Start both tracks as close together as possible; timestamps feed adelay.
        remote_session = _start_remote(cfg, remote_path)
        t_remote_mono = time.monotonic()
        remote_session.start()
        meta.remote_start_utc = datetime.now(UTC).isoformat()
        meta.remote_start_monotonic = t_remote_mono

        part = session_dir / f"me_{me_part_i:03d}.wav"
        me_part_i += 1
        me_parts.append(part)
        mic_proc = _start_mic(mic.index, part)
        t_me_mono = time.monotonic()
        meta.me_start_utc = datetime.now(UTC).isoformat()
        meta.me_start_monotonic = t_me_mono
        meta.status = "recording"
        save_meta(session_dir, meta)

        while not stop_requested:
            if mic_proc.poll() is not None:
                err = ""
                if mic_proc.stderr:
                    err = (mic_proc.stderr.read() or "")[-500:]
                log_line(
                    "recorder",
                    f"mic ffmpeg exited (code {mic_proc.returncode}); "
                    f"re-probing {mic.name!r}. {err}",
                    level="ERROR",
                )
                mic = _reprobe_mic_by_name(
                    mic.name,
                    should_abort=lambda: stop_requested,
                )
                # Class can change if the same name is unlikely; refresh profile lightly.
                profile = resolve_mic_profile(mic, cfg)
                meta.mic_device_resolved = f"{mic.index}:{mic.name}"
                meta.mic_class = profile.mic_class
                meta.me_latency_bias_ms = profile.me_latency_bias_ms
                meta.mixdown_duration_tolerance_s = profile.duration_tolerance_s
                save_meta(session_dir, meta)
                part = session_dir / f"me_{me_part_i:03d}.wav"
                me_part_i += 1
                me_parts.append(part)
                mic_proc = _start_mic(mic.index, part)
                log_line(
                    "recorder",
                    f"mic reconnected at [{mic.index}] {mic.name} → {part.name}",
                )
                notify(
                    "CallScribe",
                    f"Mic reconnected: {mic.name}",
                    enabled=cfg.notify,
                )
            # Property (not a method) — True if the Core Audio tap failed mid-run.
            if remote_session.capture_failed:
                raise RuntimeError("System/app audio capture failed (catap).")
            time.sleep(0.2)

        remote_session.stop()
        silence_remote = bool(remote_session.captured_only_silence)

        _stop_mic_gracefully(mic_proc)
        mic_proc = None
        _concat_wavs(me_parts, me_path)
        me_parts = []

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
            log_line("recorder", meta.error, level="ERROR")
            notify("CallScribe", meta.error, enabled=cfg.notify)
            return 1

        if is_silent_wav(me_path):
            meta.status = "failed"
            meta.error = (
                f"Microphone track is silent ({meta.mic_device_resolved}, "
                f"class={meta.mic_class}). "
                f"Grant Microphone permission to {host}, check mute, and confirm "
                f"the device with `callscribe devices` (AirPods / built-in)."
            )
            save_meta(session_dir, meta)
            log_line("recorder", meta.error, level="ERROR")
            notify("CallScribe", meta.error, enabled=cfg.notify)
            return 1

        try:
            mixdown(me_path, remote_path, call_path, meta)
        except MixdownError as e:
            meta.status = "failed"
            meta.error = str(e)
            save_meta(session_dir, meta)
            log_exception("recorder", "mixdown failed", e)
            notify("CallScribe", f"Mixdown failed: {e}", enabled=cfg.notify)
            return 1

        if call_path.exists():
            meta.duration_s = float(wav_info(call_path)["duration_s"])

        if not cfg.keep_raw_tracks:
            me_path.unlink(missing_ok=True)
            remote_path.unlink(missing_ok=True)

        meta.status = "recorded"
        meta.error = None
        save_meta(session_dir, meta)
        log_line(
            "recorder",
            f"recorded {session_dir.name} duration_s={meta.duration_s}",
        )
        notify(
            "CallScribe",
            f"Recording saved ({meta.duration_s:.0f}s): {session_dir.name}",
            enabled=cfg.notify,
        )

        if cfg.auto_transcribe:
            try:
                from callscribe.spawn_transcribe import spawn_detached_transcribe

                tpid = spawn_detached_transcribe(session_dir)
                notify(
                    "CallScribe",
                    f"Transcribing in background (pid {tpid})",
                    enabled=cfg.notify,
                )
            except RuntimeError as e:
                # e.g. another transcription already running
                notify("CallScribe", str(e), enabled=cfg.notify)
        return 0

    except Exception as e:
        meta.status = "failed"
        meta.error = str(e)
        meta.stopped_utc = datetime.now(UTC).isoformat()
        save_meta(session_dir, meta)
        log_exception("recorder", f"failed {session_dir.name}", e)
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
    """Start ``callscribe _recorder`` in a new session; return PID.

    ``start_new_session=True`` detaches from the controlling terminal so the
    interactive CLI can exit while recording continues.
    """
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
    # Child inherits the open FD; closing the parent's copy is fine.
    log_f.close()
    return proc.pid
