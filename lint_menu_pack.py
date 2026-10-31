#!/usr/bin/env python3
"""Check a menu pack: menu.toml by the engine's own rules, then the files it names."""
import argparse
import os
import re
import struct
import sys
import zlib

FIRST_CUSTOM_PAGE = 0x08
LAST_CUSTOM_PAGE = 0x7f
MODE_PAGE = 0x7f
SEQUENCE_PAGE = 0x7e
MAX_MODES = 32
MAX_MODE_ID = 32
MAX_MODE_NAME = 64
MAX_MODE_DESCRIPTION = 256
MAX_MODE_ORDER = 0x7fffffff
MAX_SEQUENCES = 64
MAX_PRELOADS = 64
MAX_LAYOUTS = 16
MAX_PATCHES = 64
MAX_MODULE_NAME = 200
MAX_MOVIE_PATH = 62
U32_MAX = 0xffffffff
SMASH = 0x02010000
MAIN_MENU = "main_menu"
MAIN_MENU_LAYOUT = "ui/layout/menu/main_menu/main_menu/layout.arc"
BNTX_ALIGNMENT = 4096
HUB_PATCH = ("menu/main/main_menu_layer_top", "menu/clone_engine/ce_top")
SCRIPT_FUNCTIONS = ("decide", "enter", "update", "leave")
SCENES = (
    "MenuSequenceScene", "OptionSequenceScene", "HelpSequenceScene", "IngameCallSequenceScene",
    "UnlockSequenceScene", "LocalSequenceScene", "MeleeNormalSequenceScene",
    "MeleeAllBattleSequenceScene", "MeleeTeamCompeSequenceScene", "MeleeTournamentSequenceScene",
    "SpiritsBoardSequenceScene", "SpiritsCampaignSequenceScene",
    "SpiritsCampaignFinalStageSequenceScene", "SpiritsBoardSpecialSequenceScene",
    "SpiritsOrganizationSequenceScene", "StandardSequenceScene", "TrainingSequenceScene",
    "KumiteSequenceScene", "HomeRunContestSequenceScene", "CharaMakeSequenceScene",
    "AmiiboSequenceScene", "ChallengerRoomSequenceScene", "OnlineMeleeAnySequenceScene",
    "OnlineMeleeParallelSequenceScene", "OnlineMeleeRoomSequenceScene", "OnlineWatchSequenceScene",
    "SoundTestSequenceScene", "CollectionTipsSequenceScene", "CollectionShopSequenceScene",
    "CollectionFighterSequenceScene", "CollectionCountSequenceScene",
    "CollectionAnniversarySequenceScene", "CollectionPlayingSequenceScene",
    "CollectionCardSequenceScene", "CollectionReplaySequenceScene", "CollectionVideoSequenceScene",
    "CollectionGetterSequenceScene", "CollectionPresentSequenceScene", "CollectionMovieSequenceScene",
    "MeleeVrSequenceScene", "StageMakeSequenceScene", "VideoEditSequenceScene",
    "OnlineMeleeTournamentSequenceScene", "OnlineShareSequenceScene", "OnlineWatchFullSequenceScene",
    "OnlineMeleeConventionSequenceScene",
)
SEQUENCE_NAMES = (
    ("title", 0x01000000), ("title_demo", 0x01010000), ("melee", 0x02000000),
    ("melee_normal", 0x02010000), ("melee_team_compe", 0x02020000), ("melee_special", 0x02030000),
    ("melee_special_various", 0x02030100), ("melee_special_suddendeath", 0x02030200),
    ("melee_special_all_battle", 0x02030300), ("melee_tournament", 0x02040000), ("spirits", 0x03000000),
    ("spirits_challenge", 0x03010000), ("spirits_canpaign", 0x03020000), ("spirits_formation", 0x03030000),
    ("spirits_challenge_special", 0x03040000), ("other", 0x04000000), ("other_standard", 0x04010000),
    ("other_kumite", 0x04020000), ("other_kumite_100", 0x04020100), ("other_kumite_allstar", 0x04020200),
    ("other_kumite_cruel", 0x04020300), ("other_homerun", 0x04030000), ("other_homerun_single", 0x04030100),
    ("other_homerun_coop", 0x04030200), ("other_homerun_everyone", 0x04030300),
    ("other_training", 0x04040000), ("other_chara_make", 0x04050000), ("other_stage_make", 0x04060000),
    ("other_amiibo", 0x04070000), ("other_challenger", 0x04080000), ("other_vr", 0x04090000),
    ("collection", 0x05000000), ("collection_replay", 0x05010000), ("collection_replay_data", 0x05010100),
    ("collection_replay_video", 0x05010200), ("collection_replay_edit", 0x05010300),
    ("collection_cleargetter", 0x05020000), ("collection_sound", 0x05030000),
    ("collection_smaknowledge", 0x05040000), ("collection_movie", 0x05050000),
    ("collection_record", 0x05060000), ("collection_record_count", 0x05060100),
    ("collection_record_memorial", 0x05060200), ("collection_record_fighter", 0x05060300),
    ("collection_record_card", 0x05060400), ("collection_record_playing", 0x05060500),
    ("collection_shop", 0x05070000), ("collection_present", 0x05080000), ("option", 0x06000000),
    ("option_melee", 0x06010000), ("option_button", 0x06020000), ("option_picture", 0x06030000),
    ("option_sound", 0x06040000), ("option_online", 0x06050000), ("option_language", 0x06060000),
    ("online", 0x07000000), ("online_melee", 0x07010000), ("online_melee_anyone", 0x07010100),
    ("online_melee_room", 0x07010200), ("online_melee_tournament", 0x07010300),
    ("online_melee_anyone_vip", 0x07010400), ("online_melee_wait_parallel", 0x07010600),
    ("online_melee_convention", 0x07010800), ("online_watch", 0x07020000), ("online_share", 0x07070000),
)
COMMON_MODES = ("melee_normal", "other_training", "other_standard", "melee_team_compe")
KEYS = {
    "sequence": {"id": "text", "code": "number", "runs_as": "mode", "scene": "text", "skip": "texts",
                 "after_battle": "text"},
    "preload": {"after": "text", "files": "texts"},
    "layout": {"scene": "text", "file": "text", "over_side_panel": "flag", "under_movies": "flag"},
    "patch": {"module": "text", "script": "text", "root": "text"},
    "mode": {"id": "text", "name": "text", "description": "text", "script": "text", "button": "text",
             "runs_as": "mode", "scene": "text", "order": "number", "skip": "texts",
             "after_battle": "text"},
}
TABLES = tuple(KEYS)
SKIPS = ("rules", "stage_select")
AFTER_BATTLE = ("menu", "vanilla")
ROOTS = {"script": "ui/script/", "script_patch": "ui/script_patch/"}


