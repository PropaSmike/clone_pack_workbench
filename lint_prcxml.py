#!/usr/bin/env python3
"""The prcxml files a pack ships for its clones, checked the way Dionysus reads
them: a fighter's fighter_param / fighter_param_motion / common files, an item's
common_param.prcxml, a fighter's ai/param/fighter_param.prcxml, an enemy's
common.prcxml, a stage's item_switch_param.prcxml, stage_sound_settings.prcxml
and stage_param.prcxml, and the keys of their own an item, enemy or stage takes
from param.prcxml. Also warns about a prcxml for the shared file itself, which
changes the vanilla rows."""

import os
import sys
import xml.etree.ElementTree as ElementTree
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
FIELDS_FILE = os.path.join(HERE, "clone_pack_gui", "data", "param_fields.tsv")

FIGHTER_FILES = {
    "fighter_param": ("fighter_param_table", "fighter_param"),
    "fighter_param_motion": ("fighter_param_motion_table", "fighter_param_motion"),
    "common": (None, "common"),
    "item": (None, "common"),
    "etc": (None, "common"),
    "power_up": (None, "common"),
    "effect": (None, "common"),
    "sound": (None, "common"),
}
ITEM_TOPS = ("item", "assist", "pokemon", "boss")
ITEM_FILE = "common_param.prcxml"
CPU_FILE = "fighter_param.prcxml"
ENEMY_FILE = "common.prcxml"
STAGE_FILE = "item_switch_param.prcxml"
SOUND_FILE = "stage_sound_settings.prcxml"
AREA_FILE = "stage_param.prcxml"
STAGE_FILES = (STAGE_FILE, SOUND_FILE, AREA_FILE)
ASSET_FILE = "param.prcxml"
REVERB_PRESETS = 11
INTEGERS = ("sbyte", "byte", "short", "ushort", "int", "uint")
NUMBERS = INTEGERS + ("float",)
AREA_FIELDS = ("x0", "y0", "x1", "y1")
SHARED_STAGE_FILES = {
    "item/common/param/item_switch_param.prcxml": "item lists",
    "param/sound/stage_sound_settings.prcxml": "reverb and sound settings",
    "fighter/common/ai/param/stage_param.prcxml": "computer player areas",
}
IDENTITY = ("fighter_kind", "name", "name_hash", "kind")
SCALARS = ("bool", "sbyte", "byte", "short", "ushort", "int", "uint", "float", "hash40", "string")
SHOWN = 6

_fields = None


def hash40(text):
    data = text.encode("utf8")
    return (len(data) << 32) | (zlib.crc32(data) & 0xffffffff)


def key(text):
    text = (text or "").strip()
    if text[:2].lower() == "0x":
        try:
            return int(text[2:], 16)
        except ValueError:
            pass
    return hash40(text)


def fields():
    global _fields
    if _fields is None:
        _fields = {}
        if os.path.isfile(FIELDS_FILE):
            with open(FIELDS_FILE, encoding="utf-8") as handle:
                next(handle, None)
                for line in handle:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) == 4:
                        _fields.setdefault(parts[0], {})[int(parts[1], 16)] = (parts[2], parts[3])
    return _fields


def listing(names):
    shown = list(names[:SHOWN])
    if len(names) > SHOWN:
        shown.append("%d more" % (len(names) - SHOWN))
    return ", ".join(shown)


def parse(path):
    """The root struct, or the reason Dionysus would skip the file."""
    try:
        root = ElementTree.parse(path).getroot()
    except (ElementTree.ParseError, OSError, UnicodeDecodeError) as error:
        return None, "is not readable XML (%s)" % error
    if root.tag != "struct":
        return None, "must start with <struct>"
    return root, None


def switch_size():
    path = os.path.join(HERE, "clone_pack_gui", "data", "item_switch.tsv")
    if not os.path.isfile(path):
        return 0
    with open(path, encoding="utf-8") as handle:
        return max(sum(1 for line in handle if line.strip()) - 1, 0)


def is_dummy(element):
    return element.tag == "hash40" and (element.text or "").strip() == "dummy"


def member(root, name):
    wanted = hash40(name)
    for child in root:
        if key(child.get("hash")) == wanted:
            return child
    return None


def rows(root, list_name):
    found = member(root, list_name)
    if found is None or found.tag != "list":
        return []
    return [child for child in found if child.tag == "struct"]


def field_name(element, table):
    known = fields().get(table, {}).get(key(element.get("hash")))
    if known and known[0]:
        return known[0]
    return element.get("hash") or "?"


