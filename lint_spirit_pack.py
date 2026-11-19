#!/usr/bin/env python3
"""Check a spirit pack: spirit.toml and the files its spirits need."""
import argparse
import os
import re
import sys
import xml.etree.ElementTree as ElementTree
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = "spirit.toml"
DATA = os.path.join(HERE, "clone_pack_gui", "data")
DEFAULT_ARC_INDEX = os.path.join(HERE, "arc_index")
SAVE_FIRST, SAVE_LAST = 1513, 1999
ROOM = SAVE_LAST - SAVE_FIRST + 1
MAX_FIGHTERS = 16
BOARD_FIRST, BOARD_LAST = 11, 31
BOARD_ROOM = BOARD_LAST - BOARD_FIRST + 1
MAX_BOARD_SPIRITS = 64
MAX_NAME = 64
GAME_BOARDS = ("jack", "brave", "buddy", "dolly", "master", "tantan", "pickel", "edge", "flame_first", "demon",
               "trail")
BOARD_KEYS = ("id", "base", "name", "background", "spirits", "art")
BOARD_FIELDS = {"value": "uint", "bgm_id": "hash40", "prize_id": "hash40", "layout_no": "uint",
                "shop_item_tag": "hash40"}
BOARD_FIXED = ("label", "save_no", "spirit_list")
GAME_BACKGROUNDS = 11
BACKGROUND = "ui/layout/patch/spirits_board_special_bg_%02d/spirits_board_special_bg_%02d/layout.arc"
PRCXML_FILES = {"spirit": "spirit/ui_spirit_db.prcxml", "battle": "spirit/ui_spirits_battle_db.prcxml",
                "layout": "spirit/ui_spirit_layout_db.prcxml", "board": "spirit/spirits_board_special_param.prcxml"}
XML_INTEGERS = ("sbyte", "byte", "short", "ushort", "int", "uint")
FIXED = {
    "spirit": {"ui_spirit_id", "name_id", "save_no", "directory_id", "fixed_no"},
    "battle": {"battle_id"},
    "fighter": {"battle_id"},
    "layout": {"ui_spirit_layout_id"},
}
INTEGERS = {"sbyte": (-0x80, 0x7F), "byte": (0, 0xFF), "short": (-0x8000, 0x7FFF), "ushort": (0, 0xFFFF),
            "int": (-0x80000000, 0x7FFFFFFF), "uint": (0, 0xFFFFFFFF)}
ID_RE = re.compile(r"^[a-z0-9_]{1,48}$")
FIELD_RE = re.compile(r"^([a-z0-9_]{1,48}|0x[0-9a-fA-F]{1,10})$")


def hash40(text):
    data = text.encode()
    return (len(data) << 32) | (zlib.crc32(data) & 0xFFFFFFFF)


def strip_comment(line):
    quoted = False
    for index, char in enumerate(line):
        if char == '"':
            quoted = not quoted
        elif char == "#" and not quoted:
            return line[:index]
    return line


def parse_value(raw):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == "[" and raw[-1] == "]":
        items = []
        for item in raw[1:-1].split(","):
            item = item.strip()
            if not item:
                continue
            if len(item) < 2 or item[0] != '"' or item[-1] != '"':
                return None
            items.append(item[1:-1].strip())
        return ("list", items)
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return ("text", raw[1:-1])
    if raw in ("true", "false"):
        return ("flag", raw == "true")
    digits = raw.replace("_", "")
    try:
        return ("number", int(digits))
    except ValueError:
        pass
    if any(mark in digits for mark in ".eE"):
        try:
            return ("float", float(digits))
        except ValueError:
            pass
    return None


def field_of(key):
    parts = [part.strip() for part in key.split(".")]
    if len(parts) == 1:
        table, fighter, name = "spirit", 0, parts[0]
    elif len(parts) == 2 and parts[0] in ("battle", "layout"):
        table, fighter, name = parts[0], 0, parts[1]
    elif len(parts) == 3 and parts[0] == "fighter" and parts[1].isdigit() and int(parts[1]) < MAX_FIGHTERS:
        table, fighter, name = "fighter", int(parts[1]), parts[2]
    else:
        return None
    return (table, fighter, name) if FIELD_RE.match(name) else None


