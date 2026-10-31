#!/usr/bin/env python3
"""Check a Mii parts pack: mii.toml by the engine's own rules, then the files each hat and outfit needs."""
import argparse
import json
import os
import re
import sys
import zlib

MANIFEST = "mii.toml"
COLOURS = 12
MAX_ID = 48
MAX_PARTS = 256
MAX_HAIR_TYPES = 256
MAX_DISP_ORDER = 0x7fffffff
FIRST_FREE = {"mii_hat": 133, "mii_outfit": 154}
LAST_SAVE_NO = {"mii_hat": 0x19f, "mii_outfit": 0x3ff}
MODEL_TYPES = ("normal", "hat", "face_only", "term", "no_head")
FIGHTERS = {"miifighter": "miifighter", "brawler": "miifighter",
            "miiswordsman": "miiswordsman", "swordfighter": "miiswordsman",
            "miigunner": "miigunner", "gunner": "miigunner"}
GENDERS = ("male", "m", "female", "f", "both")
OUTFIT_MOTION = ("flip.prc", "ik.prc", "scharge.prc", "update.prc")
KEYS = {
    "mii_hat": {"id": "text", "base": "text", "model_type": "text", "hair_model_types": "texts",
                "owned": "flag", "disp_order": "number", "swing": "flag", "is_patch": "flag"},
    "mii_outfit": {"id": "text", "base": "text", "fighter": "text", "gender": "text", "name": "text",
                   "owned": "flag", "disp_order": "number", "swing": "flag", "is_patch": "flag"},
}
TABLES = tuple(KEYS)
ID_RE = re.compile(r"^[a-z0-9_]{1,%d}$" % MAX_ID)


def _default_arc_index():
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.join(here, "arc_index"),
                      os.path.join(os.path.dirname(here), "arc_index"),
                      os.path.join(os.path.dirname(os.path.dirname(here)), "arc_index")):
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(here, "arc_index")


DEFAULT_ARC_INDEX = os.environ.get("SSBU_ARC_INDEX", _default_arc_index())


class MiiError(Exception):
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
    if re.fullmatch(r"[+-]?\d+", digits):
        return ("number", int(digits))
    return None


def outfit_name(part_id):
    for suffix in ("_m", "_f"):
        if part_id.endswith(suffix) and len(part_id) > len(suffix):
            return part_id[:-len(suffix)]
    return part_id


def ui_id(table, part_id):
    if table == "mii_hat":
        return "ui_mii_hat_" + part_id
    return "ui_mii_body_" + (part_id[2:] if part_id.startswith("b_") else part_id)


def hair_entry(text):
    hair, _, model = text.partition("=")
    try:
        number = int(hair.strip())
    except ValueError:
        return None
    if not 0 <= number < MAX_HAIR_TYPES or model.strip() not in MODEL_TYPES:
        return None
    return number, model.strip()


def read_blocks(text):
    """Every table in the file with its raw text, without judging it; used by the window too."""
    blocks = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = strip_comment(raw).strip()
        if not line:
            continue
        if line.startswith("[[") and line.endswith("]]"):
            blocks.append({"table": line[2:-2].strip(), "line": number, "raw": {}, "lines": {}})
            continue
        if "=" not in line or not blocks:
            blocks.append({"table": None, "line": number, "raw": {}, "lines": {}})
            continue
        key, _, value = line.partition("=")
        blocks[-1]["raw"][key.strip()] = value.strip()
        blocks[-1]["lines"][key.strip()] = number
    return blocks


def finish(block, values, parts):
    line, table = block["line"], block["table"]
    part = {"table": table, "line": line, "id": values.get("id", "").strip(),
            "base": values.get("base", "").strip(), "owned": values.get("owned", True),
            "disp_order": values.get("disp_order"), "swing": values.get("swing"),
            "is_patch": values.get("is_patch"), "model_type": values.get("model_type"),
            "hair_model_types": values.get("hair_model_types", []),
            "fighter": values.get("fighter"), "gender": values.get("gender"),
            "name": values.get("name")}
    if not part["id"]:
        raise MiiError(line, "[[%s]] needs id" % table)
    if not part["base"]:
        raise MiiError(line, "[[%s]] needs base, the game's hat or outfit it copies" % table)
    if not ID_RE.match(part["id"]):
        raise MiiError(line, 'id "%s" must be 1 to %d lower case letters, digits or _' % (part["id"], MAX_ID))
    if table == "mii_outfit":
        if part["fighter"] is None:
            raise MiiError(line, "[[mii_outfit]] needs fighter: miifighter, miiswordsman or miigunner")
        if not part["id"].startswith("b_"):
            raise MiiError(line, 'outfit id "%s" must start with b_, as the game\'s do' % part["id"])
        if part["name"] is not None and not ID_RE.match(part["name"]):
            raise MiiError(line, 'name "%s" must be lower case letters, digits or _' % part["name"])
    if any(other["table"] == table and other["id"] == part["id"] for other in parts):
        raise MiiError(line, '%s "%s" is declared twice' % (table[4:], part["id"]))
    if len(parts) >= MAX_PARTS:
        raise MiiError(line, "more than %d parts in one mii.toml" % MAX_PARTS)
    return part


