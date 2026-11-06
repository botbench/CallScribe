"""Install CallScribe Cursor skills into the user's personal skills dir.

Project skills (``.cursor/skills/…`` in the repo) are enough when the checkout
is open in Cursor. ``setup`` also copies skills to ``~/.cursor/skills/…`` so
agents can use them from *other* projects after CallScribe is installed.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def personal_skills_root() -> Path:
    return Path.home() / ".cursor" / "skills"


def personal_skill_dir(name: str = "callscribe") -> Path:
    return personal_skills_root() / name


def _find_skill_dir(*, bundled_name: str, project_name: str) -> Path | None:
    """Locate packaged or checkout skill directory containing ``SKILL.md``."""
    here = Path(__file__).resolve().parent
    bundled = here / bundled_name
    if (bundled / "SKILL.md").is_file():
        return bundled

    for parent in here.parents:
        candidate = parent / ".cursor" / "skills" / project_name
        if (candidate / "SKILL.md").is_file():
            return candidate
        if (parent / "pyproject.toml").is_file() and parent.name.lower() == "callscribe":
            break
    return None


def find_operator_skill_dir() -> Path | None:
    return _find_skill_dir(bundled_name="operator_skill", project_name="callscribe")


def find_summarize_skill_dir() -> Path | None:
    return _find_skill_dir(
        bundled_name="summarize_skill", project_name="callscribe-summarize"
    )


def _install_skill(*, src: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)

    # Replace prior install (file or symlink) with a fresh copy of SKILL.md (+ extras).
    for path in dest.iterdir():
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    for item in src.iterdir():
        if item.is_file():
            shutil.copy2(item, dest / item.name)
        elif item.is_dir():
            shutil.copytree(item, dest / item.name)

    if not (dest / "SKILL.md").is_file():
        raise FileNotFoundError(f"SKILL.md missing after install into {dest}")
    return dest


def install_personal_operator_skill(*, dest_dir: Path | None = None) -> Path:
    """Copy operator skill into ``~/.cursor/skills/callscribe``. Returns dest dir.

    ``dest_dir`` overrides the install location (tests).
    """
    src = find_operator_skill_dir()
    if src is None:
        raise FileNotFoundError(
            "CallScribe operator skill (SKILL.md) not found next to the package "
            "or under .cursor/skills/callscribe in the checkout."
        )
    return _install_skill(src=src, dest=dest_dir or personal_skill_dir("callscribe"))


def install_personal_summarize_skill(*, dest_dir: Path | None = None) -> Path:
    """Copy summarize skill into ``~/.cursor/skills/callscribe-summarize``."""
    src = find_summarize_skill_dir()
    if src is None:
        raise FileNotFoundError(
            "CallScribe summarize skill (SKILL.md) not found next to the package "
            "or under .cursor/skills/callscribe-summarize in the checkout."
        )
    return _install_skill(
        src=src, dest=dest_dir or personal_skill_dir("callscribe-summarize")
    )


def install_personal_skills() -> list[Path]:
    """Install all bundled personal skills. Returns dest dirs."""
    return [
        install_personal_operator_skill(),
        install_personal_summarize_skill(),
    ]