def parse(text):
    """(spirits, problems). Each spirit: id, base, fighters, fields [(table, fighter, name, value, line)]."""
    spirits, _, problems = parse_manifest(text)
    return spirits, problems


def board_key(board, key, value, number):
    """None, or the problem with one key = value line of a [[board]]."""
    sort, raw = value
    if key in BOARD_FIXED:
        return "line %d: the engine sets %s itself" % (number, key)
    if key not in BOARD_KEYS:
        if not FIELD_RE.match(key):
            return "line %d: %s is not a board key (%s, or a field of the board row)" % (
                number, key, ", ".join(BOARD_KEYS))
        if sort == "list":
            return "line %d: %s takes one value, not a list" % (number, key)
        board["fields"][key] = (value, number)
        return None
    if key == "art":
        if sort != "text" or not raw.strip().lower().endswith("/layout.arc") or "/" not in raw.strip()[:-11]:
            return "line %d: art takes a layout path ending in /layout.arc" % number
        board["art"] = raw.strip().lower()
        return None
    if key == "spirits":
        if sort != "list":
            return 'line %d: spirits takes a list on one line, like ["geno", "sidestepper"]' % number
        if len(raw) > MAX_BOARD_SPIRITS:
            return "line %d: a board holds up to %d spirits" % (number, MAX_BOARD_SPIRITS)
        bad = [item for item in raw if not FIELD_RE.match(item)]
        if bad:
            return "line %d: %s is not a spirit id" % (number, bad[0])
        board["spirits"] = raw
        return None
    if sort != "text":
        return "line %d: %s takes text" % (number, key)
    if key == "name" and (len(raw.encode()) > MAX_NAME or "\n" in raw or "\r" in raw):
        return "line %d: name takes one line of up to %d bytes" % (number, MAX_NAME)
    board[key] = raw if key == "name" else raw.strip()
    return None


def parse_manifest(text):
    """(spirits, boards, problems). Each board: id, base, name, background, spirits, art, fields
    {field: (value, line)}, line."""
    spirits, boards, problems, block = [], [], [], None

    def finish_board(done):
        if not done["id"]:
            problems.append(("ERROR", "line %d: a [[board]] has no id" % done["line"]))
        elif not ID_RE.match(done["id"]):
            problems.append(("ERROR", "line %d: id %r takes lower case letters, digits and _, up to 48"
                             % (done["line"], done["id"])))
        elif any(other["id"] == done["id"] for other in boards):
            problems.append(("ERROR", "line %d: board %s is declared twice" % (done["line"], done["id"])))
        elif not done["base"]:
            problems.append(("ERROR", "line %d: board %s has no base" % (done["line"], done["id"])))
        elif not done["spirits"]:
            problems.append(("ERROR", "line %d: board %s has no spirits" % (done["line"], done["id"])))
        elif len(boards) >= BOARD_ROOM:
            problems.append(("ERROR", "line %d: more than %d boards; the save has board numbers for %d"
                             % (done["line"], BOARD_ROOM, BOARD_ROOM)))
        else:
            boards.append(done)

    def finish(done):
        if done.get("board"):
            finish_board(done)
            return
        if not done["id"]:
            problems.append(("ERROR", "line %d: a [[spirit]] has no id" % done["line"]))
        elif not ID_RE.match(done["id"]):
            problems.append(("ERROR", "line %d: id %r takes lower case letters, digits and _, up to 48"
                             % (done["line"], done["id"])))
        elif any(other["id"] == done["id"] for other in spirits):
            problems.append(("ERROR", "line %d: id %s is declared twice" % (done["line"], done["id"])))
        elif not done["base"]:
            problems.append(("ERROR", "line %d: spirit %s has no base" % (done["line"], done["id"])))
        else:
            spirits.append(done)

    for number, raw in enumerate(text.splitlines(), 1):
        line = strip_comment(raw).strip()
        if not line:
            continue
        if line.startswith("[[") and line.endswith("]]"):
            if block is not None:
                finish(block)
            table = line[2:-2].strip()
            if table == "board":
                block = {"board": True, "id": "", "base": "", "name": "", "background": "", "spirits": [],
                         "art": "", "fields": {}, "line": number}
                continue
            if table != "spirit":
                problems.append(("ERROR", "line %d: unknown table %s" % (number, line)))
                block = None
                continue
            block = {"id": "", "base": "", "fighters": None, "fields": [], "line": number}
            continue
        if "=" not in line or block is None:
            problems.append(("ERROR", "line %d: not a key = value line inside a [[spirit]] or [[board]]" % number))
            continue
        key, raw_value = (part.strip() for part in line.split("=", 1))
        value = parse_value(raw_value)
        if value is None:
            problems.append(("ERROR", "line %d: %s has a value the engine cannot read" % (number, key)))
            continue
        if block.get("board"):
            problem = board_key(block, key, value, number)
            if problem:
                problems.append(("ERROR", problem))
            continue
        if value[0] == "list":
            problems.append(("ERROR", "line %d: %s takes one value, not a list" % (number, key)))
            continue
        if key in ("id", "base"):
            if value[0] != "text":
                problems.append(("ERROR", "line %d: %s takes text" % (number, key)))
            else:
                block[key] = value[1].strip()
            continue
        if key == "fighters":
            if value[0] != "number" or not 1 <= value[1] <= MAX_FIGHTERS:
                problems.append(("ERROR", "line %d: fighters takes 1 to %d" % (number, MAX_FIGHTERS)))
            else:
                block["fighters"] = value[1]
            continue
        found = field_of(key)
        if found is None:
            problems.append(("ERROR", "line %d: %s is not a field key (field, battle.field, layout.field "
                                      "or fighter.N.field, N up to %d)" % (number, key, MAX_FIGHTERS - 1)))
            continue
        table, fighter, name = found
        if name in FIXED[table]:
            problems.append(("ERROR", "line %d: the engine sets %s itself" % (number, key)))
            continue
        block["fields"].append((table, fighter, name, value, number))
    if block is not None:
        finish(block)
    return spirits, boards, problems


