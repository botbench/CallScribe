"""Load and validate ~/.callscribe/config.toml."""

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
capture           = "system"       # "system" or "app:Firefox"
exclude_apps      = []             # only used when capture = "system"
language          = "auto"         # or "en", "fr", "nl", ...
whisper_model     = "mlx-community/whisper-large-v3-turbo"
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


def _validate(data: dict[str, Any]) -> Config:
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

    cfg = Config(
        output_dir=str(data.get("output_dir", "~/CallScribe")),
        my_name=str(data.get("my_name", "Me")),
        mic_device=str(data.get("mic_device", "default")),
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
