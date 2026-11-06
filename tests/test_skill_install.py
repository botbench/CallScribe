"""Personal Cursor skill install helper."""

from __future__ import annotations

from pathlib import Path

from callscribe.skill_install import (
    find_operator_skill_dir,
    find_summarize_skill_dir,
    install_personal_operator_skill,
    install_personal_summarize_skill,
)


def test_find_operator_skill_dir_bundled() -> None:
    src = find_operator_skill_dir()
    assert src is not None
    assert (src / "SKILL.md").is_file()
    text = (src / "SKILL.md").read_text(encoding="utf-8")
    assert "name: callscribe" in text
    assert "callscribe start" in text


def test_find_summarize_skill_dir_bundled() -> None:
    src = find_summarize_skill_dir()
    assert src is not None
    assert (src / "SKILL.md").is_file()
    text = (src / "SKILL.md").read_text(encoding="utf-8")
    assert "name: callscribe-summarize" in text
    assert "fm --model system" in text or "`fm`" in text
    assert "privacy" in text.lower()


def test_install_personal_operator_skill(tmp_path: Path) -> None:
    # Avoid writing under a real ``~/.cursor`` path in tests (sandbox / host).
    dest_dir = tmp_path / "skills-dest" / "callscribe"
    dest = install_personal_operator_skill(dest_dir=dest_dir)
    assert dest == dest_dir
    assert (dest / "SKILL.md").is_file()
    assert "Operate the CallScribe" in (dest / "SKILL.md").read_text(encoding="utf-8")

    install_personal_operator_skill(dest_dir=dest_dir)
    assert (dest / "SKILL.md").is_file()


def test_install_personal_summarize_skill(tmp_path: Path) -> None:
    dest_dir = tmp_path / "skills-dest" / "callscribe-summarize"
    dest = install_personal_summarize_skill(dest_dir=dest_dir)
    assert dest == dest_dir
    text = (dest / "SKILL.md").read_text(encoding="utf-8")
    assert "callscribe-summarize" in text
    assert "summary.md" in text

    install_personal_summarize_skill(dest_dir=dest_dir)
    assert (dest / "SKILL.md").is_file()