def at(line):
    """Where a key was given: a line of spirit.toml, or a row of a prcxml."""
    return "line %d" % line if isinstance(line, int) else line


def xml_value(tag, text):
    """One prcxml scalar as spirit.toml's value, or None when it does not hold one."""
    text = (text or "").strip()
    if tag in ("hash40", "string"):
        return ("text", text)
    if tag == "bool":
        return ("flag", text.lower() in ("true", "1")) if text.lower() in ("true", "false", "1", "0") else None
    try:
        if tag == "float":
            return ("float", float(text))
        if tag in XML_INTEGERS:
            return ("number", int(text, 0))
    except ValueError:
        return None
    return None


def xml_rows(path, listing):
    """The rows of one list of a prcxml: each [(name, tag, text, element)]."""
    with open(path, encoding="utf-8-sig") as handle:
        root = ElementTree.fromstring(handle.read().encode("utf-8"))
    if root.tag != "struct":
        raise ValueError("the file must start with <struct>")
    rows = []
    for entry in root:
        if entry.tag == "list" and entry.get("hash") == listing:
            for row in entry:
                if row.tag == "struct":
                    rows.append([(child.get("hash") or "", child.tag, child.text, child) for child in row])
    return rows


def parse_prcxml(mod_dir):
    """(spirits, boards, problems) from the pack's spirit/ prcxml files, with the engine's rules."""
    spirits, boards, problems = [], [], []
    present = {table: os.path.join(mod_dir, *relative.split("/")) for table, relative in PRCXML_FILES.items()}
    present = {table: path for table, path in present.items() if os.path.isfile(path)}

    def rows(table, listing):
        try:
            return xml_rows(present[table], listing)
        except (OSError, ValueError, ElementTree.ParseError) as error:
            problems.append(("ERROR", "%s is not readable: %s" % (PRCXML_FILES[table], error)))
            return []

    def owner(row, key, table, number):
        found = (next((text for name, _, text, _ in row if name == key), None) or "").strip()
        hashed = int(found, 16) if re.match(r"^0x[0-9a-fA-F]+$", found) else hash40(found)
        spirit = next((s for s in spirits if s["id"] == found or hash40(s["id"]) == hashed), None)
        if spirit is None:
            problems.append(("ERROR", "%s row %d is for %s, which %s does not add"
                             % (PRCXML_FILES[table], number, found or "no spirit", PRCXML_FILES["spirit"])))
        return spirit

    def value(name, tag, text, table, number):
        found = xml_value(tag, text)
        if found is None:
            problems.append(("ERROR", "%s row %d: <%s> %s holds %r" % (PRCXML_FILES[table], number, tag, name, text)))
        return found

    if "spirit" in present:
        for number, row in enumerate(rows("spirit", "db_root"), 1):
            where = "%s row %d" % (PRCXML_FILES["spirit"], number)
            spirit = {"id": "", "base": "", "fighters": None, "fields": [], "line": where}
            name_id = ""
            for name, tag, text, _ in row:
                if name == "ui_spirit_id":
                    spirit["id"] = (text or "").strip()
                elif name == "name_id":
                    name_id = (text or "").strip()
                elif name == "base":
                    spirit["base"] = (text or "").strip()
                elif name not in FIXED["spirit"]:
                    found = value(name, tag, text, "spirit", number)
                    if found is not None:
                        spirit["fields"].append(("spirit", 0, name, found, where))
            if (spirit["id"].startswith("0x") or not ID_RE.match(spirit["id"])) and ID_RE.match(name_id) \
                    and not name_id.startswith("0x"):
                spirit["id"] = name_id
            if not ID_RE.match(spirit["id"]):
                problems.append(("ERROR", "%s: id %r takes lower case letters, digits and _, up to 48" % (where, spirit["id"])))
            elif any(other["id"] == spirit["id"] for other in spirits):
                problems.append(("ERROR", "%s: %s is added twice" % (where, spirit["id"])))
            elif not spirit["base"]:
                problems.append(("ERROR", "%s: %s names no base (<hash40 hash=\"base\">)" % (where, spirit["id"])))
            else:
                spirits.append(spirit)
    if "battle" in present:
        for number, row in enumerate(rows("battle", "battle_data_tbl"), 1):
            spirit = owner(row, "battle_id", "battle", number)
            for name, tag, text, _ in row:
                if spirit is not None and name not in FIXED["battle"]:
                    found = value(name, tag, text, "battle", number)
                    if found is not None:
                        spirit["fields"].append(("battle", 0, name, found, "%s row %d" % (PRCXML_FILES["battle"], number)))
        counts = {}
        for number, row in enumerate(rows("battle", "fighter_data_tbl"), 1):
            spirit = owner(row, "battle_id", "battle", number)
            if spirit is None:
                continue
            index = counts.get(spirit["id"], 0)
            if index >= MAX_FIGHTERS:
                problems.append(("ERROR", "%s: %s has more than %d fighters" % (PRCXML_FILES["battle"], spirit["id"], MAX_FIGHTERS)))
                continue
            for name, tag, text, _ in row:
                if name not in FIXED["fighter"] and name != "spirit_name":
                    found = value(name, tag, text, "battle", number)
                    if found is not None:
                        spirit["fields"].append(("fighter", index, name, found,
                                                 "%s fighter row %d" % (PRCXML_FILES["battle"], number)))
            counts[spirit["id"]] = index + 1
            spirit["fighters"] = index + 1
    if "layout" in present:
        for number, row in enumerate(rows("layout", "db_root"), 1):
            spirit = owner(row, "ui_spirit_layout_id", "layout", number)
            for name, tag, text, _ in row:
                if spirit is not None and name not in FIXED["layout"]:
                    found = value(name, tag, text, "layout", number)
                    if found is not None:
                        spirit["fields"].append(("layout", 0, name, found, "%s row %d" % (PRCXML_FILES["layout"], number)))
    if "board" in present:
        for number, row in enumerate(rows("board", "special_board_data_list"), 1):
            where = "%s row %d" % (PRCXML_FILES["board"], number)
            board = {"board": True, "id": "", "base": "", "name": "", "background": "", "spirits": [], "art": "",
                     "fields": {}, "line": where}
            for name, tag, text, element in row:
                text = (text or "").strip()
                if name == "label":
                    board["id"] = text[len("ui_chara_"):] if text.startswith("ui_chara_") else text
                elif name in ("base", "name", "background"):
                    board[name] = text
                elif name == "art":
                    board["art"] = text.lower()
                elif name == "spirit_list":
                    board["spirits"] = [(child.text or "").strip() for entry in element for child in entry
                                        if child.get("hash") == "spirit_id"]
                elif name == "save_no":
                    continue
                else:
                    found = value(name, tag, text, "board", number)
                    if found is not None:
                        board["fields"][name] = (found, where)
            if not ID_RE.match(board["id"]):
                problems.append(("ERROR", "%s: its label makes no board id" % where))
            elif not board["base"]:
                problems.append(("ERROR", "%s: board %s names no base" % (where, board["id"])))
            elif not board["spirits"]:
                problems.append(("ERROR", "%s: board %s has no spirit_list" % (where, board["id"])))
            elif board["art"] and not board["art"].endswith("/layout.arc"):
                problems.append(("ERROR", "%s: art takes a layout path ending in /layout.arc" % where))
            else:
                boards.append(board)
    return spirits, boards, problems


