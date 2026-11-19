#!/usr/bin/env python3
"""Param files as prcxml: start from the game's values, kept as tables beside
this package, change them, and write the prcxml Dionysus and ARCropolis read."""

from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ElementTree
import zlib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

MAGIC = b"paracobn"
TAGS = {1: "bool", 2: "sbyte", 3: "byte", 4: "short", 5: "ushort", 6: "int", 7: "uint",
        8: "float", 9: "hash40", 10: "string", 11: "list", 12: "struct"}
FORMATS = {1: "<B", 2: "<b", 3: "<B", 4: "<h", 5: "<H", 6: "<i", 7: "<I", 8: "<f"}
RANGES = {"sbyte": (-0x80, 0x7F), "byte": (0, 0xFF), "short": (-0x8000, 0x7FFF),
          "ushort": (0, 0xFFFF), "int": (-0x80000000, 0x7FFFFFFF), "uint": (0, 0xFFFFFFFF)}
CONTAINERS = ("struct", "list")
SCALARS = ("bool", "sbyte", "byte", "short", "ushort", "int", "uint", "float", "hash40", "string")
NUMBERS = tuple(RANGES) + ("float",)


def hash40(text: str) -> int:
    data = text.encode("utf8")
    return (len(data) << 32) | (zlib.crc32(data) & 0xFFFFFFFF)


def key(text: str) -> int:
    """A name as Dionysus reads it: 0x... is the hash itself, anything else is hashed."""
    text = (text or "").strip()
    if text[:2].lower() == "0x":
        try:
            return int(text[2:], 16)
        except ValueError:
            pass
    return hash40(text)


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


F32_MAX = struct.unpack("<f", bytes((0xFF, 0xFF, 0x7F, 0x7F)))[0]


def float_text(value: float) -> str:
    """The shortest text that reads back as the same f32, without an exponent
    unless the number is very large or very small."""
    target = f32(value)
    text = "%.9g" % target
    for digits in range(1, 10):
        candidate = "%.*g" % (digits, target)
        if abs(float(candidate)) <= F32_MAX and f32(float(candidate)) == target:
            text = candidate
            break
    exact = Decimal(text)
    if exact.is_finite() and exact != 0 and -7 <= exact.adjusted() < 16:
        text = format(exact, "f")
    return text


@dataclass
class Node:
    """One element of a param file. `name` is how its hash is written (a label or
    0x...); list entries carry `index` instead."""
    tag: str
    name: str = ""
    index: int | None = None
    value: object = None
    children: list = field(default_factory=list)

    @property
    def hash(self) -> int | None:
        return key(self.name) if self.name else None

    def copy(self) -> "Node":
        return Node(self.tag, self.name, self.index, self.value, [child.copy() for child in self.children])

    def member(self, name: str) -> "Node | None":
        wanted = key(name)
        return next((child for child in self.children if child.hash == wanted), None)

    def label(self) -> str:
        return self.name if self.index is None else "[%d]" % self.index


DUMMY = hash40("dummy")


def name_of(value: int, labels: dict) -> str:
    if value == DUMMY:
        return "dummy"
    return labels.get(value) or "0x%010x" % value


class _Reader:
    def __init__(self, data: bytes, labels: dict):
        if data[:8] != MAGIC:
            raise ValueError("not a paracobn param file")
        self.data = data
        self.labels = labels
        hash_size, ref_size = struct.unpack_from("<II", data, 8)
        count = hash_size // 8
        self.hashes = struct.unpack_from("<%dQ" % count, data, 0x10)
        self.ref_start = 0x10 + hash_size
        self.param_start = self.ref_start + ref_size

    def hash_at(self, index: int) -> int:
        return self.hashes[index] if 0 <= index < len(self.hashes) else 0

    def node(self, at: int, name: str = "", index: int | None = None, depth: int = 0) -> Node:
        if depth > 64:
            raise ValueError("param file nests too deep")
        kind = self.data[at]
        tag = TAGS.get(kind)
        if tag is None:
            raise ValueError("unknown param type %d at %#x" % (kind, at))
        node = Node(tag, name, index)
        if tag == "struct":
            count, reference = struct.unpack_from("<II", self.data, at + 1)
            table = self.ref_start + reference
            for position in range(count):
                hash_index, offset = struct.unpack_from("<II", self.data, table + position * 8)
                child_name = name_of(self.hash_at(hash_index), self.labels)
                node.children.append(self.node(at + offset, child_name, None, depth + 1))
        elif tag == "list":
            count, = struct.unpack_from("<I", self.data, at + 1)
            for position in range(count):
                offset, = struct.unpack_from("<I", self.data, at + 5 + position * 4)
                node.children.append(self.node(at + offset, "", position, depth + 1))
        elif tag == "hash40":
            hash_index, = struct.unpack_from("<I", self.data, at + 1)
            node.value = self.hash_at(hash_index)
        elif tag == "string":
            offset, = struct.unpack_from("<I", self.data, at + 1)
            start = self.ref_start + offset
            node.value = self.data[start:self.data.index(b"\0", start)].decode("utf-8", "replace")
        elif tag == "bool":
            node.value = bool(self.data[at + 1])
        else:
            node.value = struct.unpack_from(FORMATS[kind], self.data, at + 1)[0]
        return node