def _default_arc_index():
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.join(here, "arc_index"),
                      os.path.join(os.path.dirname(here), "arc_index"),
                      os.path.join(os.path.dirname(os.path.dirname(here)), "arc_index")):
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(here, "arc_index")


DEFAULT_ARC_INDEX = os.environ.get("SSBU_ARC_INDEX", _default_arc_index())


class MenuError(Exception):
    def __init__(self, line, message):
        super().__init__(message)
        self.line = line
        self.message = message

    def __str__(self):
        return "line %d: %s" % (self.line, self.message) if self.line else self.message


def hash40(text):
    lower = text.lower().encode("utf8")
    return (len(lower) << 32) | zlib.crc32(lower)


def strip_comment(line):
    quoted = False
    for index, char in enumerate(line):
        if char == '"':
            quoted = not quoted
        elif char == "#" and not quoted:
            return line[:index]
    return line


def parse_value(raw):
    """A value as the engine reads it: number, text, list of texts or flag; None when it reads none."""
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        items = []
        for item in raw[1:-1].split(","):
            item = item.strip()
            if not item:
                continue
            if len(item) < 2 or not (item.startswith('"') and item.endswith('"')):
                return None
            items.append(item[1:-1])
        return ("texts", items)
    if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
        return ("text", raw[1:-1])
    if raw in ("true", "false"):
        return ("flag", raw == "true")
    digits = raw.replace("_", "")
    try:
        if digits[:2] in ("0x", "0X"):
            return ("number", int(digits[2:], 16))
        if digits.isdigit():
            return ("number", int(digits))
    except ValueError:
        return None
    return None


def is_custom(code):
    return FIRST_CUSTOM_PAGE <= code >> 24 <= LAST_CUSTOM_PAGE


def is_vanilla(code):
    return 1 <= code >> 24 < FIRST_CUSTOM_PAGE


def is_mode_code(code):
    return code >> 24 == MODE_PAGE


def is_engine_code(code):
    return code >> 24 in (MODE_PAGE, SEQUENCE_PAGE)