def read_table(name, columns):
    path = os.path.join(DATA, name)
    if not os.path.isfile(path):
        return None
    rows = []
    with open(path, encoding="utf-8") as handle:
        header = handle.readline().rstrip("\n").split("\t")
        for line in handle:
            values = line.rstrip("\n").split("\t")
            row = dict(zip(header, values))
            rows.append(tuple(row.get(column, "") for column in columns))
    return rows


def game_spirits():
    rows = read_table("spirits.tsv", ("id", "pictures", "is_dlc"))
    if rows is None:
        return None
    return {spirit: {"pictures": pictures or "012", "is_dlc": dlc == "1"} for spirit, pictures, dlc in rows}


def game_fields():
    rows = read_table("spirit_fields.tsv", ("table", "field", "type"))
    if rows is None:
        return None
    fields = {}
    for table, field, kind in rows:
        fields.setdefault(table, {})[field] = kind
        if field.startswith("0x"):
            continue
        fields[table][hex(hash40(field))] = kind
    return fields


def value_problem(kind, value):
    sort, raw = value
    if kind == "hash40":
        return None if sort == "text" or (sort == "number" and raw >= 0) else "takes a name"
    if kind == "string":
        return None if sort == "text" else "takes text"
    if kind == "bool":
        return None if sort == "flag" or (sort == "number" and raw in (0, 1)) else "takes true or false"
    if kind in INTEGERS:
        low, high = INTEGERS[kind]
        if sort == "flag":
            return None
        if sort != "number":
            return "takes a whole number"
        return None if low <= raw <= high else "takes %d to %d" % (low, high)
    if kind == "float":
        return None if sort in ("number", "float") else "takes a number"
    return "is a group, not a value"


