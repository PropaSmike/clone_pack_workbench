#!/usr/bin/env python3
"""Make a pack smaller without changing what the game sees: a costume's file
that is byte for byte the file of a lower costume is taken out of the pack and
config.json points the name at the lower costume's file instead (reslotter's
moveset optimizer, with the lowest matching costume as the source rather than
one main slot)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath

from . import backups

SLOT_DIR_RE = re.compile(r"^c(\d{2,3})$")
SLOT_FILE_RE = re.compile(r"_c(\d{2,3})(?=\.)")
SKIP_SUFFIXES = {".marker", ".json", ".toml", ".md", ".txt", ".zip", ".bak", ".nro"}
SKIP_DIRS = {"backups", "junk", ".git"}


def family(relative: PurePosixPath):
    """(key, slot) for a path that belongs to one costume: the deepest cNN
    directory, or the _cNN of a sound bank's name, replaced by c* in the key.
    None for a path no costume owns."""
    parts = list(relative.parts)
    for index in range(len(parts) - 2, -1, -1):
        match = SLOT_DIR_RE.match(parts[index])
        if match:
            parts[index] = "c*"
            return "/".join(parts), int(match.group(1))
    name = parts[-1]
    match = SLOT_FILE_RE.search(name)
    if match:
        parts[-1] = name[:match.start()] + "_c*" + name[match.end():]
        return "/".join(parts), int(match.group(1))
    return None


def slot_path(key: str, slot: int) -> str:
    return key.replace("c*", "c%02d" % slot)


def digest(path: Path) -> str:
    sha = hashlib.sha1()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def scan(folder: Path) -> dict:
    """duplicates: (target, source, size) for every costume file whose bytes
    equal a lower costume's twin, source being the lowest such costume.
    families: how many costume-owned files were looked at. empty: directories
    with nothing in them."""
    folder = Path(folder)
    families: dict[str, dict[int, Path]] = {}
    looked = 0
    empty = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
        if not dirs and not files and Path(root) != folder:
            empty.append(Path(root).relative_to(folder))
        for name in files:
            path = Path(root) / name
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            owner = family(PurePosixPath(path.relative_to(folder).as_posix()))
            if owner is None:
                continue
            key, slot = owner
            families.setdefault(key, {})[slot] = path
            looked += 1
    duplicates = []
    for key in sorted(families):
        slots = families[key]
        if len(slots) < 2:
            continue
        by_size: dict[int, list[int]] = {}
        for slot, path in slots.items():
            by_size.setdefault(path.stat().st_size, []).append(slot)
        for size, members in by_size.items():
            if len(members) < 2:
                continue
            by_hash: dict[str, list[int]] = {}
            for slot in sorted(members):
                by_hash.setdefault(digest(slots[slot]), []).append(slot)
            for same in by_hash.values():
                source = same[0]
                for slot in same[1:]:
                    duplicates.append((slot_path(key, slot), slot_path(key, source), size))
    duplicates.sort()
    return {"duplicates": duplicates, "looked": looked, "empty": sorted(empty)}


def share_targets(config: dict) -> set[str]:
    """Every path config.json already makes an alias of something."""
    targets = set()
    for section in ("share-to-vanilla", "share-to-added"):
        for value in (config.get(section) or {}).values():
            if isinstance(value, str):
                targets.add(value)
            else:
                targets.update(str(item) for item in value)
    return targets


def group_of(config: dict, path: str) -> str | None:
    for group, members in (config.get("new-dir-files") or {}).items():
        if path in members:
            return group
    return None


def plan_config(config: dict, duplicates: list) -> tuple[dict, list, list[str]]:
    """The config with a share-to-added line per duplicate, the duplicates it
    covers, and one note per duplicate left alone: a target config.json already
    aliases stays what it is."""
    config = json.loads(json.dumps(config)) if config else {}
    shares = config.setdefault("share-to-added", {})
    groups = config.setdefault("new-dir-files", {})
    already = share_targets(config)
    kept, notes = [], []
    for target, source, size in duplicates:
        if target in already:
            notes.append("%s is already an alias in config.json; left as it is" % target)
            continue
        existing = shares.get(source)
        if existing is None:
            shares[source] = [target]
        elif isinstance(existing, str):
            shares[source] = sorted({existing, target})
        elif target not in existing:
            shares[source] = sorted(set(existing) | {target})
        home = group_of(config, source)
        if home is not None and group_of(config, target) is None:
            twin = home.replace("c%02d" % family(PurePosixPath(source))[1],
                                "c%02d" % family(PurePosixPath(target))[1])
            if twin != home and twin in groups:
                groups[twin] = sorted(set(groups[twin]) | {target})
            else:
                notes.append("%s is in no new-dir-files group (%s is in %s); add it by hand"
                             % (target, source, home))
        kept.append((target, source, size))
    config["share-to-added"] = {key: shares[key] for key in sorted(shares)}
    return config, kept, notes


def apply(folder: Path, config: dict, kept: list, empty: list) -> list[str]:
    """Write config.json (kept first), take each duplicate out of the pack (a
    copy kept), drop the directories that are then empty. One line each."""
    folder = Path(folder)
    lines = []
    path = folder / "config.json"
    backups.keep(path, folder)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines.append("config.json: %d share-to-added source(s)" % len(config.get("share-to-added") or {}))
    touched = set()
    for target, source, size in kept:
        file = folder / target
        if not file.is_file():
            lines.append("%s was already gone" % target)
            continue
        backups.remove(file, folder)
        touched.add(file.parent)
        lines.append("removed %s (%s, now %s)" % (target, human(size), source))
    for directory in sorted(touched | {folder / relative for relative in empty},
                            key=lambda entry: len(entry.parts), reverse=True):
        while directory != folder and directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
            lines.append("dropped the empty folder %s" % directory.relative_to(folder).as_posix())
            directory = directory.parent
    return lines


def human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return "%d %s" % (size, unit) if unit == "B" else "%.1f %s" % (size, unit)
        size /= 1024.0
    return "%d B" % size