def read_prc(data: bytes, labels: dict | None = None) -> Node:
    """The whole tree of a paracobn file; ValueError when it is not one."""
    try:
        reader = _Reader(data, labels or {})
        root = reader.node(reader.param_start)
    except (struct.error, IndexError) as error:
        raise ValueError("the file is cut short or damaged (%s)" % error) from None
    if root.tag != "struct":
        raise ValueError("the file does not start with a struct")
    return root


CODES = {tag: code for code, tag in TAGS.items()}
SIZES = {"bool": 2, "sbyte": 2, "byte": 2, "short": 3, "ushort": 3, "int": 5, "uint": 5, "float": 5,
         "hash40": 5, "string": 5}


def write_prc(root: Node) -> bytes:
    """A paracobn file for a tree, laid out as the game's own are: each struct's
    keys sorted by hash, structs with the same keys and offsets sharing one key
    table, strings beside the key tables in the order they are met."""
    if root.tag != "struct":
        raise ValueError("a param file starts with a struct")
    hashes, slots = [0], {0: 0}
    sizes: dict = {}
    refs, tables, out = bytearray(), {}, bytearray()

    def slot(value: int) -> int:
        if value not in slots:
            slots[value] = len(hashes)
            hashes.append(value)
        return slots[value]

    def members(node: Node) -> list:
        ordered = sorted(node.children, key=lambda child: child.hash or 0)
        for first, second in zip(ordered, ordered[1:]):
            if first.hash == second.hash:
                raise ValueError("%s is in %s twice" % (first.name, node.label() or "the top"))
        return ordered

    def size(node: Node) -> int:
        if id(node) not in sizes:
            if node.tag == "struct":
                sizes[id(node)] = 9 + sum(size(child) for child in node.children)
            elif node.tag == "list":
                sizes[id(node)] = 5 + 4 * len(node.children) + sum(size(child) for child in node.children)
            else:
                sizes[id(node)] = SIZES[node.tag]
        return sizes[id(node)]

    def emit(node: Node) -> None:
        if node.tag == "struct":
            ordered = members(node)
            at, table = 9, bytearray()
            for child in ordered:
                table += struct.pack("<II", slot(child.hash), at)
                at += size(child)
            table = bytes(table)
            if table not in tables:
                tables[table] = len(refs)
                refs.extend(table)
            out.extend(struct.pack("<BII", CODES["struct"], len(ordered), tables[table]))
            for child in ordered:
                emit(child)
        elif node.tag == "list":
            out.extend(struct.pack("<BI", CODES["list"], len(node.children)))
            at = 5 + 4 * len(node.children)
            for child in node.children:
                out.extend(struct.pack("<I", at))
                at += size(child)
            for child in node.children:
                emit(child)
        elif node.tag == "hash40":
            out.extend(struct.pack("<BI", CODES["hash40"], slot(int(node.value))))
        elif node.tag == "string":
            out.extend(struct.pack("<BI", CODES["string"], len(refs)))
            refs.extend(str(node.value).encode("utf-8") + bytes(1))
        else:
            code = CODES[node.tag]
            value = int(node.value) if node.tag != "float" else float(node.value)
            try:
                out.extend(struct.pack("<B" + FORMATS[code][1:], code, value))
            except struct.error:
                raise ValueError("%s does not fit a %s" % (node.label(), node.tag)) from None

    emit(root)
    return (MAGIC + struct.pack("<II", len(hashes) * 8, len(refs))
            + struct.pack("<%dQ" % len(hashes), *hashes) + bytes(refs) + bytes(out))