def shipped_files(mod_dir):
    out = set()
    for root, _, names in os.walk(mod_dir):
        for name in names:
            out.add(os.path.relpath(os.path.join(root, name), mod_dir).replace(os.sep, "/").lower())
    return out


def labels(mod_dir):
    path = os.path.join(mod_dir, "ui", "message", "msg_spirits.xmsbt")
    if not os.path.isfile(path):
        return set()
    with open(path, "rb") as handle:
        raw = handle.read()
    for encoding in ("utf-16", "utf-8-sig"):
        try:
            return set(re.findall(r'label="([^"]+)"', raw.decode(encoding)))
        except UnicodeDecodeError:
            continue
    return set()


def check_spirit(spirit, game, fields, shipped, names, declared):
    findings = []
    label = 'spirit "%s"' % spirit["id"]
    base = spirit["base"]
    if game is not None:
        if spirit["id"] in game:
            findings.append(("ERROR", "%s: the game already has a spirit with this id; the engine skips it" % label))
        if base not in game and base not in declared and not base.lower().startswith("0x"):
            findings.append(("ERROR", "%s: base %s is not one of the game's spirits; the engine skips it"
                             % (label, base)))
    if base in declared:
        findings.append(("INFO", "%s: its base %s is another spirit of this pack, declared above it" % (label, base)))
    if fields is not None:
        for table, fighter, name, value, line in spirit["fields"]:
            key = name if table == "spirit" else ("fighter.%d.%s" % (fighter, name) if table == "fighter"
                                                  else "%s.%s" % (table, name))
            known = fields.get(table, {})
            kind = known.get(name) or known.get(hex(int(name, 16)) if name.startswith("0x") else name)
            if kind is None:
                findings.append(("WARN", "%s: %s (%s) is not a field of the %s table; the engine leaves it out"
                                 % (label, key, at(line), table)))
                continue
            problem = value_problem(kind, value)
            if problem:
                findings.append(("WARN", "%s: %s (%s) is a %s and %s; the engine leaves it out"
                                 % (label, key, at(line), kind, problem)))
    is_dlc = next((value[1] for table, _, name, value, _ in spirit["fields"]
                   if table == "spirit" and name == "is_dlc"), False)
    tree = "ui/replace_patch/spirits" if is_dlc else "ui/replace/spirits"
    sizes = (game or {}).get(base, {}).get("pictures", "012")
    missing = ["spirits_%s" % size for size in sizes
               if "%s/spirits_%s/spirits_%s_%s.bntx" % (tree, size, size, spirit["id"]) not in shipped]
    if missing:
        findings.append(("WARN", "%s: no picture in %s under %s/; those screens show an empty frame"
                         % (label, ", ".join(missing), tree)))
    if "spi_%s" % spirit["id"] not in names:
        findings.append(("WARN", "%s: ui/message/msg_spirits.xmsbt has no spi_%s; the menus show no name"
                         % (label, spirit["id"])))
    return findings


