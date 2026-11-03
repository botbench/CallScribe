"""Install the CallScribe operator skill into the user's personal Cursor skills dir.

Project skill (``.cursor/skills/callscribe`` in the repo) is enough when the
checkout is open in Cursor. ``setup`` also copies the skill to
``~/.cursor/skills/callscribe`` so agents can use it from *other* projects after
CallScribe is installed.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def personal_skills_root() -> Path:
    return Path.home() / ".cursor" / "skills"


def personal_skill_dir() -> Path:
    return personal_skills_root() / "callscribe"


def find_operator_skill_dir() -> Path | None:
    """Locate packaged or checkout skill directory containing ``SKILL.md``."""
    here = Path(__file__).resolve().parent
    bundled = here / "operator_skill"
    if (bundled / "SKILL.md").is_file():
        return bundled

    # Editable / source tree: repo ``.cursor/skills/callscribe``
    for parent in here.parents:
        candidate = parent / ".cursor" / "skills" / "callscribe"
        if (candidate / "SKILL.md").is_file():
            return candidate
        if (parent / "pyproject.toml").is_file() and parent.name.lower() == "callscribe":
            break
    return None


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

    dest = dest_dir or personal_skill_dir()
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
