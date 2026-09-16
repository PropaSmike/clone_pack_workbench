#!/usr/bin/env python3
"""Vanilla names, kinds and param field lists the panels offer as choices."""

from __future__ import annotations

import os
from pathlib import Path

from . import prc

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
ROSTER_LAST_KIND = 93

PARAM_TABLES = {
    "fighter_param": "fighter_param_row_13.0.4.tsv",
    "param_motion": "fighter_param_motion_row_13.0.4.tsv",
    "common": "fighter_common_copies_13.0.4.tsv",
    "item_common": "item_common_row_13.0.4.tsv",
}

THROWN_VECTORS = ("offset", "offset_f", "offset_b", "offset_hi", "offset_lw",
                  "held_offset")
THROWN_COMPONENTS = ("_x", "_y", "_z")
VL_SURFACE = "vl.prc"
OWNER_SURFACE = "item_owner_param"
FIELDLESS = (VL_SURFACE, OWNER_SURFACE)
OWNER_TABLE = "owner_params.tsv"
OWNER_WORDS = ("f32", "i32", "u32", "bool")

FLOAT_TYPES = ("f32", "float")
INT_TYPES = ("u32", "i32", "s32", "int", "bool", "u8", "s8", "u16", "s16")
LABEL_TYPES = ("kind",)
NAME_TYPES = ("hash40",)


def data_file(name: str) -> Path | None:
    """A shipped table, looked for beside this package and in the repo docs."""
    roots = [DATA, HERE.parent / "docs", HERE.parent.parent / "docs"]
    for root in roots:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def rows(path: Path):
    """Every data row of a tab separated file as a dict keyed by its header."""
    with path.open(encoding="utf-8", errors="replace") as handle:
        header = handle.readline().rstrip("\n").split("\t")
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                continue
            yield dict(zip(header, line.split("\t")))


def default_arc_index() -> Path:
    """The arc index beside this package, or above it. SSBU_ARC_INDEX overrides."""
    override = os.environ.get("SSBU_ARC_INDEX")
    roots = [Path(override)] if override else []
    roots += [HERE / "arc_index", HERE.parent / "arc_index",
              HERE.parent.parent / "arc_index", HERE.parent.parent.parent / "arc_index"]
    for root in roots:
        if (root / "arc_dirs.tsv").is_file() or (root / "arc_files.tsv").is_file():
            return root
    return roots[-1]