def check_row(relative, row, tables, numeric_label_ok=False):
    """Every field of one row against the engine's tables: unknown names, labels
    and lists Dionysus leaves out."""
    identity = {hash40(name) for name in IDENTITY}
    unknown, left_out = [], []
    for element in row:
        hashed = key(element.get("hash"))
        if hashed in identity:
            continue
        found = None
        for table in tables:
            found = fields().get(table, {}).get(hashed)
            if found:
                name = found[0] or element.get("hash")
                kind = found[1]
                break
        if element.tag in ("list", "struct"):
            left_out.append("%s (a %s)" % (found[0] if found and found[0] else element.get("hash"), element.tag))
            continue
        if element.tag not in SCALARS:
            continue
        if not found:
            unknown.append(element.get("hash") or "?")
            continue
        if kind == "fixed":
            left_out.append("%s (fixed by the game)" % name)
        elif kind == "Label":
            left_out.append("%s (a label)" % name)
        elif kind == "Hash40" and element.tag != "hash40":
            left_out.append("%s (takes a hash40)" % name)
        elif kind == "Hash40" and not numeric_label_ok:
            left_out.append("%s (a hash40)" % name)
        elif kind not in ("Hash40", "Enum") and element.tag == "hash40":
            left_out.append("%s (a label)" % name)
        elif element.tag == "string":
            left_out.append("%s (text)" % name)
    findings = []
    if unknown:
        findings.append(("WARN", "%s: no field called %s in this file; Dionysus leaves %s out"
                         % (relative, listing(unknown), "it" if len(unknown) == 1 else "them")))
    if left_out:
        findings.append(("INFO", "%s: Dionysus leaves out %s" % (relative, listing(left_out))))
    return findings


def check_fighter(relative, root, stem):
    list_name, table = FIGHTER_FILES[stem]
    if list_name is None:
        return check_row(relative, root, [table])
    found = rows(root, list_name)
    if not found:
        return [("WARN", "%s has no <list hash=\"%s\"> row; Dionysus reads nothing from it"
                 % (relative, list_name))]
    findings = []
    if len(found) > 1:
        findings.append(("WARN", "%s has %d rows; Dionysus reads only the first, the clone's"
                         % (relative, len(found))))
    return findings + check_row(relative, found[0], [table])


def check_item(relative, root):
    found = rows(root, "params")
    if not found:
        return [("WARN", "%s has no <list hash=\"params\"> row; Dionysus reads nothing from it" % relative)]
    findings = []
    if len(found) > 1:
        findings.append(("WARN", "%s has %d rows; Dionysus reads only the first, the item's"
                         % (relative, len(found))))
    return findings + check_row(relative, found[0], ["item_float", "item_word", "item_hash"], True)


def check_table_row(relative, root, list_name, table, owner):
    found = rows(root, list_name)
    if not found:
        return [("WARN", "%s has no <list hash=\"%s\"> row; Dionysus reads nothing from it" % (relative, list_name))]
    findings = []
    if len(found) > 1:
        findings.append(("WARN", "%s has %d rows; Dionysus reads only the first, the %s's"
                         % (relative, len(found), owner)))
    return findings + check_row(relative, found[0], [table], True)


def values_under(element, path):
    """The path of every value under `element`, dummies left out."""
    if element.tag in SCALARS:
        if not is_dummy(element):
            yield path
        return
    for position, child in enumerate(element):
        if element.tag == "list":
            inner = "%s[%s]" % (path, child.get("index", position))
        else:
            inner = "%s.%s" % (path, child.get("hash") or "?")
        yield from values_under(child, inner)


def own_file_values(root):
    """The values Dionysus cannot hand over itself, as "path (why)": it reads the
    numbers under a top-level group, or in the first row of a top-level list."""
    found = []

    def unread(element, path, why):
        found.extend("%s (%s)" % (inner, why) for inner in values_under(element, path))

    def numbers_of(group, path):
        for field in group:
            inner = "%s.%s" % (path, field.get("hash") or "?")
            if field.tag == "hash40":
                unread(field, inner, "a hash40")
            elif field.tag == "string":
                unread(field, inner, "text")
            elif field.tag in ("list", "struct"):
                unread(field, inner, "a %s inside a group" % field.tag)

    for group in root:
        name = group.get("hash") or "?"
        if group.tag == "hash40":
            unread(group, name, "a hash40")
        elif group.tag == "string":
            unread(group, name, "text")
        elif group.tag == "struct":
            numbers_of(group, name)
        elif group.tag == "list":
            entries = [(child.get("index", position), child) for position, child in enumerate(group)
                       if not is_dummy(child)]
            if not entries:
                continue
            if entries[0][1].tag != "struct":
                unread(group, name, "a list of values")
                continue
            numbers_of(entries[0][1], "%s[%s]" % (name, entries[0][0]))
            for index, entry in entries[1:]:
                unread(entry, "%s[%s]" % (name, index), "past the list's first row")
    return found