def game_board(name):
    """The game's board a base or background names, None when it names none, "" when it cannot be told."""
    name = name.strip()
    if name.lower().startswith("0x"):
        return ""
    plain = name[len("ui_chara_"):] if name.startswith("ui_chara_") else name.lower()
    return plain if plain in GAME_BOARDS else None


def art_problem(mod_dir, art):
    """None, or what is wrong with a board's art layout in the pack."""
    path = os.path.join(mod_dir, *art.split("/"))
    if not os.path.isfile(path):
        return "%s is not in the pack" % art
    root = art.split("/")[-2]
    with open(path, "rb") as handle:
        data = handle.read()
    missing = [pane for pane in ("banner", "card") if pane.encode() + b"\0" not in data]
    if missing:
        return "%s has no %s pane" % (art, " or ".join(missing))
    if ("blyt/%s.bflyt" % root).encode() not in data:
        return "%s holds no layout named %s, its folder's name" % (art, root)
    return None


def background_packs(mod_dir, number):
    """The other installed packs that ship board background number N."""
    parent = os.path.dirname(os.path.abspath(mod_dir))
    relative = (BACKGROUND % (number, number)).split("/")
    others = []
    try:
        entries = sorted(os.listdir(parent))
    except OSError:
        return others
    for entry in entries:
        folder = os.path.join(parent, entry)
        if os.path.abspath(folder) != os.path.abspath(mod_dir) and os.path.isfile(os.path.join(folder, *relative)):
            others.append(entry)
    return others


def check_board(board, game, spirit_ids, shipped=frozenset(), mod_dir=None):
    findings = []
    label = 'board "%s"' % board["id"]
    for field, (value, line) in board.get("fields", {}).items():
        kind = BOARD_FIELDS.get(field)
        if kind is None:
            findings.append(("WARN", "%s: %s (%s) is not a field of the board row (%s); the engine leaves it "
                                     "out" % (label, field, at(line), ", ".join(BOARD_FIELDS))))
            continue
        problem = value_problem(kind, value)
        if problem:
            findings.append(("WARN", "%s: %s (%s) is a %s and %s; the engine leaves it out"
                             % (label, field, at(line), kind, problem)))
    layout = board.get("fields", {}).get("layout_no")
    number = layout[0][1] if layout and layout[0][0] == "number" else None
    if number is not None and number >= GAME_BACKGROUNDS and mod_dir is not None:
        background = (BACKGROUND % (number, number)).lower()
        if background not in shipped:
            findings.append(("WARN", "%s: layout_no %d asks for %s, which the pack does not ship; the board shows "
                                     "no background" % (label, number, background)))
        others = background_packs(mod_dir, number)
        if others:
            findings.append(("WARN", "%s: %s also ship background %d; only one of them shows, so pick another "
                                     "number" % (label, ", ".join(others), number)))
    if board.get("art") and mod_dir is not None:
        problem = art_problem(mod_dir, board["art"])
        if problem:
            findings.append(("WARN", "%s: %s; its button shows its name" % (label, problem)))
    if board["id"] in GAME_BOARDS:
        findings.append(("ERROR", "%s: the game already has a board with this id; the engine skips it" % label))
    base = game_board(board["base"])
    if base is None:
        findings.append(("ERROR", "%s: base %s is not one of the game's boards (%s); the engine skips it"
                         % (label, board["base"], ", ".join(GAME_BOARDS))))
    if board["background"] and game_board(board["background"]) is None:
        findings.append(("WARN", "%s: background %s is not one of the game's boards; it keeps its base's"
                         % (label, board["background"])))
    if game is not None:
        unknown = [spirit for spirit in board["spirits"] if spirit not in game and spirit not in spirit_ids
                   and not spirit.lower().startswith("0x")]
        if unknown and len(unknown) == len(board["spirits"]):
            findings.append(("WARN", "%s: none of its spirits is the game's or this pack's; the engine skips it "
                                     "unless another pack declares them" % label))
        elif unknown:
            findings.append(("WARN", "%s: %s are not the game's or this pack's spirits; the engine leaves them out "
                                     "unless another pack declares them" % (label, ", ".join(unknown))))
    if not board["name"]:
        findings.append(("INFO", "%s: no name, so its button shows its id" % label))
    return findings


