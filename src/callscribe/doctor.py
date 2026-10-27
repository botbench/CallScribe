"""Environment and permission checks."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import catap

from callscribe import __version__
from callscribe.audio_util import wav_info
from callscribe.config import load_config
from callscribe.devices import list_microphones, resolve_mic_device
from callscribe.paths import callscribe_home, config_path
from callscribe.recorder import host_app_hint


def _ffmpeg_version() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        return "NOT FOUND"
    proc = subprocess.run(
        [path, "-version"], capture_output=True, text=True, check=False
    )
    line = (proc.stdout or "").splitlines()[:1]
    return line[0] if line else path


def run_doctor(*, seconds: float = 3.0) -> int:
    """Print diagnostics; return 0 if both captures look non-silent."""
    cfg = load_config()
    host = host_app_hint()
    print(f"callscribe {__version__}")
    print(f"host app (permissions attach here): {host}")
    print(f"config: {config_path()}")
    print(f"home:   {callscribe_home()}")
    print(f"output: {cfg.output_dir_path()}")
    print(f"ffmpeg: {_ffmpeg_version()}")
    print(f"catap:  {getattr(catap, '__version__', '?')}")
    print(f"capture mode: {cfg.capture}")
    print(f"mic_device config: {cfg.mic_device}")

    mics = list_microphones()
    print("microphones:")
    for d in mics:
        print(f"  [{d.index}] {d.name}")

    try:
        mic = resolve_mic_device(cfg.mic_device)
        print(f"resolved mic: [{mic.index}] {mic.name}")
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

    if "WezTerm" in host or "wezterm" in host.lower():
        print(
            "WARNING: WezTerm often cannot prompt for System Audio Recording "
            "(missing NSAudioCaptureUsageDescription). Prefer Terminal.app for recording."
        )

    rc = 0
    with tempfile.TemporaryDirectory(prefix="callscribe-doctor-") as tmp:
        tmp_path = Path(tmp)
        remote = tmp_path / "remote.wav"
        me = tmp_path / "me.wav"

        print(f"\nRecording {seconds:.0f}s system/app audio…")
        try:
            if cfg.capture == "system":
                session = catap.record_system_audio(
                    output_path=str(remote),
                    exclude=list(cfg.exclude_apps) or (),
                )
            else:
                app = cfg.capture.split(":", 1)[1]
                session = catap.record_process(app, output_path=str(remote))
            session.start()
            time.sleep(seconds)
            session.stop()
            silent = session.captured_only_silence or (
                remote.exists() and wav_info(remote)["silent"]
            )
            info = wav_info(remote) if remote.exists() else {}
            print(
                f"  remote: silent={silent} peak={info.get('peak')} "
                f"rms={info.get('rms')} dur={info.get('duration_s')}"
            )
            if silent:
                print(
                    f"  FIX: Enable Screen & System Audio Recording for {host}, "
                    "then fully quit and reopen that app."
                )
                rc = 1
            session.close()
        except Exception as e:
            print(f"  remote FAILED: {e}")
            rc = 1

        print(f"Recording {seconds:.0f}s microphone [{mic.index}] {mic.name}…")
        print("  (speak now)")
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "avfoundation",
                "-i",
                f":{mic.index}",
                "-t",
                str(seconds),
                "-ac",
                "1",
                str(me),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0 or not me.exists():
            print(f"  mic FAILED (ffmpeg exit {proc.returncode})")
            print((proc.stderr or "")[-800:])
            rc = 1
        else:
            info = wav_info(me)
            print(
                f"  me: silent={info['silent']} peak={info['peak']} "
                f"rms={info['rms']} rate={info['rate']} dur={info['duration_s']}"
            )
            if info["silent"]:
                print(
                    f"  FIX: Enable Microphone for {host}, unmute the device, "
                    "and confirm AirPods/built-in with `callscribe devices`."
                )
                rc = 1

    if rc == 0:
        print("\ndoctor: OK")
    else:
        print("\ndoctor: problems found (see above)")
    return rc