def vanilla_code(name):
    """The code of one of the game's modes by its SEQUENCE_ name, any case, with or without the prefix."""
    name = name.strip().lower()
    if name.startswith("sequence_"):
        name = name[len("sequence_"):]
    return dict(SEQUENCE_NAMES).get(name)


def mode_code(index):
    return MODE_PAGE << 24 | ((index + 1) & 0xff) << 16


def valid_mode_id(text):
    return 0 < len(text) <= MAX_MODE_ID and re.fullmatch(r"[a-z0-9_]+", text) is not None


def layout_root(path):
    path = path.strip().lower()
    if not path.endswith("/layout.arc"):
        return None
    name = path[:-len("/layout.arc")].rsplit("/", 1)[-1]
    return name or None


def module_name(name):
    name = name.strip().lower()
    valid = (0 < len(name) <= MAX_MODULE_NAME and not name.startswith("/") and not name.endswith("/")
             and not name.endswith(".lc") and not name.startswith("ui/")
             and re.fullmatch(r"[a-z0-9_/.\-]+", name) is not None)
    return name if valid else None


def check_flow(block, values, runs_as, scene):
    flow = []
    for screen in values.get("skip", []):
        if screen.strip().lower() not in SKIPS:
            raise MenuError(block["line"], 'skip "%s" is not one of %s' % (screen, ", ".join(SKIPS)))
        flow.append(screen.strip().lower())
    after = values.get("after_battle")
    if after is not None:
        if after.strip().lower() not in AFTER_BATTLE:
            raise MenuError(block["line"], 'after_battle "%s" is not menu or vanilla' % after)
        if after.strip().lower() == "menu":
            flow.append("menu")
    if flow and (runs_as != SMASH or scene is not None):
        raise MenuError(block["line"], 'skip and after_battle need runs_as = "melee_normal" (Smash) and no '
                                       "scene (NoFlow)")
    return flow


def finish(block):
    """The engine's check of one finished table; raises MenuError, returns the table's meaning."""
    table, line, values = block["table"], block["line"], block["values"]

    def need(key):
        if key not in values:
            raise MenuError(line, "[[%s]] needs %s" % (table, key))
        return values[key]

    def scene_of(name):
        if name.strip() not in SCENES:
            raise MenuError(line, 'scene "%s" is not a scene the game has' % name)
        return name.strip()

    if table == "sequence":
        identifier = values.get("id", "").strip()
        if identifier and not valid_mode_id(identifier):
            raise MenuError(line, 'sequence id "%s" must be lower case letters, digits and _, up to %d'
                            % (identifier, MAX_MODE_ID))
        code = values.get("code")
        if code is None and not identifier:
            raise MenuError(line, "[[sequence]] needs id or code")
        runs_as = need("runs_as")
        if code is not None and not is_custom(code):
            raise MenuError(line, "code %#010x is not a custom code; its first byte is 0x08 to 0x7d" % code)
        if code is not None and is_engine_code(code):
            raise MenuError(line, "code %#010x is on page 0x7e or 0x7f, which hold the codes the engine gives"
                            % code)
        if not is_vanilla(runs_as):
            raise MenuError(line, "runs_as %#010x is not a vanilla mode (first byte 0x01 to 0x07)" % runs_as)
        scene = scene_of(values["scene"]) if "scene" in values else None
        flow = check_flow(block, values, runs_as, scene)
        return {"id": identifier or None, "code": code, "runs_as": runs_as, "scene": scene, "flow": flow}
    if table == "preload":
        after = need("after")
        if not values.get("files"):
            raise MenuError(line, "[[preload]] needs files")
        return {"after": after.strip().lower(), "files": [path.strip().lower() for path in values["files"]]}
    if table == "layout":
        scene, path = need("scene").strip().lower(), need("file")
        if scene != MAIN_MENU:
            raise MenuError(line, 'layout scene "%s" is not main_menu' % scene)
        if not path.strip().lower().endswith("/layout.arc"):
            raise MenuError(line, 'layout file "%s" does not end in /layout.arc' % path)
        return {"file": path.strip().lower(), "over_side_panel": values.get("over_side_panel", False),
                "under_movies": values.get("under_movies", False)}
    if table == "patch":
        module_text, script_text = need("module"), need("script")
        module, script = module_name(module_text), module_name(script_text)
        if module is None:
            raise MenuError(line, 'module "%s" is not a module name (a path under ui/script/ without .lc)'
                            % module_text)
        if script is None:
            raise MenuError(line, 'script "%s" is not a module name (a path under ui/script/ without .lc)'
                            % script_text)
        root = values.get("root", "script").strip().lower()
        if root not in ROOTS:
            raise MenuError(line, 'root "%s" is not script or script_patch' % values.get("root"))
        return {"module": module, "script": script, "root": root}
    identifier = need("id").strip()
    if not valid_mode_id(identifier):
        raise MenuError(line, 'mode id "%s" must be lower case letters, digits and _, up to %d'
                        % (identifier, MAX_MODE_ID))
    name = need("name").strip()
    if not name or len(name.encode("utf8")) > MAX_MODE_NAME:
        raise MenuError(line, "mode name must be 1 to %d bytes" % MAX_MODE_NAME)
    description = values.get("description", "").strip()
    if len(description.encode("utf8")) > MAX_MODE_DESCRIPTION:
        raise MenuError(line, "mode description is %d bytes, more than %d"
                        % (len(description.encode("utf8")), MAX_MODE_DESCRIPTION))
    script = None
    if "script" in values:
        script = module_name(values["script"])
        if script is None:
            raise MenuError(line, 'script "%s" is not a module name (a path under ui/script/ without .lc)'
                            % values["script"])
    button = None
    if "button" in values:
        button = values["button"].strip().lower()
        if layout_root(button) is None:
            raise MenuError(line, 'button "%s" does not end in <folder>/layout.arc' % values["button"])
    runs_as = values.get("runs_as")
    if runs_as is not None and not is_vanilla(runs_as):
        raise MenuError(line, "runs_as %#010x is not a vanilla mode (first byte 0x01 to 0x07)" % runs_as)
    scene = None
    if "scene" in values:
        if runs_as is None:
            raise MenuError(line, "a mode with a scene needs runs_as")
        scene = scene_of(values["scene"])
    if script is None and runs_as is None:
        raise MenuError(line, "a mode needs script or runs_as")
    flow = check_flow(block, values, runs_as, scene)
    return {"id": identifier, "name": name, "description": description, "script": script,
            "button": button, "runs_as": runs_as, "scene": scene, "order": values.get("order", 0),
            "flow": flow}