_CACHE = {}


def _cached(name, build):
    if name not in _CACHE:
        _CACHE[name] = build()
    return _CACHE[name]


def table_fields():
    """{table: [(field, type)]}: every field of the spirit tables a spirit.toml may set, in the tables' order."""
    def build():
        fields = {}
        for table, field, kind in read_table("spirit_fields.tsv", ("table", "field", "type")) or ():
            if field not in FIXED.get(table, ()):
                fields.setdefault(table, []).append((field, kind))
        return fields
    return _cached("table_fields", build)


ROW_TABLES = (("spirit", "spirit_db.tsv", "ui_spirit_id"), ("battle", "spirit_battles.tsv", "battle_id"),
              ("fighter", "spirit_fighters.tsv", "battle_id"), ("layout", "spirit_layouts.tsv", "ui_spirit_layout_id"))
RESETS = {"is_dlc": "false", "is_bcat": "false", "replace_battle_id": "", "check_id": ""}


def game_rows():
    """{table: {key value: [rows]}}: every row of the game's four spirit tables, values as spirit.toml writes them."""
    def build():
        found = {}
        for table, name, column in ROW_TABLES:
            path = os.path.join(DATA, name)
            if not os.path.isfile(path):
                return None
            index = {}
            with open(path, encoding="utf-8") as handle:
                header = handle.readline().rstrip("\n").split("\t")
                for line in handle:
                    cells = dict(zip(header, line.rstrip("\n").split("\t")))
                    index.setdefault(cells.get(column, ""), []).append(cells)
            found[table] = index
        return found
    return _cached("rows", build)


def base_values(base):
    """Every key a spirit copied from this game spirit starts with, as the engine builds it, or None."""
    rows = game_rows()
    wanted = '"%s"' % str(base).strip()
    if not rows or wanted not in rows["spirit"]:
        return None
    values = {field: RESETS.get(field, value) for field, value in rows["spirit"][wanted][0].items()
              if field not in FIXED["spirit"]}
    for table in ("battle", "layout"):
        for field, value in (rows[table].get(wanted) or [{}])[0].items():
            if field not in FIXED[table]:
                values["%s.%s" % (table, field)] = value
    fighters = rows["fighter"].get(wanted) or []
    for index, fighter in enumerate(fighters):
        for field, value in fighter.items():
            if field not in FIXED["fighter"]:
                values["fighter.%d.%s" % (index, field)] = "" if field == "spirit_name" else value
    if fighters:
        values["fighters"] = str(len(fighters))
    return values


def game_boards():
    """{board: {field: value}}: the game's DLC spirit boards, values as spirit.toml writes them."""
    def build():
        path = os.path.join(DATA, "spirit_boards.tsv")
        if not os.path.isfile(path):
            return None
        rows = {}
        with open(path, encoding="utf-8") as handle:
            header = handle.readline().rstrip("\n").split("\t")
            for line in handle:
                cells = dict(zip(header, line.rstrip("\n").split("\t")))
                rows[cells.pop("board")] = cells
        return rows
    return _cached("boards", build)


def board_values(base):
    """Every key a board copied from this game board starts with, as the engine builds it, or None."""
    boards = game_boards()
    name = game_board(base) if base else None
    if not boards or not name or name not in boards:
        return None
    values = dict(boards[name])
    values["shop_item_tag"] = ""
    return values