class Catalog:
    """Every list a panel needs, read once and kept."""

    def __init__(self, arc_index: Path | None = None):
        self.arc_index = Path(arc_index) if arc_index else default_arc_index()
        self._cache: dict[str, object] = {}
        self.notes: list[str] = []

    def _table(self, name: str, columns):
        key = "table:" + name
        if key not in self._cache:
            path = data_file(name)
            if path is None:
                self.notes.append("%s is missing, so its list is empty" % name)
                self._cache[key] = []
            else:
                self._cache[key] = [tuple(row.get(column, "") for column in columns)
                                    for row in rows(path)]
        return self._cache[key]

    def fighter_kinds(self) -> list[tuple[int, str]]:
        """Every fighter kind name the lua constants carry, by number."""
        return sorted((int(kind), name)
                      for kind, name in self._table("fighter_kinds.tsv", ("kind", "name")))

    def fighter_bases(self) -> list[tuple[int, str]]:
        """The 94 roster fighters, the only sane bases for a clone."""
        return [(kind, name) for kind, name in self.fighter_kinds()
                if kind <= ROSTER_LAST_KIND]

    def item_kinds(self) -> list[tuple[int, str]]:
        """Every item kind by number, whatever tree its files live under."""
        return sorted((int(kind), name) for kind, name, _
                      in self._table("item_kinds.tsv", ("kind", "name", "root")))

    def item_bases(self) -> list[tuple[int, str]]:
        """The item kinds a clone can be built on: rooted at item/ and in the arc."""
        present = set(self.item_dirs())
        return sorted((int(kind), name) for kind, name, root
                      in self._table("item_kinds.tsv", ("kind", "name", "root"))
                      if root == "item" and (not present or name in present))

    def weapons(self) -> list[tuple[int, str, str]]:
        return [(int(kind), const, owner) for kind, const, owner
                in self._table("weapon_kinds.tsv", ("kind", "const", "owner"))]

    def weapon_owners(self) -> list[str]:
        return sorted({owner for _, _, owner in self.weapons() if owner})

    def weapons_for(self, owner: str) -> list[tuple[int, str]]:
        """The weapons that belong to one fighter, shortest name first."""
        return sorted((kind, const) for kind, const, holder in self.weapons()
                      if holder == owner)

    def _arc_dirs(self) -> list[str]:
        if "arc_dirs" not in self._cache:
            path = self.arc_index / "arc_dirs.tsv"
            found = []
            if path.is_file():
                with path.open(encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        value = line.split("\t", 1)[0].strip()
                        if value:
                            found.append(value)
            else:
                self.notes.append("no arc_dirs.tsv under %s, so the place and "
                                  "directory lists are empty" % self.arc_index)
            self._cache["arc_dirs"] = found
        return self._cache["arc_dirs"]

    def _tree_names(self, prefix: str) -> list[str]:
        """The names one level under a tree: fighter/<name>, stage/<place>."""
        depth = prefix.rstrip("/").count("/") + 1
        names = set()
        for directory in self._arc_dirs():
            if not directory.startswith(prefix):
                continue
            parts = directory.split("/")
            if len(parts) > depth and parts[depth]:
                names.add(parts[depth])
        return sorted(names)

    def fighter_dirs(self) -> list[str]:
        return self._tree_names("fighter/")

    def item_dirs(self) -> list[str]:
        return self._tree_names("item/")

    def stage_places(self) -> list[str]:
        """Every vanilla place, which is what a donor is picked from."""
        return self._tree_names("stage/")

    def thrown_keys(self) -> list[tuple[str, str]]:
        """The hold offset rules, whole vectors first, then their components."""
        keys = []
        for vector in THROWN_VECTORS:
            keys.append((vector, "vector"))
            for part in THROWN_COMPONENTS:
                keys.append((vector + part, "f32"))
        return keys

    def param_fields(self, table: str) -> list[tuple[str, str]]:
        """(field, type) for one param table, in file order."""
        return [(field, kind) for field, kind, _ in self.param_rows(table)]

    def param_rows(self, table: str) -> list[tuple[str, str, str]]:
        """(field, type, source file) for one surface. The source names the prc."""
        if table == "param_thrown":
            return [(field, kind, "fighter_param_thrown")
                    for field, kind in self.thrown_keys()]
        if table in FIELDLESS:
            return []
        name = PARAM_TABLES.get(table)
        if name is None:
            return []
        key = "rows:" + table
        if key not in self._cache:
            path = data_file(name)
            found: list[tuple[str, str, str]] = []
            if path is None:
                self.notes.append("%s is missing, so the %s field list is empty"
                                  % (name, table))
            else:
                seen = set()
                for row in rows(path):
                    field = row.get("field", "")
                    if field and field not in seen:
                        seen.add(field)
                        found.append((field, row.get("type", ""),
                                      row.get("source", table)))
            self._cache[key] = found
        return self._cache[key]

    def param_sources(self, table: str) -> list[str]:
        """Which prc files a surface is made of, for the file filter."""
        return sorted({source for _, _, source in self.param_rows(table) if source})

    def labels(self) -> dict:
        """The param label list, read once. Without it names show as hashes."""
        if "labels" not in self._cache:
            path = data_file(prc.LABELS_FILE)
            if path is None:
                self.notes.append("%s is not beside this GUI, so a prc's own param "
                                  "names show as hashes" % prc.LABELS_FILE)
                self._cache["labels"] = {}
            else:
                self._cache["labels"] = prc.load_labels(path)
        return self._cache["labels"]

    def owner_params(self, kind: int) -> list[tuple[str, str, int, str]]:
        """(path, type, offset, default) for each word of one fighter's vl.prc payload
        that sits inline, which is what item_owner_param_set can reach."""
        if "owner" not in self._cache:
            path = data_file(OWNER_TABLE)
            table: dict[int, list] = {}
            if path is None:
                self.notes.append("%s is missing, so owner params have no names"
                                  % OWNER_TABLE)
            else:
                for row in rows(path):
                    if row.get("type") not in OWNER_WORDS:
                        continue
                    parent = row.get("parent", "")
                    name = row.get("field", "")
                    try:
                        offset = int(row.get("offset", ""), 16)
                        owner = int(row.get("kind", ""))
                    except ValueError:
                        continue
                    table.setdefault(owner, []).append(
                        ((parent + "/" + name) if parent else name, row["type"], offset,
                         row.get("default", "")))
            self._cache["owner"] = table
        return list(self._cache["owner"].get(kind, []))

    def owner_prc_in_pack(self, folder, owner: str) -> Path | None:
        """The owner's own vl.prc, when the pack happens to ship it."""
        if not folder or not owner:
            return None
        candidate = Path(folder) / "fighter" / owner / "param" / "vl.prc"
        return candidate if candidate.is_file() else None

    def prc_values(self, path) -> dict:
        """path to (type, value) read out of one prc, kept once read."""
        path = Path(path)
        key = "values:%s" % path
        if key not in self._cache:
            self._cache[key] = prc.param_values(path, self.labels())
        return self._cache[key]

    def prc_row_values(self, path, index: int) -> dict:
        """field to (type, value) for one row of a list-rooted prc, kept once read."""
        path = Path(path)
        key = "row:%s:%d" % (path, index)
        if key not in self._cache:
            self._cache[key] = prc.row_values(path, self.labels(), index)
        return self._cache[key]

    def owner_defaults(self, kind: int) -> dict:
        """path to the compiled default of one fighter's inline words, by name."""
        return {path: default for path, _, _, default in self.owner_params(kind) if default}

    def pack_item_prc_files(self, folder, resource: str) -> list[Path]:
        """The prc files an item pack ships under its own item directory."""
        if not folder or not resource:
            return []
        root = Path(folder) / "item" / resource / "param"
        if not root.is_dir():
            return []
        return sorted(path for path in root.glob("*.prc") if path.is_file())

    def common_item_prc_in_pack(self, folder) -> Path | None:
        """item/common/param/param.prc, if the pack happens to carry a copy."""
        if not folder:
            return None
        candidate = Path(folder) / "item" / "common" / "param" / "param.prc"
        return candidate if candidate.is_file() else None

    def pack_prc_files(self, folder, resource: str) -> list[Path]:
        """The prc files a fighter pack ships, which is where its own names live."""
        if not folder or not resource:
            return []
        root = Path(folder) / "fighter" / resource / "param"
        if not root.is_dir():
            return []
        return sorted(path for path in root.glob("*.prc") if path.is_file())

    def prc_rows(self, path) -> list[tuple[str, str, str]]:
        """(name, type, file) for one prc the pack ships."""
        path = Path(path)
        key = "prc:%s" % path
        if key not in self._cache:
            self._cache[key] = [(name, kind, path.name)
                                for name, kind in prc.param_names(path, self.labels())]
        return self._cache[key]

    def bgm_sets(self) -> list[tuple[str, int]]:
        """The playlists a stage may draw from, with how many columns each holds."""
        return [(name, int(columns)) for name, columns
                in self._table("bgm_sets.tsv", ("name", "columns"))]

    def bgm_columns(self, name: str) -> int | None:
        """How many columns one playlist has, so a column number can be checked."""
        wanted = (name or "").strip().lower()
        if wanted and not wanted.startswith("bgm"):
            wanted = "bgm" + wanted
        for known, columns in self.bgm_sets():
            if known == wanted:
                return columns
        return None

    def item_labels(self) -> list[tuple[str, int]]:
        """The prc labels a kind field of the item common row accepts."""
        return sorted((label, int(value, 16))
                      for value, label in self._table("item_common_labels_13.0.4.tsv",
                                                      ("value", "label")) if label)

    def item_label_names(self) -> dict:
        """hash to label for the kind fields of the item common row."""
        out = {}
        for hash_text, label in self._table("item_common_labels_13.0.4.tsv",
                                            ("hash", "label")):
            try:
                out[int(hash_text, 16)] = label
            except ValueError:
                continue
        return out

    def labels_for(self, field: str) -> list[str]:
        """The labels whose name belongs to one kind field, such as shield_kind."""
        stem = field[:-5] if field.endswith("_kind") else field
        exact = [label for label, _ in self.item_labels()
                 if stem in label or label.startswith("item_%s" % stem)]
        return exact or [label for label, _ in self.item_labels()]

    def kind_of_fighter(self, name: str) -> int | None:
        for kind, known in self.fighter_kinds():
            if known == name:
                return kind
        return None

    def kind_of_item(self, name: str) -> int | None:
        for kind, known in self.item_kinds():
            if known == name:
                return kind
        return None

    def item_name(self, kind: int) -> str | None:
        for known, name in self.item_kinds():
            if known == kind:
                return name
        return None


def is_float_field(kind: str) -> bool:
    return kind in FLOAT_TYPES


def is_int_field(kind: str) -> bool:
    return kind in INT_TYPES


def is_label_field(kind: str) -> bool:
    return kind in LABEL_TYPES


def is_name_field(kind: str) -> bool:
    return kind in NAME_TYPES