def _scalars(node: Node, trail: str):
    """(path, node) for every value under `node`, placeholders left out."""
    for path, found in flat(node, trail):
        if found.tag in SCALARS and not (found.tag == "hash40" and found.value == DUMMY):
            yield path, found


def own_file_values(root: Node) -> list:
    """The values of a vl or param file Dionysus cannot hand over itself, as
    "path (why)": it reads the numbers under a top-level group, or in the first
    row of a top-level list, by group and name. Everything else reaches the
    game only through the part's own copy of the file."""
    found = []

    def unread(node: Node, path: str, why: str) -> None:
        if node.tag in SCALARS:
            if not (node.tag == "hash40" and node.value == DUMMY):
                found.append("%s (%s)" % (path, why))
            return
        found.extend("%s (%s)" % (inner, why) for inner, _ in _scalars(node, path))

    def numbers_of(group: Node, path: str) -> None:
        for child in group.children:
            inner = "%s.%s" % (path, child.name)
            if child.tag in ("hash40", "string"):
                unread(child, inner, "a hash40" if child.tag == "hash40" else "text")
            elif child.tag in CONTAINERS:
                unread(child, inner, "a %s inside a group" % child.tag)

    for group in root.children:
        if group.tag in ("hash40", "string"):
            unread(group, group.name, "a hash40" if group.tag == "hash40" else "text")
        elif group.tag == "struct":
            numbers_of(group, group.name)
        elif group.tag == "list":
            entries = [entry for entry in group.children if not (entry.tag == "hash40" and entry.value == DUMMY)]
            if not entries:
                continue
            if entries[0].tag != "struct":
                unread(group, group.name, "a list of values")
                continue
            numbers_of(entries[0], "%s[%d]" % (group.name, entries[0].index or 0))
            for entry in entries[1:]:
                unread(entry, "%s[%d]" % (group.name, entry.index), "past the list's first row")
    return found


def scalar_value(tag: str, text: str):
    """The value an element's text holds, or ValueError."""
    text = (text or "").strip()
    if tag == "bool":
        lowered = text.lower()
        if lowered in ("true", "1"):
            return True
        if lowered in ("false", "0"):
            return False
        raise ValueError("a bool takes True or False")
    if tag in RANGES:
        number = int(text, 0)
        low, high = RANGES[tag]
        if not low <= number <= high:
            raise ValueError("%s takes %d to %d" % (tag, low, high))
        return number
    if tag == "float":
        number = float(text)
        if number != number or number in (float("inf"), float("-inf")):
            raise ValueError("a float takes a finite number")
        return f32(number)
    if tag == "hash40":
        if not text:
            raise ValueError("a hash40 takes a name or 0x...")
        return key(text)
    if tag == "string":
        return text
    raise ValueError("unknown type %s" % tag)


def parse_prcxml(text: str) -> Node:
    """A prcxml file as a tree; ValueError names what is wrong."""
    try:
        root = ElementTree.fromstring(text.lstrip("﻿").encode("utf-8"))
    except ElementTree.ParseError as error:
        raise ValueError("not XML: %s" % error) from None
    if root.tag != "struct":
        raise ValueError("the file must start with <struct>")
    return _element(root, 0)


def _element(element, depth: int) -> Node:
    if depth > 64:
        raise ValueError("the file nests too deep")
    tag = element.tag
    if tag not in CONTAINERS and tag not in SCALARS:
        raise ValueError("<%s> is not a param type" % tag)
    index = element.get("index")
    node = Node(tag, element.get("hash") or "", int(index) if index is not None and index.strip().isdigit() else None)
    if tag in CONTAINERS:
        for position, child in enumerate(element):
            entry = _element(child, depth + 1)
            if tag == "list" and entry.index is None:
                entry.index = position
            node.children.append(entry)
    else:
        try:
            node.value = scalar_value(tag, element.text or "")
        except ValueError as error:
            raise ValueError("%s %s: %s" % (tag, node.label() or "?", error)) from None
    return node


def value_text(node: Node, labels: dict | None = None) -> str:
    """A scalar as a prcxml writes it."""
    if node.tag == "bool":
        return "True" if node.value else "False"
    if node.tag == "float":
        return float_text(node.value)
    if node.tag == "hash40":
        return name_of(int(node.value), labels or {})
    if node.tag == "string":
        return str(node.value)
    return str(int(node.value))