def read_blocks(text):
    """Every table in the file with its raw text, without judging it; used by the window too."""
    blocks = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = strip_comment(raw).strip()
        if not line:
            continue
        if line.startswith("[[") and line.endswith("]]"):
            blocks.append({"table": line[2:-2].strip(), "line": number, "raw": {}, "values": {},
                           "lines": {}})
            continue
        if "=" not in line or not blocks:
            blocks.append({"table": None, "line": number, "raw": {}, "values": {}, "lines": {}})
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        blocks[-1]["raw"][key] = value.strip()
        blocks[-1]["lines"][key] = number
    return blocks


def parse(text):
    """(tables, problems): each table the engine keeps, and what it refuses or ignores.
    An ERROR means the engine skips the whole menu.toml, as it stops at the first."""
    tables, problems = [], []
    for block in read_blocks(text):
        if block["table"] is None:
            problems.append(("ERROR", "line %d: a key outside any table, or a line with no =" % block["line"]))
            continue
        if block["table"] not in KEYS:
            problems.append(("ERROR", "line %d: [[%s]] is not a menu.toml table (%s)"
                             % (block["line"], block["table"], ", ".join(TABLES))))
            continue
        kinds = KEYS[block["table"]]
        refused = False
        for key, raw in block["raw"].items():
            value = parse_value(raw)
            if key not in kinds:
                problems.append(("WARN", "line %d: [[%s]] has no key %s; the engine ignores it"
                                 % (block["lines"][key], block["table"], key)))
                continue
            wanted = kinds[key]
            if wanted == "mode" and value is not None and value[0] == "text":
                code = vanilla_code(value[1])
                if code is None:
                    problems.append(("ERROR", 'line %d: runs_as "%s" is not one of the game\'s modes (%s, ...; '
                                              "docs/wiki/MENUS.md lists them)"
                                     % (block["lines"][key], value[1], ", ".join(COMMON_MODES))))
                    refused = True
                    continue
                block["values"][key] = code
                continue
            if wanted == "mode":
                wanted = "number"
            if value is None or value[0] != wanted or (
                    wanted == "number" and value[1] > (MAX_MODE_ORDER if key == "order" else U32_MAX)):
                problems.append(("ERROR", "line %d: %s = %s is not a valid %s"
                                 % (block["lines"][key], key, raw, describe_kind(wanted, key))))
                refused = True
                continue
            block["values"][key] = value[1]
        if refused:
            continue
        try:
            meaning = finish(block)
        except MenuError as problem:
            problems.append(("ERROR", str(problem)))
            continue
        tables.append(dict(meaning, table=block["table"], line=block["line"]))
    return tables, problems


