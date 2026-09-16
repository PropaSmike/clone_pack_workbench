#!/usr/bin/env python3
"""Read the param names out of a prc file the pack itself ships."""

from __future__ import annotations

import struct
from pathlib import Path

MAGIC = b"paracobn"
TYPES = {1: "bool", 2: "i8", 3: "u8", 4: "i16", 5: "u16", 6: "i32", 7: "u32",
         8: "f32", 9: "hash40", 10: "string", 11: "list", 12: "struct"}
SCALARS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
FORMATS = {1: "<B", 2: "<b", 3: "<B", 4: "<h", 5: "<H", 6: "<i", 7: "<I", 8: "<f"}
LABELS_FILE = "ParamLabels.csv"
MAX_NAMES = 4000


def load_labels(path: Path) -> dict:
    """hash to name, from the community param label list."""
    labels: dict[int, str] = {}
    if not Path(path).is_file():
        return labels
    with Path(path).open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line or "," not in line:
                continue
            number, name = line.split(",", 1)
            try:
                labels[int(number, 16)] = name.strip()
            except ValueError:
                continue
    return labels


class Prc:
    """Just enough of the format to walk two levels of names."""

    def __init__(self, data: bytes, labels: dict):
        if data[:8] != MAGIC:
            raise ValueError("not a paracobn param file")
        self.data = data
        self.labels = labels
        hash_size, ref_size = struct.unpack_from("<II", data, 8)
        self.hash_start = 0x10
        count = hash_size // 8
        self.hashes = struct.unpack_from("<%dQ" % count, data, self.hash_start)
        self.ref_start = self.hash_start + hash_size
        self.param_start = self.ref_start + ref_size

    def name(self, index: int) -> str:
        value = self.hashes[index] if index < len(self.hashes) else 0
        return self.labels.get(value, "0x%010x" % value)

    def kind(self, at: int) -> int:
        return self.data[at]

    def struct_members(self, at: int):
        """(name index, member offset) for a struct, in file order."""
        count, reference = struct.unpack_from("<II", self.data, at + 1)
        table = self.ref_start + reference
        for index in range(count):
            name_index, offset = struct.unpack_from("<II", self.data, table + index * 8)
            yield name_index, at + offset

    def list_entries(self, at: int):
        count, = struct.unpack_from("<I", self.data, at + 1)
        for index in range(count):
            offset, = struct.unpack_from("<I", self.data, at + 5 + index * 4)
            yield at + offset

    def first_entry(self, at: int) -> int | None:
        for entry in self.list_entries(at):
            return entry
        return None

    def scalar(self, at: int):
        """The value of a scalar node, or None for a container. A hash40 node holds
        an index into the hash table and a string node an offset into the reference
        table, four bytes each, not the value itself."""
        kind = self.kind(at)
        if kind == 9:
            index, = struct.unpack_from("<I", self.data, at + 1)
            return self.hashes[index] if index < len(self.hashes) else 0
        if kind == 10:
            offset, = struct.unpack_from("<I", self.data, at + 1)
            start = self.ref_start + offset
            end = self.data.index(b"\0", start)
            return self.data[start:end].decode("utf-8", "replace")
        if kind in FORMATS:
            return struct.unpack_from(FORMATS[kind], self.data, at + 1)[0]
        return None

    def walk(self, limit: int = MAX_NAMES):
        """(path, type, node) two levels down; a list stands for its first entry."""
        found: list[tuple[str, str, int]] = []
        if self.kind(self.param_start) != 12:
            return found
        for name_index, member in self.struct_members(self.param_start):
            top = self.name(name_index)
            kind = self.kind(member)
            if kind in SCALARS:
                found.append((top, TYPES.get(kind, "?"), member))
                continue
            inner = member
            if kind == 11:
                entry = self.first_entry(member)
                if entry is None:
                    found.append((top, "list", member))
                    continue
                inner = entry
            if self.kind(inner) != 12:
                found.append((top, TYPES.get(self.kind(inner), "?"), inner))
                continue
            found.append((top, "struct" if kind == 12 else "list", member))
            for field_index, field in self.struct_members(inner):
                found.append(("%s/%s" % (top, self.name(field_index)),
                              TYPES.get(self.kind(field), "?"), field))
                if len(found) >= limit:
                    return found
        return found

    def names(self, limit: int = MAX_NAMES) -> list[tuple[str, str]]:
        """Top level params, and the fields one level inside each of them."""
        return [(path, kind) for path, kind, _ in self.walk(limit)]

    def values(self, limit: int = MAX_NAMES) -> dict:
        """path to (type, value) for every scalar the walk reaches."""
        return {path: (kind, self.scalar(node)) for path, kind, node in self.walk(limit)
                if self.kind(node) in SCALARS}

    def row(self, index: int) -> dict:
        """field to (type, value) for one entry of the list at the root, which is
        how item/common/param/param.prc keeps one row per item kind."""
        if self.kind(self.param_start) != 12:
            return {}
        for _, member in self.struct_members(self.param_start):
            if self.kind(member) != 11:
                continue
            entries = list(self.list_entries(member))
            if index < 0 or index >= len(entries) or self.kind(entries[index]) != 12:
                return {}
            return {self.name(field_index): (TYPES.get(self.kind(field), "?"),
                                             self.scalar(field))
                    for field_index, field in self.struct_members(entries[index])
                    if self.kind(field) in SCALARS}
        return {}


def param_names(path: Path, labels: dict) -> list[tuple[str, str]]:
    """Every name this prc offers, or an empty list if it cannot be read."""
    try:
        return Prc(Path(path).read_bytes(), labels).names()
    except (ValueError, struct.error, IndexError, OSError):
        return []


def param_values(path: Path, labels: dict) -> dict:
    """path to (type, value) for this prc, or nothing if it cannot be read."""
    try:
        return Prc(Path(path).read_bytes(), labels).values()
    except (ValueError, struct.error, IndexError, OSError):
        return {}


def row_values(path: Path, labels: dict, index: int) -> dict:
    """field to (type, value) for one row of a list-rooted prc, or nothing."""
    try:
        return Prc(Path(path).read_bytes(), labels).row(index)
    except (ValueError, struct.error, IndexError, OSError):
        return {}


def shown(kind: str, value, labels: dict | None = None) -> str:
    """A value as the list prints it: floats short, a hash by its label when known,
    the rest plain."""
    if value is None:
        return ""
    if kind == "f32":
        return "%.9g" % value
    if kind == "hash40":
        return (labels or {}).get(value) or "0x%010x" % value
    if kind == "string":
        return str(value)
    return str(int(value))


def word(kind: str, value) -> str:
    """The word a value occupies in the game's payload, as the engine logs it."""
    try:
        if kind == "f32":
            bits = struct.unpack("<I", struct.pack("<f", float(value)))[0]
        elif kind == "hash40":
            return "0x%010x" % (int(str(value), 0) & 0xFFFFFFFFFF)
        elif kind == "string":
            return ""
        else:
            bits = int(float(value)) & 0xFFFFFFFF
    except (ValueError, OverflowError, struct.error):
        return ""
    return "0x%08x" % bits