def write_prcxml(root: Node, labels: dict | None = None) -> str:
    lines = ['<?xml version="1.0" encoding="utf-8"?>']
    _write(root, labels or {}, 0, lines, top=True)
    return "\n".join(lines) + "\n"


def _write(node: Node, labels: dict, depth: int, lines: list, top: bool = False) -> None:
    pad = "  " * depth
    attributes = ""
    if not top:
        if node.index is not None:
            attributes = " index=%s" % quoteattr(str(node.index))
        elif node.name:
            attributes = " hash=%s" % quoteattr(node.name)
    if node.tag in CONTAINERS:
        if not node.children:
            lines.append("%s<%s%s />" % (pad, node.tag, attributes))
            return
        lines.append("%s<%s%s>" % (pad, node.tag, attributes))
        for child in node.children:
            _write(child, labels, depth + 1, lines)
        lines.append("%s</%s>" % (pad, node.tag))
        return
    lines.append("%s<%s%s>%s</%s>" % (pad, node.tag, attributes, escape(value_text(node, labels)), node.tag))


FIGHTER, ITEM, STAGE, ENEMY = "fighter", "item", "stage", "enemy"
ENEMY_KINDS = {"yellow_devil": "yellowdevil", "dark_emperor": "subetenoyaminoou",
               "flying_man": "flyingman", "metal_face": "metalface", "nabbit": "nabbit"}
COMMON_FILES = ("common", "item", "etc", "power_up", "effect", "sound")


@dataclass(frozen=True)
class Target:
    """One prcxml a clone can ship: where it goes in the pack, the game file it
    starts from, and how much of that file Dionysus reads."""
    key: str
    family: str
    title: str
    path: str
    source: str = ""
    table: str = ""
    match: str = ""
    value: str = ""
    top_only: bool = False
    whole_row: bool = False
    by_index: bool = False
    own_keys: bool = False
    values: str = ""
    note: str = ""


TARGETS = (
    Target("vl", FIGHTER, "vl.prc values", "fighter/{name}/param/vl.prcxml",
           "fighter/{base}/param/vl.prc", own_keys=True, values="vl.tsv",
           note="Dionysus sets every number under a group, or in the first row of a list. Change "
                "anything else (a later row, a list inside a group, a hash40, text) and Save also "
                "writes the clone's own vl.prc, a copy of the base's, for ARCropolis to patch."),
    Target("fighter_param", FIGHTER, "fighter_param.prc row", "fighter/{name}/param/fighter_param.prcxml",
           "fighter/common/param/fighter_param.prc", "fighter_param_table", "fighter_kind", "fighter_kind_{base}",
           values="fighter_param.tsv",
           note="The clone's row: walk and run speeds, jumps, weight, scale, ..."),
    Target("fighter_param_motion", FIGHTER, "fighter_param_motion.prc row",
           "fighter/{name}/param/fighter_param_motion.prcxml",
           "fighter/common/param/fighter_param_motion.prc", "fighter_param_motion_table", "fighter_kind",
           "fighter_kind_{base}", values="fighter_param_motion.tsv",
           note="The clone's row: dodge, roll and air dodge timings."),
) + tuple(
    Target(name, FIGHTER, "%s.prc" % name, "fighter/{name}/param/%s.prcxml" % name,
           "fighter/common/param/%s.prc" % name, top_only=True, values="fighter_common.tsv",
           note="Top-level values only; lists and the match-level fields stay everyone's.")
    for name in COMMON_FILES
) + (
    Target("cpu", FIGHTER, "computer player row", "fighter/{name}/ai/param/fighter_param.prcxml",
           "fighter/common/ai/param/fighter_param.prc", "base", "name_hash", "fighter_kind_{base}",
           values="cpu.tsv",
           note="Recovery reach, attack ranges, Final Smash range. final_type is a label and stays the base's."),
    Target("item_common", ITEM, "item/common/param/param.prc row", "{top}/{name}/param/common_param.prcxml",
           "item/common/param/param.prc", "params", "name_hash", "{base}", values="item_common.tsv",
           note="The item's row: throw speeds, kinds, nodes. group cannot be set."),
    Target("item_param", ITEM, "the item's own param.prc", "{top}/{name}/param/param.prcxml",
           "{top}/{base}/param/param.prc", own_keys=True, values="item_param.tsv",
           note="Values the item's scripts read, keys of your own included. Change a later row, a "
                "list inside a group, a hash40 or text and Save also writes the item's own param.prc, "
                "a copy of the base's, for ARCropolis to patch."),
    Target("enemy_common", ENEMY, "enemy/common/common.prc row", "enemy/{name}/common.prcxml",
           "enemy/common/common.prc", "enemy_param_table", "kind", "enemy_kind_{base}",
           values="enemy_common.tsv",
           note="The enemy's row: hp, weight, sizes, capture. Labels stay the base's."),
    Target("enemy_param", ENEMY, "params of its own", "enemy/{name}/param/param.prcxml", own_keys=True,
           note="Keys your code reads with WorkModule::get_param_* and the group param."),
    Target("item_switch", STAGE, "item switches", "stage/{name}/{tree}/param/item_switch_param.prcxml",
           "item/common/param/item_switch_param.prc", "itsw_normal", "name", "{base}", by_index=True,
           values="item_switch.tsv",
           note="1 lets the item drop on the stage, 0 leaves it out."),
    Target("stage_sound", STAGE, "reverb and sound", "stage/{name}/{tree}/param/stage_sound_settings.prcxml",
           "param/sound/stage_sound_settings.prc", "info_", "place_id_", "{base}",
           values="stage_sound.tsv",
           note="reverb_type_: 0 none, 1 outdoors, 2 to 4 small, medium and large rooms, 10 Hanenbow's delay."),
    Target("stage_area", STAGE, "computer player box", "stage/{name}/{tree}/param/stage_param.prcxml",
           "fighter/common/ai/param/stage_param.prc", "area", "stage_name", "{base}", whole_row=True,
           values="stage_area.tsv",
           note="The Normal form's box: x0, y0, x1, y1, all four."),
    Target("stage_param", STAGE, "params of its own", "stage/{name}/{tree}/param/param.prcxml", own_keys=True,
           note="Keys your code reads with dionysus_api::stage::param_float."),
)


