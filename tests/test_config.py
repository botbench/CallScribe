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