def describe_kind(kind, key):
    if kind == "mode":
        return 'mode name such as "other_training", or its number'
    if kind == "number":
        return "number up to %#x" % (MAX_MODE_ORDER if key == "order" else U32_MAX)
    return {"text": "quoted text", "texts": 'list of quoted texts, ["a", "b"]',
            "flag": "true or false"}[kind]


def block_problem(table, row):
    """What the engine would refuse in one table written from these TOML texts, or ""."""
    text = "\n".join(["[[%s]]" % table] + ["%s = %s" % (key, value) for key, value in row.items()])
    _, problems = parse(text)
    for level, message in problems:
        if level == "ERROR":
            return re.sub(r"^line \d+: ", "", message)
    return ""


def shipped_files(mod_dir):
    """{lower case path: path on disk} of every file in the pack, relative to it."""
    out = {}
    for root, _, names in os.walk(mod_dir):
        for name in names:
            relative = os.path.relpath(os.path.join(root, name), mod_dir).replace(os.sep, "/")
            out[relative.lower()] = relative
    return out


def load_vanilla(arc_index):
    path = os.path.join(arc_index, "arc_files.tsv")
    if not os.path.isfile(path):
        return None
    files = set()
    with open(path, encoding="utf8", errors="replace") as handle:
        for line in handle:
            files.add(line.split("\t", 1)[0].strip())
    files.discard("")
    return files


def sarc_files(blob):
    """{name: (start, end)} of a SARC archive, as absolute offsets; None when it is not one."""
    if len(blob) < 0x14 or blob[:4] != b"SARC":
        return None
    order = "<" if blob[6:8] == b"\xff\xfe" else ">"
    data_start = struct.unpack_from(order + "I", blob, 0x0c)[0]
    header = struct.unpack_from(order + "H", blob, 4)[0]
    if blob[header:header + 4] != b"SFAT":
        return None
    count = struct.unpack_from(order + "H", blob, header + 6)[0]
    nodes = header + 0x0c
    names = nodes + count * 0x10
    if blob[names:names + 4] != b"SFNT":
        return None
    names_start = names + 8
    out = {}
    for index in range(count):
        _, attributes, start, end = struct.unpack_from(order + "IIII", blob, nodes + index * 0x10)
        name = "#%d" % index
        if attributes & 0x01000000:
            offset = names_start + (attributes & 0xffff) * 4
            stop = blob.find(b"\0", offset)
            name = blob[offset:stop].decode("utf8", "replace")
        out[name] = (data_start + start, data_start + end)
    return out


def check_layout_file(mod_dir, shipped, path, label, needs_root=False):
    """Findings for one layout.arc the pack ships: the __Combined.bntx alignment, the main .bflyt name."""
    findings = []
    try:
        with open(os.path.join(mod_dir, *shipped[path].split("/")), "rb") as handle:
            blob = handle.read()
    except OSError:
        return findings
    files = sarc_files(blob)
    if files is None:
        return [("ERROR", "%s: %s is not a SARC archive; the main menu cannot open it" % (label, path))]
    combined = files.get("timg/__Combined.bntx")
    if combined and combined[0] % BNTX_ALIGNMENT:
        findings.append(("ERROR", "%s: timg/__Combined.bntx starts at %#x inside %s, not on a %d-byte "
                                  "boundary; the main menu stops at load" % (
                                      label, combined[0], path, BNTX_ALIGNMENT)))
    root = layout_root(path)
    if needs_root and root and "blyt/%s.bflyt" % root not in {name.lower() for name in files}:
        findings.append(("ERROR", "%s: %s has no blyt/%s.bflyt; the engine names the button after its "
                                  "folder, so the page finds no layout" % (label, path, root)))
    return findings


LUA_HEADER = b"\x1bLua\x53\x00\x19\x93\r\n\x1a\n"
LUA_SIZES = bytes([4, 8, 4, 8, 4])