def parse(text):
    """(parts, problems): the hats and outfits the engine keeps, and why it would refuse the file.
    The engine reads all of mii.toml or none of it, so every problem is an ERROR."""
    parts, problems = [], []
    for block in read_blocks(text):
        if block["table"] is None:
            problems.append(("ERROR", "line %d: a key outside any table, or a line with no =" % block["line"]))
            continue
        if block["table"] not in KEYS:
            problems.append(("ERROR", "line %d: [[%s]] is not a mii.toml table (%s)"
                             % (block["line"], block["table"], ", ".join(TABLES))))
            continue
        kinds = KEYS[block["table"]]
        values, refused = {}, False
        for key, raw in block["raw"].items():
            where = block["lines"][key]
            if key not in kinds:
                problems.append(("ERROR", "line %d: [[%s]] has no key %s" % (where, block["table"], key)))
                refused = True
                continue
            value = parse_value(raw)
            wanted = kinds[key]
            bad = value is None or value[0] != wanted
            if not bad and key == "disp_order":
                bad = not 0 <= value[1] <= MAX_DISP_ORDER
            if not bad and key == "model_type":
                bad = value[1].strip() not in MODEL_TYPES
            if not bad and key == "fighter":
                bad = value[1].strip() not in FIGHTERS
            if not bad and key == "gender":
                bad = value[1].strip() not in GENDERS
            if not bad and key == "hair_model_types":
                entries = [hair_entry(item) for item in value[1]]
                bad = None in entries or len(entries) > MAX_HAIR_TYPES
                if not bad:
                    merged = {}
                    for hair, model in entries:
                        merged.pop(hair, None)
                        merged[hair] = model
                    value = ("texts", list(merged.items()))
            if bad:
                problems.append(("ERROR", "line %d: %s = %s is not a valid %s"
                                 % (where, key, raw, describe(key, wanted))))
                refused = True
                continue
            values[key] = value[1].strip() if isinstance(value[1], str) else value[1]
        if refused:
            continue
        try:
            parts.append(finish(block, values, parts))
        except MiiError as problem:
            problems.append(("ERROR", str(problem)))
    return parts, problems


def describe(key, kind):
    return {"model_type": "model type (%s)" % ", ".join(MODEL_TYPES[:4]),
            "fighter": "fighter (miifighter, miiswordsman, miigunner)",
            "gender": "gender (male, female, both)",
            "hair_model_types": 'list like ["12=face_only", "40=hat"], hair types 0 to 255',
            "disp_order": "order from 0 to %d" % MAX_DISP_ORDER}.get(
        key, {"text": "quoted text", "texts": 'list of quoted texts', "flag": "true or false",
              "number": "whole number"}[kind])


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
    """{"mii_hat": ids, "mii_outfit": ids} from the arc index's folders, or None without one."""
    path = os.path.join(arc_index, "arc_dirs.tsv")
    if not os.path.isfile(path):
        return None
    found = {"mii_hat": set(), "mii_outfit": set()}
    with open(path, encoding="utf8", errors="replace") as handle:
        for line in handle:
            parts = line.split("\t", 1)[0].strip().split("/")
            if len(parts) == 2 and parts[0] == "miihat":
                found["mii_hat"].add(parts[1])
            elif len(parts) == 3 and parts[0] == "miibody":
                found["mii_outfit"].add(parts[2])
    return found if found["mii_hat"] else None


def folder_of(part):
    if part["table"] == "mii_hat":
        return "miihat/%s" % part["id"]
    return "miibody/%s/%s" % (FIGHTERS[part["fighter"]], part["id"])


