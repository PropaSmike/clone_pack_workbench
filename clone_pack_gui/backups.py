#!/usr/bin/env python3
"""A dated copy of every pack file the window writes over or deletes, kept
beside the tools rather than in the pack."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "backups"
KEPT: list[tuple[Path, Path]] = []


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def keep(path, pack=None) -> Path | None:
    """Copy the file as it is now to backups/<pack>/<date>/<path in the pack>.
    Returns where the copy went, or None when there was nothing to keep."""
    path = Path(path)
    if not path.is_file():
        return None
    pack = Path(pack) if pack else path.parent
    try:
        relative = path.resolve().relative_to(pack.resolve())
    except ValueError:
        relative = Path(path.name)
    target = ROOT / pack.name / stamp() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        number = 2
        while target.with_name("%s.%d" % (target.name, number)).exists():
            number += 1
        target = target.with_name("%s.%d" % (target.name, number))
    shutil.copy2(path, target)
    KEPT.append((path, target))
    return target


def remove(path, pack=None) -> Path | None:
    """Delete a pack file, keeping its copy first."""
    kept = keep(path, pack)
    Path(path).unlink()
    return kept


def drain() -> list[tuple[Path, Path]]:
    """The copies made since the last call, for the log."""
    kept = list(KEPT)
    KEPT.clear()
    return kept


def describe(target: Path) -> str:
    try:
        return target.relative_to(ROOT.parent).as_posix()
    except ValueError:
        return str(target)