def check_vl(relative, root, own_file=None):
    """own_file: the copy of the file the pack can ship (vl.prc, an item's param.prc),
    True when it ships it, None when the part has no such file."""
    left_out = own_file_values(root)
    if not left_out or own_file is True:
        return []
    if own_file is None:
        return [("INFO", "%s: Dionysus leaves out %s" % (relative, listing(left_out)))]
    return [("WARN", "%s: Dionysus leaves out %s. Those reach the game only through your own %s, which "
             "ARCropolis patches with this file; Save on the Workbench's Parameters > prcxml files tab writes it"
             % (relative, listing(left_out), own_file))]


def check_asset(relative, root, family, own_file=None):
    if not rows(root, "params"):
        return check_vl(relative, root, own_file)
    if family in ITEM_TOPS:
        return [("WARN", "%s looks written for item/common/param/param.prc; ARCropolis applies it to your "
                 "own param.prc instead. Name it %s" % (relative, ITEM_FILE))]
    return [("WARN", "%s holds a params list; Dionysus does not use the file" % relative)]


def check_stage(relative, root):
    found = rows(root, "itsw_normal")
    if not found:
        return [("WARN", "%s has no <list hash=\"itsw_normal\"> row; Dionysus reads nothing from it" % relative)]
    table = member(found[0], "table")
    if table is None or table.tag != "list":
        return [("WARN", "%s: its itsw_normal row has no table list; Dionysus reads nothing from it" % relative)]
    findings = []
    if len(found) > 1:
        findings.append(("WARN", "%s has %d itsw_normal rows; Dionysus reads only the first"
                         % (relative, len(found))))
    size = switch_size()
    entries = [child for child in table if not is_dummy(child)]
    beyond = []
    for position, child in enumerate(entries):
        index = child.get("index")
        index = int(index) if index and index.strip().isdigit() else position
        if size and index >= size:
            beyond.append(str(index))
        elif child.tag not in ("byte", "sbyte", "short", "ushort", "int", "uint", "bool"):
            beyond.append("%s (a %s)" % (index, child.tag))
    if beyond:
        findings.append(("WARN", "%s: entries %s are not items the game switches; Dionysus skips them"
                         % (relative, listing(beyond))))
    return findings


def first_row(relative, root, list_name):
    found = rows(root, list_name)
    if not found:
        return None, [("WARN", "%s has no <list hash=\"%s\"> row; Dionysus reads nothing from it"
                       % (relative, list_name))]
    findings = []
    if len(found) > 1:
        findings.append(("WARN", "%s has %d rows; Dionysus reads only the first, the stage's"
                         % (relative, len(found))))
    return found[0], findings


def check_stage_sound(relative, root):
    row, findings = first_row(relative, root, "info_")
    if row is None:
        return findings
    unknown, left_out = [], []
    for element in row:
        hashed = key(element.get("hash"))
        name = element.get("hash") or "?"
        if hashed == hash40("place_id_"):
            continue
        if hashed == hash40("reverb_type_"):
            text = (element.text or "").strip()
            if element.tag not in INTEGERS:
                left_out.append("reverb_type_ (takes a whole number)")
            elif not text.isdigit() or int(text) >= REVERB_PRESETS:
                left_out.append("reverb_type_ (0 to %d)" % (REVERB_PRESETS - 1))
        elif hashed in (hash40("scale_"), hash40("offset_")):
            if element.tag not in NUMBERS:
                left_out.append("%s (takes a number)" % name)
        else:
            unknown.append(name)
    if unknown:
        findings.append(("WARN", "%s: no field called %s in this file; Dionysus leaves %s out"
                         % (relative, listing(unknown), "it" if len(unknown) == 1 else "them")))
    if left_out:
        findings.append(("WARN", "%s: Dionysus leaves out %s" % (relative, listing(left_out))))
    return findings


def check_stage_area(relative, root):
    row, findings = first_row(relative, root, "area")
    if row is None:
        return findings
    unknown, found = [], set()
    for element in row:
        hashed = key(element.get("hash"))
        if hashed == hash40("stage_name"):
            continue
        named = [field for field in AREA_FIELDS if hash40(field) == hashed]
        if not named:
            unknown.append(element.get("hash") or "?")
        elif element.tag in NUMBERS:
            found.add(named[0])
    if unknown:
        findings.append(("WARN", "%s: no field called %s in this file; Dionysus leaves %s out"
                         % (relative, listing(unknown), "it" if len(unknown) == 1 else "them")))
    missing = [field for field in AREA_FIELDS if field not in found]
    if missing:
        findings.append(("WARN", "%s needs a number for %s too; Dionysus does not use the file"
                         % (relative, ", ".join(missing))))
    return findings


