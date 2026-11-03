"""Load and validate ``~/.callscribe/config.toml``.

Defaults live in ``DEFAULT_TOML`` (written on first run). Unknown keys are
rejected so typos fail loudly. Hallucination thresholds stay in ``asr.py``.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from callscribe.paths import config_path, ensure_home, expand

DEFAULT_TOML = """\
output_dir        = "~/CallScribe"
my_name           = "Me"
mic_device        = "default"      # name from `callscribe devices`, or "default"
# Mic path profile: "auto" (from device name) or force airpods|bluetooth|builtin|usb|unknown
mic_class         = "auto"
# Optional overrides (omit / leave commented to use class defaults):
# mic_latency_bias_ms            = 100   # assume Me lags remote by N ms
# mixdown_duration_tolerance_s   = 2.0   # call.wav duration check slack
capture           = "system"       # "system" or "app:Firefox"
exclude_apps      = []             # only used when capture = "system"
language          = "auto"         # or "en", "fr", "nl", ...
whisper_model     = "mlx-community/whisper-large-v3-turbo"
# Optional local pyannote snapshot (config.yaml). Default: Hugging Face Hub cache.
diarization_dir   = "~/.callscribe/models/pyannote-speaker-diarization-community-1"
initial_prompt    = ""             # vocabulary hint for Whisper: names, acronyms
keep_raw_tracks   = true
auto_transcribe   = true
notify            = true
"""


@dataclass
class Config:
    output_dir: str = "~/CallScribe"
    my_name: str = "Me"
    mic_device: str = "default"
    mic_class: str = "auto"
    mic_latency_bias_ms: float | None = None
    mixdown_duration_tolerance_s: float | None = None
    capture: str = "system"
    exclude_apps: list[str] = field(default_factory=list)
    language: str = "auto"
    whisper_model: str = "mlx-community/whisper-large-v3-turbo"
    diarization_dir: str = "~/.callscribe/models/pyannote-speaker-diarization-community-1"
    initial_prompt: str = ""
    keep_raw_tracks: bool = True
    auto_transcribe: bool = True
    notify: bool = True

    def output_dir_path(self) -> Path:
        return expand(self.output_dir)

    def diarization_dir_path(self) -> Path:
        return expand(self.diarization_dir)


def _optional_float(data: dict[str, Any], key: str) -> float | None:
    if key not in data or data[key] is None:
        return None
    return float(data[key])


def _validate(data: dict[str, Any]) -> Config:
    from callscribe.mic_profile import VALID_MIC_CLASSES

    known = {f.name for f in Config.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    extra = set(data) - known
    if extra:
        raise ValueError(f"Unknown config keys: {sorted(extra)}")

    capture = str(data.get("capture", "system"))
    if capture != "system" and not capture.startswith("app:"):
        raise ValueError('capture must be "system" or "app:<Name>"')

    exclude = data.get("exclude_apps", [])
    if not isinstance(exclude, list) or not all(isinstance(x, str) for x in exclude):
        raise ValueError("exclude_apps must be a list of strings")

    mic_class = str(data.get("mic_class", "auto")).strip().lower() or "auto"
    if mic_class not in VALID_MIC_CLASSES:
        raise ValueError(
            f"mic_class must be one of {sorted(VALID_MIC_CLASSES)}, got {mic_class!r}"
        )

    bias = _optional_float(data, "mic_latency_bias_ms")
    tol = _optional_float(data, "mixdown_duration_tolerance_s")
    if tol is not None and tol <= 0:
        raise ValueError("mixdown_duration_tolerance_s must be > 0")

    cfg = Config(
        output_dir=str(data.get("output_dir", "~/CallScribe")),
        my_name=str(data.get("my_name", "Me")),
        mic_device=str(data.get("mic_device", "default")),
        mic_class=mic_class,
        mic_latency_bias_ms=bias,
        mixdown_duration_tolerance_s=tol,
        capture=capture,
        exclude_apps=list(exclude),
        language=str(data.get("language", "auto")),
        whisper_model=str(data.get("whisper_model", "mlx-community/whisper-large-v3-turbo")),
        diarization_dir=str(
            data.get(
                "diarization_dir",
                "~/.callscribe/models/pyannote-speaker-diarization-community-1",
            )
        ),
        initial_prompt=str(data.get("initial_prompt", "")),
        keep_raw_tracks=bool(data.get("keep_raw_tracks", True)),
        auto_transcribe=bool(data.get("auto_transcribe", True)),
        notify=bool(data.get("notify", True)),
    )
    return cfg


def write_defaults(path: Path | None = None) -> Path:
    ensure_home()
    path = path or config_path()
    if not path.exists():
        path.write_text(DEFAULT_TOML, encoding="utf-8")
    return path


def load_config(path: Path | None = None) -> Config:
    ensure_home()
    path = path or config_path()
    if not path.exists():
        write_defaults(path)
    raw = path.read_text(encoding="utf-8")
    data = tomllib.loads(raw)
    return _validate(data)


def config_as_dict(cfg: Config) -> dict[str, Any]:
    return asdict(cfg)