def targets(family: str) -> list:
    return [target for target in TARGETS if target.family == family]


@dataclass(frozen=True)
class Names:
    """What a part's paths are filled with: the clone's name or place, its base
    (fighter, item, enemy kind word or donor place), the item's top folder and
    the stage tree its Normal form loads."""
    name: str
    base: str = ""
    top: str = "item"
    tree: str = "normal"


def plain(text) -> str:
    """A name without the " (number)" a picker shows after it."""
    return str(text or "").split(" (")[0].strip()


def names_for(family: str, part: dict, item_root=None, item_name=None) -> "Names | None":
    """The names of a Workbench part, or None while it has no name yet."""
    if family == FIGHTER:
        name = part.get("resource_name")
        base = plain(part.get("base_resource_name") or part.get("base_fighter"))
        return Names(name, base) if name else None
    if family == ITEM:
        name, base = part.get("resource_name"), plain(part.get("base_item"))
        if not base and item_name is not None and isinstance(part.get("base_kind"), int):
            base = item_name(part["base_kind"]) or ""
        top = item_root(base) if item_root and base else "item"
        return Names(name, base, top or "item") if name else None
    if family == ENEMY:
        name, base = part.get("name"), part.get("base") or "nabbit"
        return Names(name, ENEMY_KINDS.get(base, base)) if name else None
    if family == STAGE:
        name = part.get("place")
        tree = "battle" if part.get("normal_tree") == "battle" else "normal"
        return Names(name, part.get("donor") or "", tree=tree) if name else None
    return None


def fill(template: str, names: Names) -> str:
    return template.format(name=names.name, base=names.base, top=names.top, tree=names.tree)


def own_prc(target: Target, names: Names, pack):
    """The pack's own prc a whole-file prcxml patches, when it ships one."""
    if target.table or target.top_only or not pack:
        return None
    candidate = (Path(pack) / fill(target.path, names)).with_suffix(".prc")
    return candidate if candidate.is_file() else None


def starting_tree(target: Target, game: Node, names: Names) -> Node:
    """The part of a game file this prcxml holds: the base's row, the top-level
    values, or the whole file. ValueError when the file has no such row."""
    if target.table:
        table = game.member(target.table)
        if table is None or table.tag != "list":
            raise ValueError("the file has no %s list" % target.table)
        wanted = fill(target.value, names)
        for row in table.children:
            identity = row.member(target.match) if row.tag == "struct" else None
            if identity is not None and identity.tag == "hash40" and identity.value == key(wanted):
                picked = row.copy()
                picked.index = 0
                return Node("struct", children=[Node("list", table.name, children=[picked])])
        raise ValueError("%s has no row whose %s is %s" % (target.table, target.match, wanted))
    if target.top_only:
        return Node("struct", children=[child.copy() for child in game.children if child.tag in SCALARS])
    return game.copy()


