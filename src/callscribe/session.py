"""Session folder metadata (meta.json)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

Status = Literal["recording", "recorded", "transcribing", "done", "failed"]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class SessionMeta:
    version: int = 1
    status: Status = "recording"
    title: str | None = None
    created_local: str = ""
    created_utc: str = ""
    me_start_utc: str | None = None
    remote_start_utc: str | None = None
    me_start_monotonic: float | None = None
    remote_start_monotonic: float | None = None
    stopped_utc: str | None = None
    duration_s: float | None = None
    me_duration_s: float | None = None
    remote_duration_s: float | None = None
    capture: str = "system"
    mic_device: str = "default"
    mic_device_resolved: str | None = None
    keep_raw_tracks: bool = True
    error: str | None = None
    tool_versions: dict[str, str] = field(default_factory=dict)
    host_app_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMeta:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def meta_path(session_dir: Path) -> Path:
    return session_dir / "meta.json"


def load_meta(session_dir: Path) -> SessionMeta:
    path = meta_path(session_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    return SessionMeta.from_dict(data)


def save_meta(session_dir: Path, meta: SessionMeta) -> None:
    path = meta_path(session_dir)
    path.write_text(json.dumps(meta.to_dict(), indent=2) + "\n", encoding="utf-8")


def new_meta(
    *,
    title: str | None,
    capture: str,
    mic_device: str,
    keep_raw_tracks: bool,
    tool_versions: dict[str, str] | None = None,
) -> SessionMeta:
    local = datetime.now().isoformat(timespec="seconds")
    return SessionMeta(
        status="recording",
        title=title,
        created_local=local,
        created_utc=_utc_now_iso(),
        capture=capture,
        mic_device=mic_device,
        keep_raw_tracks=keep_raw_tracks,
        tool_versions=tool_versions or {},
    )


def start_delay_seconds(meta: SessionMeta) -> tuple[float, float]:
    """Return (me_delay_ms, remote_delay_ms) for ffmpeg adelay.

    The track that started later gets a positive delay so timelines align.
    Prefer monotonic clocks; fall back to UTC ISO timestamps.
    """
    if (
        meta.me_start_monotonic is not None
        and meta.remote_start_monotonic is not None
    ):
        delta = meta.me_start_monotonic - meta.remote_start_monotonic
    elif meta.me_start_utc and meta.remote_start_utc:
        me = datetime.fromisoformat(meta.me_start_utc)
        remote = datetime.fromisoformat(meta.remote_start_utc)
        delta = (me - remote).total_seconds()
    else:
        delta = 0.0

    if delta >= 0:
        # me started later → delay me
        return delta * 1000.0, 0.0
    return 0.0, (-delta) * 1000.0
