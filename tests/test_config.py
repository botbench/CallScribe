from __future__ import annotations

from pathlib import Path

import pytest

from callscribe.config import Config, load_config, write_defaults


def test_write_and_load_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / ".callscribe"
    monkeypatch.setenv("HOME", str(tmp_path))
    # paths.expand uses Path.home() which respects HOME on Unix
    cfg_path = write_defaults(home / "config.toml")
    assert cfg_path.exists()
    cfg = load_config(cfg_path)
    assert isinstance(cfg, Config)
    assert cfg.capture == "system"
    assert cfg.mic_device == "default"
    assert cfg.keep_raw_tracks is True


def test_rejects_bad_capture(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('capture = "nope"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="capture"):
        load_config(path)


def test_mic_class_and_optional_overrides(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'mic_class = "airpods"\n'
        "mic_latency_bias_ms = 90\n"
        "mixdown_duration_tolerance_s = 2.5\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.mic_class == "airpods"
    assert cfg.mic_latency_bias_ms == 90.0
    assert cfg.mixdown_duration_tolerance_s == 2.5


def test_rejects_bad_mic_class(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('mic_class = "potato"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="mic_class"):
        load_config(path)