def shipped_prcxml(mod_dir):
    for folder, _, files in os.walk(mod_dir):
        for name in files:
            if name.lower().endswith(".prcxml"):
                full = os.path.join(folder, name)
                yield os.path.relpath(full, mod_dir).replace(os.sep, "/"), full


def lint_pack(mod_dir, families=("fighter", "item", "enemy", "stage")):
    findings = []
    for relative, full in sorted(shipped_prcxml(mod_dir)):
        parts = relative.split("/")
        lower = relative.lower()
        stem = parts[-1][:-len(".prcxml")]
        if lower.startswith("fighter/common/param/") and "fighter" in families:
            findings.append(("WARN", "%s changes %s for every fighter of every player. For a clone, "
                             "put it in fighter/<clone>/param/" % (relative, stem + ".prc")))
            continue
        if lower == "fighter/common/ai/param/fighter_param.prcxml" and "fighter" in families:
            findings.append(("WARN", "%s changes the computer players of every fighter. For a clone, "
                             "put it in fighter/<clone>/ai/param/" % relative))
            continue
        if lower == "enemy/common/common.prcxml" and "enemy" in families:
            findings.append(("WARN", "%s changes every enemy of every match. For a clone, "
                             "put it in enemy/<clone>/" % relative))
            continue
        if lower == "item/common/param/param.prcxml" and "item" in families:
            findings.append(("WARN", "%s changes the vanilla items' rows for every player. For a clone, "
                             "put it in item/<item>/param/%s" % (relative, ITEM_FILE)))
            continue
        if lower in SHARED_STAGE_FILES and "stage" in families:
            findings.append(("WARN", "%s changes the vanilla stages' %s for every player. For a "
                             "cloned stage, put it in stage/<place>/normal/param/"
                             % (relative, SHARED_STAGE_FILES[lower])))
            continue
        role = None
        if ("fighter" in families and len(parts) == 5 and parts[0] == "fighter" and parts[2:4] == ["ai", "param"]
                and parts[4] == CPU_FILE):
            role = "cpu"
        elif "enemy" in families and len(parts) == 3 and parts[0] == "enemy" and parts[2] == ENEMY_FILE:
            role = "enemy"
        elif "enemy" in families and len(parts) == 4 and parts[0] == "enemy" and parts[2:4] == ["param", ASSET_FILE]:
            role = "asset"
        elif "fighter" in families and len(parts) == 4 and parts[0] == "fighter" and parts[2] == "param":
            if stem in FIGHTER_FILES:
                role = "fighter"
            elif stem == "vl":
                role = "vl"
            else:
                findings.append(("WARN", "%s is not a file Dionysus reads for a clone (it reads %s)"
                                 % (relative, ", ".join(name + ".prcxml" for name in list(FIGHTER_FILES) + ["vl"]))))
        elif "item" in families and len(parts) == 4 and parts[0] in ITEM_TOPS and parts[2] == "param":
            if parts[3] == ITEM_FILE:
                role = "item"
            elif parts[3] == ASSET_FILE:
                role = "asset"
        elif ("stage" in families and len(parts) == 5 and parts[0] == "stage" and parts[3] == "param"
              and parts[2] in ("normal", "battle") and parts[4] in STAGE_FILES + (ASSET_FILE,)):
            role = "asset" if parts[4] == ASSET_FILE else parts[4]
        if role is None:
            continue
        root, problem = parse(full)
        if problem:
            findings.append(("ERROR", "%s %s; Dionysus skips the file" % (relative, problem)))
            continue
        if role == "fighter":
            findings += check_fighter(relative, root, stem)
        elif role == "item":
            findings += check_item(relative, root)
        elif role == "vl":
            findings += check_vl(relative, root, os.path.isfile(full[:-3]) or relative[:-3])
        elif role == "asset":
            own = (os.path.isfile(full[:-3]) or relative[:-3]) if parts[0] in ITEM_TOPS else None
            findings += check_asset(relative, root, parts[0], own)
        elif role == "cpu":
            findings += check_table_row(relative, root, "base", "cpu", "clone")
        elif role == "enemy":
            findings += check_table_row(relative, root, "enemy_param_table", "enemy", "enemy")
        elif role == SOUND_FILE:
            findings += check_stage_sound(relative, root)
        elif role == AREA_FILE:
            findings += check_stage_area(relative, root)
        else:
            findings += check_stage(relative, root)
    return findings


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    findings = lint_pack(argv[0])
    for level, message in findings:
        print("%s: %s" % (level, message))
    return 1 if any(level == "ERROR" for level, _ in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