def bytecode_problem(blob):
    """Why the game cannot load this compiled script, or ""; its Lua 5.3 keeps numbers in 4 bytes."""
    if not blob.startswith(LUA_HEADER[:5]):
        return "not Lua 5.3 bytecode"
    if blob[:len(LUA_HEADER)] != LUA_HEADER:
        return "a Lua 5.3 header this luac does not write"
    sizes = blob[len(LUA_HEADER):len(LUA_HEADER) + len(LUA_SIZES)]
    if sizes != LUA_SIZES:
        if len(sizes) == len(LUA_SIZES) and sizes[4] == 8:
            return "compiled with 8-byte floats; the game reads 4-byte ones (build luac with LUA_FLOAT_TYPE = LUA_FLOAT_FLOAT)"
        return "sizes %s, not the game's %s" % (sizes.hex(" "), LUA_SIZES.hex(" "))
    return ""


def lua_functions(mod_dir, shipped, relative):
    """The SCRIPT_FUNCTIONS names a compiled script holds as string constants; None when unreadable."""
    path = os.path.join(mod_dir, *shipped[relative].split("/"))
    try:
        with open(path, "rb") as handle:
            blob = handle.read()
    except OSError:
        return None
    if not blob.startswith(b"\x1bLua"):
        return None
    return {name for name in SCRIPT_FUNCTIONS
            if bytes([0x04, len(name) + 1]) + name.encode() in blob}


def sibling_menus(mod_dir):
    """Every pack folder beside this one with a menu.toml, this one included, in the engine's order."""
    mod_dir = os.path.abspath(mod_dir)
    parent = os.path.dirname(mod_dir)
    try:
        names = sorted(os.listdir(parent))
    except OSError:
        names = []
    out = []
    for name in names:
        path = os.path.join(parent, name)
        if os.path.isfile(os.path.join(path, "menu.toml")) or os.path.normcase(path) == os.path.normcase(mod_dir):
            out.append((name, path))
    if not any(os.path.normcase(path) == os.path.normcase(mod_dir) for _, path in out):
        out.append((os.path.basename(mod_dir), mod_dir))
    return out