def first_row(tree: Node, table: str) -> "Node | None":
    found = tree.member(table)
    if found is None or found.tag != "list":
        return None
    return next((row for row in found.children if row.tag == "struct"), None)


GAME_VERSION = "13.0.5"
DATA = Path(__file__).resolve().parent / "data" / "params"
STEP = re.compile(r"\[(\d+)\]|([^.\[\]]+)")
_LOADED: dict = {}


def flat(node: Node, trail: str = ""):
    """(path, node) for each value under `node`, and for each empty group.
    A path is names joined with dots, list entries as [n]: param_special_s[0].speed."""
    for child in node.children:
        if child.index is not None:
            path = "%s[%d]" % (trail, child.index)
        else:
            path = "%s.%s" % (trail, child.name) if trail else child.name
        if child.tag in CONTAINERS and child.children:
            yield from flat(child, path)
        else:
            yield path, child


def cell(node: Node, labels: dict) -> str:
    """A value as a table holds it; a group holds nothing."""
    if node.tag in CONTAINERS:
        return ""
    text = value_text(node, labels)
    if any(mark in text for mark in "\t\r\n"):
        raise ValueError("%s holds a tab or a line break" % node.label())
    return text


def rebuild(entries) -> Node:
    """A tree from (path, type, value) rows, in the order flat gives them."""
    root = Node("struct")
    members: dict = {id(root): {}}
    for path, tag, text in entries:
        steps = [(int(index) if index else None, name) for index, name in STEP.findall(path)]
        if not steps or "".join("[%d]" % index if index is not None else name
                                for index, name in steps) != path.replace(".", ""):
            raise ValueError("%s is not a path" % path)
        if tag not in SCALARS and tag not in CONTAINERS:
            raise ValueError("%s: %s is not a param type" % (path, tag))
        at = root
        for position, (index, name) in enumerate(steps):
            last = position == len(steps) - 1
            wanted = tag if last else ("list" if steps[position + 1][0] is not None else "struct")
            if index is None:
                if at.tag != "struct":
                    raise ValueError("%s: %s is not a group of names" % (path, at.label() or "the top"))
                child = members[id(at)].get(name)
                if child is None:
                    child = Node(wanted, name)
                    members[id(at)][name] = child
                    at.children.append(child)
                elif last:
                    raise ValueError("%s is there twice" % path)
            else:
                if at.tag != "list":
                    raise ValueError("%s: %s is not a list" % (path, at.label() or "the top"))
                if index < len(at.children) and not last:
                    child = at.children[index]
                elif index == len(at.children):
                    child = Node(wanted, index=index)
                    at.children.append(child)
                else:
                    raise ValueError("%s is out of order" % path)
            if child.tag != wanted:
                raise ValueError("%s: %s is a %s, not a %s" % (path, child.label(), child.tag, wanted))
            if child.tag == "struct" and id(child) not in members:
                members[id(child)] = {}
            at = child
        if tag in SCALARS:
            try:
                at.value = scalar_value(tag, text)
            except ValueError as error:
                raise ValueError("%s: %s" % (path, error)) from None
    return root


def table_text(rows: list, labels: dict) -> str:
    """Rows of one layout as a table: the field paths, their types, then one line per row."""
    if not rows:
        raise ValueError("no rows")
    layout = [(path, node.tag) for path, node in flat(rows[0])]
    lines = ["\t".join(path for path, _ in layout), "\t".join(tag for _, tag in layout)]
    for row in rows:
        entries = list(flat(row))
        if [(path, node.tag) for path, node in entries] != layout:
            raise ValueError("row %s has a layout of its own" % row.label())
        lines.append("\t".join(cell(node, labels) for _, node in entries))
    return "\n".join(lines) + "\n"


def tree_text(heading: str, trees: list, labels: dict) -> str:
    """(name, tree) pairs as one value per line: name, path, type, value."""
    lines = ["\t".join((heading, "path", "type", "value"))]
    for name, tree in trees:
        for path, node in flat(tree):
            lines.append("\t".join((name, path, node.tag, cell(node, labels))))
    return "\n".join(lines) + "\n"


