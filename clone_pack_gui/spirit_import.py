#!/usr/bin/env python3
"""Spirits from a Spirit Board export (its ArcOutput folder) as spirit.toml rows, with their names and pictures."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import unescape

from . import gimmicks, packs, prc, prcxml_files

DATA = Path(__file__).resolve().parent / "data"
DATABASE = ("ui", "param", "database")
TABLES = (("spirit", "ui_spirit_db.prc", "db_root", "ui_spirit_id"),
          ("battle", "ui_spirits_battle_db.prc", "battle_data_tbl", "battle_id"),
          ("fighter", "ui_spirits_battle_db.prc", "fighter_data_tbl", "battle_id"),
          ("layout", "ui_spirit_layout_db.prc", "db_root", "ui_spirit_layout_id"))
SKIPPED = {"fighter": ("spirit_name",)}
NAMES = (("ui", "message", "msg_spirits.xmsbt"), ("ui", "message", "msg_spirits.msbt"))
CANDIDATES = 24
ID_RE = re.compile(r"[^a-z0-9_]")


def toml_value(node, labels) -> str:
    """One value of a param row as spirit.toml writes it; a zero hash is blank."""
    if node.tag == "hash40":
        return "" if int(node.value) == 0 else '"%s"' % prcxml_files.value_text(node, labels)
    if node.tag == "bool":
        return "true" if node.value else "false"
    if node.tag == "string":
        return '"%s"' % str(node.value).replace("\\", "\\\\").replace('"', '\\"')
    return prcxml_files.value_text(node, labels)


def msbt_names(data: bytes) -> dict:
    """label to text of an msbt."""
    sections, at = {}, 0x20
    for _ in range(struct.unpack_from("<H", data, 0x0E)[0]):
        magic, size = data[at:at + 4], struct.unpack_from("<I", data, at + 4)[0]
        sections[magic] = (at + 0x10, size)
        at = (at + 0x10 + size + 15) & ~15
    labels, (body, _) = {}, sections[b"LBL1"]
    for slot in range(struct.unpack_from("<I", data, body)[0]):
        count, offset = struct.unpack_from("<II", data, body + 4 + slot * 8)
        p = body + offset
        for _ in range(count):
            length = data[p]
            labels[struct.unpack_from("<I", data, p + 1 + length)[0]] = data[p + 1:p + 1 + length].decode()
            p += 5 + length
    body, size = sections[b"TXT2"]
    count = struct.unpack_from("<I", data, body)[0]
    offsets = struct.unpack_from("<%dI" % count, data, body + 4)
    out = {}
    for index, offset in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < count else size
        text = data[body + offset:body + end].decode("utf-16-le", "replace")
        out[labels.get(index, "")] = text.split("\x0e")[0].replace("\n", " ").replace("\t", " ").strip("\0 ")
    return out


@dataclass
class Imported:
    """What one export holds for Dionysus: new spirits as rows, and what could not come along."""
    rows: list = field(default_factory=list)
    names: dict = field(default_factory=dict)
    pictures: list = field(default_factory=list)
    changed: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def export_root(folder) -> Path | None:
    """The folder holding the export's ui/param/database, the ArcOutput inside the app's own folder too."""
    folder = Path(folder)
    for candidate in (folder, folder / "ArcOutput"):
        if candidate.joinpath(*DATABASE, TABLES[0][1]).is_file():
            return candidate
    return None


def export_rows(root: Path, labels: dict) -> dict:
    """{table: {key: [rows]}} of the export's tables, values as spirit.toml writes them."""
    found, trees = {}, {}
    for table, name, listing, column in TABLES:
        path = root.joinpath(*DATABASE, name)
        index: dict = {}
        if path.is_file():
            if name not in trees:
                trees[name] = prcxml_files.read_prc(path.read_bytes(), labels)
            rows = trees[name].member(listing)
            for row in (rows.children if rows is not None else []):
                cells = {child.name: toml_value(child, labels) for child in row.children
                         if child.tag not in ("list", "struct")}
                index.setdefault(cells.get(column, ""), []).append(cells)
        found[table] = index
    return found


def spirit_values(rows: dict, key: str, tool) -> dict:
    """Every key the export's spirit sets, as a base's values are written."""
    values = {name: value for name, value in rows["spirit"][key][0].items() if name not in tool.FIXED["spirit"]}
    for table in ("battle", "layout"):
        for name, value in (rows[table].get(key) or [{}])[0].items():
            if name not in tool.FIXED[table]:
                values["%s.%s" % (table, name)] = value
    fighters = rows["fighter"].get(key) or []
    for number, fighter in enumerate(fighters):
        for name, value in fighter.items():
            if name not in tool.FIXED["fighter"] and name not in SKIPPED["fighter"]:
                values["fighter.%d.%s" % (number, name)] = value
    if fighters:
        values["fighters"] = str(len(fighters))
    return values