def read_tables(path):
    try:
        with open(path, encoding="utf8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return None
    tables, problems = parse(text)
    if any(level == "ERROR" for level, _ in problems):
        return None
    return tables


def check_registry(mod_dir):
    """What the engine refuses once every installed pack's menu.toml is in: taken codes and ids, full lists."""
    findings = []
    own = os.path.normcase(os.path.abspath(mod_dir))
    sequences, modes, layouts, patches, preloads = {}, [], set(), [], 0
    sequence_ids = {}
    for name, path in sibling_menus(mod_dir):
        tables = read_tables(os.path.join(path, "menu.toml"))
        if tables is None:
            continue
        mine = os.path.normcase(os.path.abspath(path)) == own
        for table in tables:
            kind = table["table"]
            if kind == "sequence":
                key = (table["runs_as"], table["scene"])
                owner = sequence_ids.get(table["id"]) if table["id"] else None
                if owner:
                    if owner[0] != key or table["code"] not in (None, owner[2]):
                        if mine:
                            findings.append(("ERROR", 'sequence id "%s" is declared first by %s; the engine '
                                                      "refuses this one" % (table["id"], owner[1])))
                    continue
                code = table["code"]
                if code is None:
                    given = sum(1 for known in sequences if known >> 24 == SEQUENCE_PAGE)
                    code = SEQUENCE_PAGE << 24 | (given + 1) << 16
                label = 'sequence "%s"' % table["id"] if table["id"] else "code %#010x" % code
                known = sequences.get(code)
                if known and known[0] != key:
                    if mine:
                        findings.append(("ERROR", "code %#010x is taken by %s (runs as %#010x); the engine "
                                                  "refuses this one" % (code, known[1], known[0][0])))
                    continue
                if known is None and len(sequences) >= MAX_SEQUENCES:
                    if mine:
                        findings.append(("ERROR", "%s: %d codes are installed already, the most the "
                                                  "engine keeps" % (label, MAX_SEQUENCES)))
                    continue
                sequences.setdefault(code, (key, name))
                if table["id"]:
                    sequence_ids[table["id"]] = (key, name, code)
            elif kind == "mode":
                taken = next((known for known in modes if known["id"] == table["id"]), None)
                if taken:
                    if mine and taken["pack"] != name:
                        findings.append(("ERROR", 'mode id "%s" is declared first by %s; the engine refuses '
                                                  "this one" % (table["id"], taken["pack"])))
                    elif mine:
                        findings.append(("ERROR", 'mode id "%s" is declared twice; the engine keeps the first'
                                         % table["id"]))
                    continue
                if len(modes) >= MAX_MODES:
                    if mine:
                        findings.append(("ERROR", 'mode "%s": %d modes are installed already, the most the '
                                                  "page shows" % (table["id"], MAX_MODES)))
                    continue
                modes.append(dict(table, pack=name, mine=mine))
            elif kind == "layout":
                if table["file"] == MAIN_MENU_LAYOUT or table["file"] in layouts:
                    continue
                if len(layouts) >= MAX_LAYOUTS and mine:
                    findings.append(("ERROR", "layout %s: %d pack layouts are installed already, the most "
                                              "the main menu builds" % (table["file"], MAX_LAYOUTS)))
                    continue
                layouts.add(table["file"])
            elif kind == "patch":
                if table["root"] == "script" and table["module"] == table["script"]:
                    if mine:
                        findings.append(("ERROR", "patch of %s runs itself; the engine refuses it"
                                         % table["module"]))
                    continue
                key = (table["module"], table["script"], table["root"])
                if key in patches:
                    continue
                if len(patches) >= MAX_PATCHES and mine:
                    findings.append(("ERROR", "patch of %s: %d patches are installed already"
                                     % (table["module"], MAX_PATCHES)))
                    continue
                patches.append(key)
            elif kind == "preload":
                if preloads >= MAX_PRELOADS and mine:
                    findings.append(("ERROR", "preload after %s: %d preloads are installed already"
                                     % (table["after"], MAX_PRELOADS)))
                    continue
                preloads += 1
    modes.sort(key=lambda mode: mode["order"])
    for index, mode in enumerate(modes):
        if mode["runs_as"] is None:
            continue
        code = mode_code(index)
        known = sequences.get(code)
        if known is None and len(sequences) >= MAX_SEQUENCES:
            if mode["mine"]:
                findings.append(("ERROR", 'mode "%s" gets no code: %d codes are installed already'
                                 % (mode["id"], MAX_SEQUENCES)))
            continue
        sequences.setdefault(code, ((mode["runs_as"], mode["scene"]), mode["pack"]))
    mine = [mode for mode in modes if mode["mine"]]
    if mine:
        findings.append(("INFO", "modes page rows: %s" % ", ".join(
            "%d %s" % (index + 1, mode["id"]) for index, mode in enumerate(modes) if mode["mine"])))
    if mine and not any(HUB_PATCH == (patch[0], patch[1]) for patch in patches):
        findings.append(("WARN", "no Clone Engine Modes pack is installed beside this one, so the modes "
                                 "have no page to show on; put the release's Clone Engine Modes folder "
                                 "under ultimate/mods"))
    return findings


def check_popups(mod_dir, shipped):
    findings = []
    relative = "ui/param/database/ui_popup_db.prcxml"
    if relative not in shipped:
        return findings
    try:
        with open(os.path.join(mod_dir, *shipped[relative].split("/")), encoding="utf8",
                  errors="replace") as handle:
            text = handle.read()
    except OSError:
        return findings
    for match in re.finditer(r"<bool[^>]*>\s*([^<]*?)\s*</bool>", text):
        if match.group(1) not in ("true", "false"):
            findings.append(("ERROR", "%s: <bool> %s; booleans are true or false in lower case, or "
                                      "ARCropolis rejects the whole file" % (relative, match.group(1))))
            break
    indexes = set(int(index) for index in re.findall(r'<struct\s+index="(\d+)"', text))
    for name, path in sibling_menus(mod_dir):
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(mod_dir)):
            continue
        try:
            with open(os.path.join(path, *relative.split("/")), encoding="utf8", errors="replace") as handle:
                theirs = set(int(index) for index in re.findall(r'<struct\s+index="(\d+)"', handle.read()))
        except OSError:
            continue
        shared = sorted(indexes & theirs)
        if shared:
            findings.append(("WARN", "%s: popup row %s is also added by %s; the two replace each other"
                             % (relative, ", ".join(str(index) for index in shared), name)))
    return findings


def check_movies(shipped):
    findings = []
    for path in sorted(shipped):
        if path.startswith("stream;/movie/") and path.endswith(".webm"):
            played = "stream:/" + path[len("stream;/"):]
            if len(played) > MAX_MOVIE_PATH:
                findings.append(("WARN", "%s: %s is %d bytes; engine.movie_play takes up to %d"
                                 % (path, played, len(played), MAX_MOVIE_PATH)))
    return findings