def _loaded(name: str):
    path = DATA / name
    stamp = (str(path), path.stat().st_mtime_ns)
    if stamp not in _LOADED:
        with path.open(encoding="utf-8", newline="") as handle:
            lines = handle.read().split("\n")
        _LOADED[stamp] = [line.split("\t") for line in lines if line]
    return _LOADED[stamp]


def table_row(name: str, column: str, wanted: str) -> "Node | None":
    """The row of a table whose `column` names `wanted`, as a tree."""
    lines = _loaded(name)
    if len(lines) < 2 or column not in lines[0]:
        raise ValueError("%s has no %s column" % (name, column))
    header, types = lines[0], lines[1]
    at, want = header.index(column), key(wanted)
    for values in lines[2:]:
        if len(values) == len(header) and key(values[at]) == want:
            return rebuild(zip(header, types, values))
    return None


def tree_rows(name: str, wanted: str) -> "Node | None":
    """One whole tree of a one-value-per-line table, or None when it has none by that name."""
    found = [line[1:] for line in _loaded(name)[1:] if line[0] == wanted]
    if not found:
        return None
    if any(len(entry) != 3 for entry in found):
        raise ValueError("%s has a line without path, type and value" % name)
    return rebuild(found)


def game_values(target: Target, names: Names) -> "Node | None":
    """The game's own copy a file starts from, the same part starting_tree cuts
    out of the game's file, read from the tables. None when the game has none."""
    if not target.values or not (names.base or target.top_only):
        return None
    if target.table:
        row = table_row(target.values, target.match, fill(target.value, names))
        if row is None:
            return None
        row.index = 0
        return Node("struct", children=[Node("list", target.table, children=[row])])
    return tree_rows(target.values, target.key if target.top_only else names.base)


def overlay(copy: Node, patch: Node) -> None:
    """Put a file's values over the game's copy; values only the file has are added."""
    if copy.tag == "struct":
        for child in patch.children:
            if not child.name:
                continue
            existing = copy.member(child.name)
            if existing is None:
                copy.children.append(child.copy())
            elif existing.tag in CONTAINERS and child.tag == existing.tag:
                overlay(existing, child)
            elif existing.tag not in CONTAINERS and child.tag not in CONTAINERS:
                existing.value = converted(existing.tag, child)
        return
    if copy.tag == "list":
        for position, child in enumerate(patch.children):
            if child.tag == "hash40" and child.value == DUMMY:
                continue
            index = child.index if child.index is not None else position
            if index < len(copy.children):
                existing = copy.children[index]
                if existing.tag in CONTAINERS and child.tag == existing.tag:
                    overlay(existing, child)
                elif existing.tag not in CONTAINERS and child.tag not in CONTAINERS:
                    existing.value = converted(existing.tag, child)
            else:
                entry = child.copy()
                entry.index = len(copy.children)
                copy.children.append(entry)


def converted(tag: str, node: Node):
    """A file's value in the game field's own type."""
    if tag == node.tag:
        return node.value
    if tag == "float" and node.tag in RANGES:
        return f32(node.value)
    if tag in RANGES and node.tag == "float":
        return int(round(node.value))
    if tag in RANGES and node.tag in RANGES:
        return int(node.value)
    if tag == "bool" and node.tag in RANGES:
        return bool(node.value)
    return node.value


def working_tree(target: Target, original: "Node | None", pack_file: "Node | None") -> tuple:
    """(what the editor shows, the game's copy to compare with), from the copy
    starting_tree or game_values gives. Without one the editor shows the pack's
    file alone."""
    if original is None:
        return (pack_file.copy() if pack_file is not None else Node("struct")), None
    current = original.copy()
    if pack_file is not None:
        if target.table:
            row, patch = first_row(current, target.table), first_row(pack_file, target.table)
            if row is not None and patch is not None:
                overlay(row, patch)
        else:
            overlay(current, pack_file)
    return current, original


def same(a: Node, b: Node) -> bool:
    if a.tag != b.tag:
        return False
    if a.tag == "float":
        return f32(a.value) == f32(b.value)
    return a.value == b.value