def changes(values: dict, base: dict, tool) -> dict:
    """The keys whose value differs from the base's; a base fighter past the spirit's count does not count."""
    count = int(values.get("fighters") or 0)
    out = {}
    for name, value in values.items():
        found = name.split(".", 2)
        if found[0] == "fighter" and len(found) == 3 and found[1].isdigit() and count and int(found[1]) >= count:
            continue
        if name == "spirit_name" or name.endswith(".spirit_name"):
            continue
        if not tool.same_value(value, tool.base_value(base, name)):
            out[name] = value
    return out


def closest_base(values: dict, tool) -> tuple[str, dict]:
    """The game spirit whose copy needs the fewest changes to become this one."""
    rows = tool.game_rows()["spirit"]
    plain = {name: value for name, value in values.items() if "." not in name and name != "fighters"}

    def rough(key):
        row = rows[key][0]
        return sum(not tool.same_value(value, tool.RESETS.get(name, row.get(name))) for name, value in plain.items())

    best = None
    for key in sorted(rows, key=rough)[:CANDIDATES]:
        base = gimmicks.display(key)
        found = changes(values, tool.base_values(base), tool)
        if best is None or len(found) < len(best[1]):
            best = (base, found)
    return best


def spirit_id(name_id: str) -> str:
    return ID_RE.sub("_", name_id.strip().lower())[:48].strip("_")


def read_names(root: Path) -> dict:
    names: dict = {}
    for place in NAMES:
        path = root.joinpath(*place)
        if not path.is_file():
            continue
        if path.suffix == ".msbt":
            try:
                names.update({label: text for label, text in msbt_names(path.read_bytes()).items()
                              if label not in names})
            except (struct.error, KeyError, IndexError):
                continue
        else:
            for label, text in packs.messages(root, place).items():
                names.setdefault(label, unescape(text))
    return names


def pictures_of(root: Path, name_id: str) -> list:
    """(file, size, patch tree) for each picture the export ships for one spirit."""
    found = []
    for patch_tree, tree in ((False, packs.SPIRIT_TREES[0]), (True, packs.SPIRIT_TREES[1])):
        for size in "0123":
            path = root.joinpath(*tree.split("/"), "spirits_%s" % size, "spirits_%s_%s.bntx" % (size, name_id))
            if path.is_file():
                found.append((path, size, patch_tree))
    return found


def import_export(folder, tool, labels: dict | None = None) -> Imported:
    """The export's new spirits as spirit.toml rows on their closest game spirit."""
    root = export_root(folder)
    if root is None:
        raise ValueError("%s holds no ui/param/database/ui_spirit_db.prc (pick Spirit Board's ArcOutput "
                         "folder)" % folder)
    if labels is None:
        labels = prc.load_labels(DATA / "ParamLabels.csv")
    game = tool.game_rows()
    if not game:
        raise ValueError("the game's spirit tables are not beside this window")
    rows = export_rows(root, labels)
    names = read_names(root)
    result = Imported()
    for key, found in rows["spirit"].items():
        row = found[0]
        name_id = gimmicks.display(row.get("name_id", "")) or gimmicks.display(key)
        if key in game["spirit"]:
            mine = {name: value for name, value in game["spirit"][key][0].items() if name not in tool.FIXED["spirit"]}
            theirs = {name: value for name, value in row.items() if name not in tool.FIXED["spirit"]}
            if any(not tool.same_value(value, mine.get(name)) for name, value in theirs.items()):
                result.changed.append(name_id)
            continue
        spirit = spirit_id(name_id)
        if not spirit:
            result.skipped.append((name_id, "its name_id makes no id"))
            continue
        values = spirit_values(rows, key, tool)
        if key not in rows["battle"] or key not in rows["fighter"]:
            result.skipped.append((name_id, "it has no battle or fighters in the export"))
            continue
        base, found_changes = closest_base(values, tool)
        result.rows.append({"id": '"%s"' % spirit, "base": '"%s"' % base, **found_changes})
        text = names.get("spi_" + name_id)
        if text:
            result.names[spirit] = text
        result.pictures += [(path, size, patch_tree, spirit) for path, size, patch_tree in pictures_of(root, name_id)]
    return result