def lint(mod_dir, arc_index=DEFAULT_ARC_INDEX):
    path = os.path.join(mod_dir, "menu.toml")
    if not os.path.isfile(path):
        return [("ERROR", "no menu.toml in %s" % mod_dir)]
    with open(path, encoding="utf8", errors="replace") as handle:
        tables, findings = parse(handle.read())
    findings = list(findings)
    if any(level == "ERROR" for level, _ in findings):
        findings.append(("ERROR", "the engine stops at the first error and skips this whole menu.toml"))
        return findings
    shipped = shipped_files(mod_dir)
    vanilla = load_vanilla(arc_index)
    if vanilla is None:
        findings.append(("WARN", "no arc index at %s, so names of the game's own files are not checked"
                         % arc_index))
    seen_ids = set()
    for table in tables:
        kind, line = table["table"], table["line"]
        label = "line %d [[%s]]" % (line, kind)
        if kind == "mode":
            label = 'mode "%s"' % table["id"]
            seen_ids.add(table["id"])
            if table["script"]:
                compiled = "ui/script/%s.lc" % table["script"]
                if compiled not in shipped:
                    findings.append(("WARN", "%s: %s is not in this pack; the mode has no script" % (label, compiled)))
                else:
                    functions = lua_functions(mod_dir, shipped, compiled)
                    if functions is not None and table["runs_as"] is None and "enter" not in functions:
                        findings.append(("WARN", "%s: no runs_as and %s has no enter, so choosing the row "
                                                 "does nothing" % (label, compiled)))
            if table["button"]:
                if table["button"] not in shipped:
                    findings.append(("WARN", "%s: button %s is not in this pack; the area shows the "
                                             "mode's name" % (label, table["button"])))
                else:
                    findings += check_layout_file(mod_dir, shipped, table["button"], label, needs_root=True)
        elif kind == "layout":
            if table["file"] in shipped:
                findings += check_layout_file(mod_dir, shipped, table["file"], label)
            elif vanilla is not None and table["file"] not in vanilla:
                findings.append(("WARN", "%s: %s is neither in this pack nor in the game" % (label, table["file"])))
            if table["over_side_panel"] and table["under_movies"]:
                findings.append(("INFO", "%s: under_movies wins over over_side_panel" % label))
        elif kind == "patch":
            compiled = "ui/script/%s.lc" % table["script"]
            if compiled not in shipped:
                findings.append(("WARN", "%s: %s is not in this pack; the patch is skipped and %s loads as "
                                         "usual" % (label, compiled, table["module"])))
            target = "%s%s.lc" % (ROOTS[table["root"]], table["module"])
            if vanilla is not None and target not in vanilla and target not in shipped:
                findings.append(("INFO", "%s: %s is not in the arc index; it may come from an update or "
                                         "another mod, or the game never loads it" % (label, target)))
        elif kind == "preload":
            for wanted in [table["after"]] + table["files"]:
                if wanted in shipped or (vanilla is not None and wanted in vanilla):
                    continue
                if vanilla is not None:
                    findings.append(("WARN", "%s: %s is neither in this pack nor in the game" % (label, wanted)))
    findings += check_registry(mod_dir)
    findings += check_popups(mod_dir, shipped)
    findings += check_movies(shipped)
    for path in sorted(shipped):
        if path.startswith(("ui/script/", "ui/script_patch/")) and path.endswith(".lc"):
            try:
                with open(os.path.join(mod_dir, *shipped[path].split("/")), "rb") as handle:
                    problem = bytecode_problem(handle.read(32))
            except OSError:
                continue
            if problem:
                findings.append(("ERROR", "%s: %s; the menu skips the script" % (path, problem)))
    lua_sources = [path for path in shipped if path.endswith(".lua")]
    if lua_sources:
        findings.append(("WARN", "%s is Lua source; the game runs only compiled .lc scripts (luac -s with "
                                 "32-bit floats)" % lua_sources[0]
                         + (" (and %d more)" % (len(lua_sources) - 1) if len(lua_sources) > 1 else "")))
    findings.append(("INFO", "menu.toml needs an engine newer than 0.6.0-beta.1; older engines ignore it"))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check a menu pack: menu.toml and the files it names.")
    parser.add_argument("mod_dir", help="your mod folder")
    parser.add_argument("--arc-index", default=DEFAULT_ARC_INDEX, metavar="DIR",
                        help="folder holding arc_files.tsv (default: beside this script)")
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