def colour_files(part, shipped):
    """{cNN: [paths]} as each colour's folder lists them, the motion files in every colour."""
    if part["table"] == "mii_hat":
        model = "miihat/%s/model/body/" % part["id"]
        motion = "miihat/%s/motion/body/c00/" % part["id"]
    else:
        fighter = FIGHTERS[part["fighter"]]
        model = "fighter/%s/model/%s/" % (fighter, part["id"])
        motion = "fighter/%s/motion/%s/c00/" % (fighter, part["id"])
    moves = sorted(shipped[path] for path in shipped if path.startswith(motion))
    out = {}
    for index in range(COLOURS):
        colour = "c%02d" % index
        prefix = "%s%s/" % (model, colour)
        own = sorted(shipped[path] for path in shipped if path.startswith(prefix))
        out[colour] = own + moves if own else []
    return out


def config_entries(part, shipped):
    """(new-dir-infos, new-dir-files) this part needs, from the files it ships."""
    folder = folder_of(part)
    infos, files = [folder], {}
    for colour, paths in colour_files(part, shipped).items():
        if paths:
            infos.append("%s/%s" % (folder, colour))
            files["%s/%s" % (folder, colour)] = paths
    return infos, files


def read_config(mod_dir):
    path = os.path.join(mod_dir, "config.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def fixed_config(config, parts, shipped):
    """config.json with each part's folders written from disk; every other entry kept."""
    config = dict(config)
    infos = list(config.get("new-dir-infos") or [])
    files = dict(config.get("new-dir-files") or {})
    for part in parts:
        folder = folder_of(part)
        infos = [entry for entry in infos if entry != folder and not entry.startswith(folder + "/")]
        files = {key: value for key, value in files.items() if not key.startswith(folder + "/")}
        wanted_infos, wanted_files = config_entries(part, shipped)
        infos += wanted_infos
        files.update(wanted_files)
    config["new-dir-infos"] = infos
    config["new-dir-files"] = files
    return config


def write_config(mod_dir, parts):
    """Write the parts' folders into config.json. Returns the folders written, or None if unreadable."""
    config = read_config(mod_dir)
    if config is None:
        return None
    shipped = shipped_files(mod_dir)
    fixed = fixed_config(config, parts, shipped)
    if fixed == config:
        return []
    path = os.path.join(mod_dir, "config.json")
    with open(path, "w", encoding="utf8", newline="\n") as handle:
        json.dump(fixed, handle, indent=2)
        handle.write("\n")
    return [folder_of(part) for part in parts]


def labels(mod_dir):
    path = os.path.join(mod_dir, "ui", "message", "msg_name.xmsbt")
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8-sig", errors="replace") as handle:
        return set(re.findall(r'label="([^"]+)"', handle.read()))


def check_part(part, mod_dir, shipped, config, vanilla, names, declared):
    findings = []
    table, part_id = part["table"], part["id"]
    label = '%s "%s"' % (table[4:], part_id)
    if vanilla is not None:
        if part_id in vanilla[table]:
            findings.append(("ERROR", "%s: the game already has this id; the engine skips the part" % label))
        if part["base"] not in vanilla[table] and part["base"] not in declared:
            findings.append(("ERROR", "%s: base %s is not one of the game's %ss; the engine skips the part"
                             % (label, part["base"], table[4:])))
    if part["base"] in declared:
        findings.append(("INFO", "%s: its base %s is another part of this pack, declared above it"
                         % (label, part["base"])))
    colours = colour_files(part, shipped)
    missing = [colour for colour, paths in colours.items()
               if not any(path.lower().endswith("/model.numdlb") for path in paths)]
    if len(missing) == COLOURS:
        findings.append(("ERROR", "%s: no model.numdlb under %s; the game draws nothing" % (
            label, "miihat/%s/model/body/cNN" % part_id if table == "mii_hat"
            else "fighter/%s/model/%s/cNN" % (FIGHTERS[part["fighter"]], part_id))))
    elif missing:
        findings.append(("ERROR", "%s: colours %s have no model.numdlb; a Mii whose favourite colour is one "
                                  "of them loads nothing" % (label, ", ".join(missing))))
    if table == "mii_outfit":
        motion = "fighter/%s/motion/%s/c00/" % (FIGHTERS[part["fighter"]], part_id)
        absent = [name for name in OUTFIT_MOTION if (motion + name) not in shipped]
        if absent:
            findings.append(("WARN", "%s: %s has no %s; copy them from the base outfit's motion folder"
                             % (label, motion, ", ".join(absent))))
    if config is None:
        findings.append(("ERROR", "config.json is not valid JSON"))
    else:
        wanted_infos, wanted_files = config_entries(part, shipped)
        infos = set(config.get("new-dir-infos") or [])
        files = config.get("new-dir-files") or {}
        if not set(wanted_infos) <= infos or any(sorted(files.get(key) or []) != sorted(value)
                                                for key, value in wanted_files.items()):
            findings.append(("ERROR", "%s: config.json does not list %s and its colour folders with their "
                                      "files; the game never loads them (run with --fix-config)"
                             % (label, folder_of(part))))
    if table == "mii_hat":
        icons = ["ui/replace/mii_hat/mii_hat_0/mii_hat_0_%s.bntx" % part_id,
                 "ui/replace_patch/mii_hat/mii_hat_0/mii_hat_0_%s.bntx" % part_id]
        wanted_label = "nam_mii_hat_%s" % part_id
    else:
        name = part["name"] or outfit_name(part_id)
        icons = ["ui/replace/mii_body/mii_body_0/mii_body_0_%s.bntx" % name,
                 "ui/replace_patch/mii_body/mii_body_0/mii_body_0_%s.bntx" % name]
        wanted_label = "nam_mii_body_%s" % part_id
    if not any(icon in shipped for icon in icons):
        findings.append(("WARN", "%s: no icon at %s; the shop and the vault show none" % (label, icons[0])))
    if wanted_label not in names:
        findings.append(("WARN", "%s: ui/message/msg_name.xmsbt has no %s; the menus show ????"
                         % (label, wanted_label)))
    return findings


def lint(mod_dir, arc_index=DEFAULT_ARC_INDEX):
    path = os.path.join(mod_dir, MANIFEST)
    if not os.path.isfile(path):
        return [("ERROR", "no mii.toml in %s" % mod_dir)]
    with open(path, encoding="utf8", errors="replace") as handle:
        parts, findings = parse(handle.read())
    findings = list(findings)
    if findings:
        findings.append(("ERROR", "the engine skips this whole mii.toml"))
        return findings
    shipped = shipped_files(mod_dir)
    vanilla = load_vanilla(arc_index)
    if vanilla is None:
        findings.append(("WARN", "no arc index at %s, so ids and bases are not checked against the game's"
                         % arc_index))
    config = read_config(mod_dir)
    names = labels(mod_dir)
    declared = set()
    for part in parts:
        findings += check_part(part, mod_dir, shipped, config, vanilla, names, declared)
        declared.add(part["id"])
    for table in TABLES:
        count = sum(part["table"] == table for part in parts)
        room = LAST_SAVE_NO[table] - FIRST_FREE[table] + 1
        if count > room:
            findings.append(("ERROR", "%d %ss, but the save holds only %d added ones" % (count, table[4:], room)))
    findings.append(("INFO", "%d hat(s), %d outfit(s); each keeps its save number in "
                             "sd:/ultimate/clone_engine/mii_parts.txt" % (
                                 sum(p["table"] == "mii_hat" for p in parts),
                                 sum(p["table"] == "mii_outfit" for p in parts))))
    findings.append(("INFO", "mii.toml needs an engine with Mii parts (CAP_MII_PARTS); older engines ignore it"))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check a Mii parts pack: mii.toml and the files it needs.")
    parser.add_argument("mod_dir", help="your mod folder")
    parser.add_argument("--arc-index", default=DEFAULT_ARC_INDEX, metavar="DIR",
                        help="folder holding arc_dirs.tsv (default: beside this script)")
    parser.add_argument("--fix-config", action="store_true",
                        help="write each part's folders into config.json from the files on disk")
    arguments = parser.parse_args(argv)
    if arguments.fix_config:
        path = os.path.join(arguments.mod_dir, MANIFEST)
        if os.path.isfile(path):
            with open(path, encoding="utf8", errors="replace") as handle:
                parts, problems = parse(handle.read())
            if not problems:
                written = write_config(arguments.mod_dir, parts)
                if written is None:
                    print("config.json is not valid JSON; nothing written")
                else:
                    print("config.json: %s" % (", ".join(written) if written else "already lists every part"))
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