def same_value(a, b):
    """Whether two spirit.toml values say the same: 1 and 1.0, "x" and "x"."""
    a, b = (a or "").strip(), (b or "").strip()
    if a == b:
        return True
    first, second = parse_value(a), parse_value(b)
    if first and second and first[0] in ("number", "float") and second[0] in ("number", "float"):
        return float(first[1]) == float(second[1])
    return bool(first and second and first == second)


def base_value(values, key):
    """The base's value for a key; a fighter past the base's count repeats its last one."""
    if key in values or not key.startswith("fighter."):
        return values.get(key)
    parts = key.split(".", 2)
    count = int(values.get("fighters") or 0)
    if len(parts) == 3 and parts[1].isdigit() and count:
        return values.get("fighter.%d.%s" % (min(int(parts[1]), count - 1), parts[2]))
    return None


def lint(mod_dir, arc_index=DEFAULT_ARC_INDEX):
    path = os.path.join(mod_dir, MANIFEST)
    xml = [relative for relative in PRCXML_FILES.values() if os.path.isfile(os.path.join(mod_dir, *relative.split("/")))]
    if not os.path.isfile(path) and not xml:
        return [("ERROR", "no %s and no spirit/ prcxml files in %s" % (MANIFEST, mod_dir))]
    spirits, boards, findings = [], [], []
    if os.path.isfile(path):
        with open(path, encoding="utf8", errors="replace") as handle:
            spirits, boards, problems = parse_manifest(handle.read())
        if problems:
            findings += list(problems) + [("ERROR", "the engine skips this whole %s" % MANIFEST)]
            spirits, boards = [], []
    if xml:
        more, more_boards, problems = parse_prcxml(mod_dir)
        if problems:
            findings += problems + [("ERROR", "the engine skips the pack's spirit/ prcxml files")]
        else:
            for spirit in more:
                if any(other["id"] == spirit["id"] for other in spirits):
                    findings.append(("ERROR", "%s: spirit %s is in %s too; the engine keeps one"
                                     % (spirit["line"], spirit["id"], MANIFEST)))
                else:
                    spirits.append(spirit)
            for board in more_boards:
                if any(other["id"] == board["id"] for other in boards):
                    findings.append(("ERROR", "%s: board %s is in %s too; the engine keeps one"
                                     % (board["line"], board["id"], MANIFEST)))
                else:
                    boards.append(board)
    if any(level == "ERROR" for level, _ in findings):
        return findings
    game, fields = game_spirits(), game_fields()
    if game is None or fields is None:
        findings.append(("WARN", "the spirit tables are not beside this script, so ids, bases and fields are "
                                 "not checked against the game's"))
    shipped = shipped_files(mod_dir)
    names = labels(mod_dir)
    declared = set()
    for spirit in spirits:
        findings += check_spirit(spirit, game, fields, shipped, names, declared)
        declared.add(spirit["id"])
    if len(spirits) > ROOM:
        findings.append(("ERROR", "%d spirits, but the save holds only %d added ones for every pack together"
                         % (len(spirits), ROOM)))
    for board in boards:
        findings += check_board(board, game, declared, shipped, mod_dir)
    if spirits:
        findings.append(("INFO", "%d spirit(s); each keeps its save number (from %d) in "
                                 "sd:/ultimate/dionysus/spirits.txt" % (len(spirits), SAVE_FIRST)))
    if boards:
        findings.append(("INFO", "%d board(s); each keeps its board number (%d to %d) in "
                                 "sd:/ultimate/dionysus/spirit_boards.txt. They show on pages of the DLC Spirits "
                                 "popup with the Dionysus Modes pack" % (len(boards), BOARD_FIRST, BOARD_LAST)))
    findings.append(("INFO", "spirits need an engine with CAP_SPIRITS; older engines ignore them"))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check a spirit pack: spirit.toml and the files it needs.")
    parser.add_argument("mod_dir", help="your mod folder")
    parser.add_argument("--arc-index", default=DEFAULT_ARC_INDEX, metavar="DIR", help="unused; kept for the GUI")
    arguments = parser.parse_args(argv)
    findings = lint(arguments.mod_dir, arguments.arc_index)
    errors = 0
    for level, message in findings:
        print("%-5s %s" % (level, message))
        errors += level == "ERROR"
    print()
    print("%d error(s), %d note(s)" % (errors, len(findings) - errors))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