def changes(current: Node, original: "Node | None", by_index: bool = False) -> "Node | None":
    """Only what differs from the game's copy, keeping list positions: an entry
    before a changed one is an empty struct, or a dummy for a scalar, so it
    patches nothing. With by_index a scalar list keeps just its changed entries."""
    if current.tag not in CONTAINERS:
        if original is not None and original.tag not in CONTAINERS and same(current, original):
            return None
        return current.copy()
    out = Node(current.tag, current.name, current.index)
    if current.tag == "struct":
        for child in current.children:
            twin = original.member(child.name) if original is not None and original.tag == "struct" else None
            kept = changes(child, twin, by_index)
            if kept is not None:
                out.children.append(kept)
        if out.children or original is None:
            return out
        return None
    kept = []
    for position, child in enumerate(current.children):
        twin = None
        if original is not None and original.tag == "list" and position < len(original.children):
            twin = original.children[position]
        entry = changes(child, twin, by_index)
        if entry is not None:
            entry.index = position
            kept.append(entry)
    if not kept:
        return out if original is None else None
    if by_index:
        out.children = kept
        return out
    changed = {entry.index: entry for entry in kept}
    for position in range(max(changed) + 1):
        if position in changed:
            out.children.append(changed[position])
        elif current.children[position].tag == "struct":
            out.children.append(Node("struct", index=position))
        else:
            out.children.append(Node("hash40", index=position, value=DUMMY))
    return out


def file_tree(target: Target, current: Node, original: "Node | None", every_value: bool) -> Node:
    """What a save writes: every value, or what differs from the game's copy."""
    if every_value or original is None:
        return current.copy()
    if target.table:
        row, twin = first_row(current, target.table), first_row(original, target.table)
        if row is None:
            entry = Node("struct")
        elif target.whole_row:
            entry = row.copy()
        else:
            entry = changes(row, twin, target.by_index) or Node("struct")
        entry.index = 0
        return Node("struct", children=[Node("list", target.table, children=[entry])])
    return changes(current, original, target.by_index) or Node("struct")


def add_value(root: Node, name: str, tag: str, text: str, labels: dict) -> Node:
    """A key of your own: `field` at the top, or `group.field` inside a group
    (the first row of a list group). ValueError when it is there already."""
    if tag not in SCALARS:
        raise ValueError("pick a value type")
    name = name.strip()
    group, dot, field_name = name.partition(".")
    if not group or (dot and not field_name):
        raise ValueError("name it field or group.field")
    parent = root
    if field_name:
        parent = root.member(group)
        if parent is None:
            parent = Node("struct", group)
            root.children.append(parent)
        elif parent.tag == "list":
            row = next((entry for entry in parent.children if entry.tag == "struct"), None)
            if row is None:
                row = Node("struct", index=0)
                parent.children.insert(0, row)
            parent = row
        elif parent.tag != "struct":
            raise ValueError("%s is a value, not a group" % group)
    else:
        field_name = group
    if parent.member(field_name) is not None:
        raise ValueError("%s is there already: change its value" % name)
    value = scalar_value(tag, text)
    for part in (group, field_name):
        if not part.lower().startswith("0x"):
            labels.setdefault(key(part), part)
    if tag == "hash40" and not text.strip().lower().startswith("0x"):
        labels.setdefault(value, text.strip())
    node = Node(tag, field_name, value=value)
    parent.children.append(node)
    return node


def walk(node: Node):
    yield node
    for child in node.children:
        yield from walk(child)


def remove_value(root: Node, node: Node) -> bool:
    """Take a node out of the tree; False when it is not in it."""
    for parent in walk(root):
        if any(child is node for child in parent.children):
            parent.children = [child for child in parent.children if child is not node]
            return True
    return False


def trail_to(root: Node, node: Node) -> "list | None":
    if root is node:
        return []
    for child in root.children:
        below = trail_to(child, node)
        if below is not None:
            return [child] + below
    return None


def twin_of(current_root: Node, original_root: "Node | None", node: Node) -> "Node | None":
    """The game's node at the same place as `node`, or None."""
    if original_root is None:
        return None
    trail = trail_to(current_root, node)
    if trail is None:
        return None
    at = original_root
    for step in trail:
        if at.tag == "struct" and step.name:
            at = at.member(step.name)
        elif at.tag == "list" and step.index is not None and 0 <= step.index < len(at.children):
            at = at.children[step.index]
        else:
            return None
        if at is None:
            return None
    return at


def set_value(node: Node, text: str, labels: dict) -> None:
    """Change a scalar from what the editor typed; ValueError explains a refusal."""
    if node.tag in CONTAINERS:
        raise ValueError("a %s holds values; change those" % node.tag)
    node.value = scalar_value(node.tag, text)
    if node.tag == "hash40" and not text.strip().lower().startswith("0x"):
        labels.setdefault(node.value, text.strip())
