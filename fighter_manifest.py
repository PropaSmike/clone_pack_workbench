#!/usr/bin/env python3
"""Read a pack's fighter.toml the way the engine does."""
import re

FIGHTER_KEYS = {
    "name": "str", "base": "str", "display_name": "str", "costumes": "int",
    "color_count": "int", "color_start": "int", "ui_chara": "str",
    "fighter_kind_name": "str", "resource_name": "str", "base_resource_name": "str",
    "series": "str", "disp_order": "int", "save_no": "int", "exhibit_year": "int",
    "narration": "str", "staffroll": "bool", "css": "bool", "jingle": "str",
    "owns_param_resources": "bool", "effect_namespace": "int", "article_namespace": "int",
}
ARTICLE_KEYS = {"name": "str", "from": "str", "base_article": "str", "kirby": "bool"}
KIRBY_KEYS = {"statuses": "int", "first": "int", "full_model": "bool", "model": "str"}
MOTION_KEYS = {"name": "str", "animation": "str", "template": "str", "scripts": "str",
               "game": "str", "sound": "str", "effect": "str", "expression": "str",
               "flags": "list", "loop": "bool", "blend_frames": "int",
               "cancel_frame": "int", "xlu": "list", "no_stop_intp": "bool",
               "animation_unk": "int", "no_extra": "bool", "victim": "bool"}
MESH_KEYS = {"name": "str", "visible": "bool"}
GRAB_KEYS = {"status": "status", "victim": "status", "then": "status", "node": "str",
             "offset": "vec3", "catch": "bool"}
HURTBOX_KEYS = {"node": "str", "size": "float", "offset": "vec3", "offset2": "vec3",
                "part": "part", "height": "height", "status": "hit_status", "shape": "shape"}
HURTBOX_FIELDS = {
    "part": ("COLLISION_PART_", {"body": 0, "etc": 1, "legs": 2, "body_legs": 3, "head": 4}),
    "height": ("HIT_HEIGHT_", {"low": 0, "center": 1, "high": 2}),
    "hit_status": ("HIT_STATUS_", {"normal": 0, "invincible": 1, "xlu": 2, "off": 3}),
    "shape": ("COLLISION_SHAPE_TYPE_", {"sphere": 0, "aabb": 1, "capsule": 2}),
}
MAX_HURTBOXES = 16
STATUS_NAMES = {
    "ATTACK": 0x27, "ATTACK_DASH": 0x29, "ATTACK_S3": 0x2a, "ATTACK_HI3": 0x2b,
    "ATTACK_LW3": 0x2c, "ATTACK_S4": 0x2f, "ATTACK_LW4": 0x32, "ATTACK_HI4": 0x35,
    "ATTACK_AIR": 0x36, "CATCH": 0x37, "CATCH_PULL": 0x38, "CATCH_DASH": 0x39,
    "CATCH_DASH_PULL": 0x3a, "CATCH_TURN": 0x3b, "CATCH_WAIT": 0x3c, "THROW": 0x40,
    "CAPTURE_PULLED": 0x41, "CAPTURE_WAIT": 0x42, "CLUNG_GANON": 0xbd, "CATCHED_GANON": 0xbe,
    "CATCHED_AIR_GANON": 0xbf, "CLUNG_CAPTAIN": 0xc3, "KOOPA_DIVED": 0xc4,
    "SHOULDERED_DONKEY_START": 0xc5, "SWALLOWED": 0xe6, "BITTEN_WARIO_START": 0xed,
    "CLUNG_DIDDY": 0xf0, "CAPTURE_YOSHI": 0xf3, "CATCHED_REFLET": 0xfe, "CATCHED_RIDLEY": 0x171,
    "MIIFIGHTER_SUPLEX_AIR_CAPTURED": 0x186, "CAPTURE_JACK_WIRE": 0x19c,
    "DOLLY_SUPER_SPECIAL2_CAPTURE": 0x1ae, "CAPTURE_MASTER_SWORD": 0x1b4, "DEMON_DIVED": 0x1ca,
    "SPECIAL_N": 0x1dc, "SPECIAL_S": 0x1dd, "SPECIAL_HI": 0x1de, "SPECIAL_LW": 0x1df,
}
NAME_RE = re.compile(r"^[a-z0-9_]+$")


def status_kind(name):
    """A status name as [[grab]] writes it, with or without FIGHTER_STATUS_KIND_, or None."""
    bare = name.strip()
    if bare.upper().startswith("FIGHTER_STATUS_KIND_"):
        bare = bare[len("FIGHTER_STATUS_KIND_"):]
    return STATUS_NAMES.get(bare.upper())


class ManifestError(ValueError):
    def __init__(self, line, message):
        super().__init__("line %d: %s" % (line, message))
        self.line = line
        self.message = message


def strip_comment(line):
    quoted = False
    for index, char in enumerate(line):
        if char == '"':
            quoted = not quoted
        elif char == "#" and not quoted:
            return line[:index]
    return line


def parse_scalar(text, kind, line, key):
    text = text.strip()
    if kind == "str":
        if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        raise ManifestError(line, "%s must be a quoted string" % key)
    if kind == "bool":
        if text in ("true", "false"):
            return text == "true"
        raise ManifestError(line, "%s must be true or false" % key)
    if kind == "int":
        try:
            return int(text, 0)
        except ValueError:
            raise ManifestError(line, "%s must be a whole number" % key)
    if kind == "list":
        if not (text.startswith("[") and text.endswith("]")):
            raise ManifestError(line, "%s must be a [list]" % key)
        return [item.strip().strip('"') for item in text[1:-1].split(",") if item.strip()]
    if kind == "status":
        if text.startswith('"'):
            name = parse_scalar(text, "str", line, key)
            value = status_kind(name)
            if value is None:
                raise ManifestError(line, '%s: "%s" is not a known status name; write its number'
                                    % (key, name))
        else:
            value = parse_scalar(text, "int", line, key)
        if value < 0:
            raise ManifestError(line, "%s must not be negative" % key)
        return value
    if kind == "float":
        try:
            return float(text)
        except ValueError:
            raise ManifestError(line, "%s must be a number" % key)
    if kind in HURTBOX_FIELDS:
        prefix, names = HURTBOX_FIELDS[kind]
        if not text.startswith('"'):
            return parse_scalar(text, "int", line, key)
        name = parse_scalar(text, "str", line, key)
        bare = name.strip().upper()
        if bare.startswith(prefix):
            bare = bare[len(prefix):]
        if bare.lower() not in names:
            raise ManifestError(line, '%s: "%s" is not one of %s' % (key, name, ", ".join(names)))
        return names[bare.lower()]
    if kind == "vec3":
        parts = parse_scalar(text, "list", line, key)
        if len(parts) != 3:
            raise ManifestError(line, "%s must be [x, y, z]" % key)
        try:
            return [float(part) for part in parts]
        except ValueError:
            raise ManifestError(line, "%s must be [x, y, z] numbers" % key)
    raise ManifestError(line, "unknown kind for %s" % key)


def header(line):
    text = line.strip()
    if text.startswith("[[") and text.endswith("]]"):
        return text[2:-2].strip(), True
    if text.startswith("[") and text.endswith("]"):
        return text[1:-1].strip(), False
    return None, False


def blocks(text):
    """The [[fighter]] blocks with their first line numbers, or the whole file."""
    lines = text.splitlines()
    heads = [index for index, line in enumerate(lines)
             if strip_comment(line).strip() == "[[fighter]]"]
    if not heads:
        return [(1, lines)]
    stray = next((index for index, line in enumerate(lines[:heads[0]])
                  if strip_comment(line).strip()), None)
    if stray is not None:
        raise ManifestError(stray + 1, "a key before the first [[fighter]] belongs to nothing")
    out = []
    for position, start in enumerate(heads):
        end = heads[position + 1] if position + 1 < len(heads) else len(lines)
        out.append((start + 2, lines[start + 1:end]))
    return out


def parse_lines(lines, first_line=1):
    fighter = {"articles": [], "kirby": None, "params": [], "global_motions": [], "grabs": []}
    section = ("fighter", None)
    for offset, raw in enumerate(lines):
        number = first_line + offset
        line = strip_comment(raw).strip()
        if not line:
            continue
        name, array = header(line)
        if name is not None:
            if name.startswith("fighter."):
                name = name[len("fighter."):]
            if (name, array) == ("fighter", False):
                section = ("fighter", None)
            elif (name, array) == ("article", True):
                fighter["articles"].append({})
                section = ("article", fighter["articles"][-1])
            elif (name, array) == ("article.hurtbox", True):
                if not fighter["articles"]:
                    raise ManifestError(number, "[[article.hurtbox]] must follow the [[article]] it belongs to")
                fighter["articles"][-1].setdefault("hurtboxes", []).append({})
                section = ("hurtbox", fighter["articles"][-1]["hurtboxes"][-1])
            elif (name, array) == ("kirby", False):
                fighter["kirby"] = fighter["kirby"] or {"motions": [], "meshes": []}
                section = ("kirby", fighter["kirby"])
            elif (name, array) == ("kirby.motion", True):
                fighter["kirby"] = fighter["kirby"] or {"motions": [], "meshes": []}
                fighter["kirby"]["motions"].append({})
                section = ("motion", fighter["kirby"]["motions"][-1])
            elif (name, array) == ("kirby.mesh", True):
                fighter["kirby"] = fighter["kirby"] or {"motions": [], "meshes": []}
                fighter["kirby"]["meshes"].append({})
                section = ("mesh", fighter["kirby"]["meshes"][-1])
            elif (name, array) == ("global_motion", True):
                fighter["global_motions"].append({})
                section = ("global_motion", fighter["global_motions"][-1])
            elif (name, array) == ("grab", True):
                fighter["grabs"].append({})
                section = ("grab", fighter["grabs"][-1])
            elif not array and (name == "params" or name.startswith("params.")):
                slot, op = None, "set"
                for part in name.split(".")[1:]:
                    if part == "mul":
                        op = "mul"
                    elif part.startswith("c") and part[1:].isdigit():
                        slot = int(part[1:])
                    else:
                        raise ManifestError(number, "unknown params table [%s]" % name)
                section = ("params", (slot, op))
            else:
                raise ManifestError(number, "unknown table [%s]" % name)
            continue
        if "=" not in line:
            raise ManifestError(number, "expected key = value")
        key, value = (part.strip() for part in line.split("=", 1))
        kind, target = section
        if kind == "params":
            slot, op = target
            text = value.strip()
            try:
                parsed = float(text) if ("." in text or "e" in text) else int(text, 0)
            except ValueError:
                raise ManifestError(number, "%s must be a number" % key)
            if op == "mul" and isinstance(parsed, int):
                raise ManifestError(number, "%s: a multiplier must be a decimal" % key)
            fighter["params"].append({"name": key, "slot": slot, "op": op, "value": parsed})
            continue
        table = {"fighter": FIGHTER_KEYS, "article": ARTICLE_KEYS, "kirby": KIRBY_KEYS,
                 "motion": MOTION_KEYS, "mesh": MESH_KEYS, "global_motion": MOTION_KEYS,
                 "grab": GRAB_KEYS, "hurtbox": HURTBOX_KEYS}[kind]
        if key not in table:
            label = "motion" if kind == "global_motion" else kind
            raise ManifestError(number, "unknown %s key %s" % (label, key))
        parsed = parse_scalar(value, table[key], number, key)
        if kind == "fighter":
            if key == "color_count":
                key = "costumes"
            fighter[key] = parsed
        else:
            target[key] = parsed
    return fighter


def check(fighter):
    """The rules the engine applies after parsing, as messages."""
    problems = []
    if not fighter.get("name"):
        problems.append("name is required")
    elif not NAME_RE.match(fighter["name"]):
        problems.append("name must be lowercase letters, digits and underscores")
    if not fighter.get("base"):
        problems.append("base is required")
    costumes = fighter.get("costumes", 8)
    start = fighter.get("color_start", 0)
    if costumes < 1 or start + costumes > 256:
        problems.append("costumes must be 1 to 256 including color_start")
    for article in fighter["articles"]:
        if not article.get("name"):
            problems.append("an article needs a name")
        source, base_article = article.get("from"), article.get("base_article")
        if not source and not base_article:
            problems.append("article %s needs from = \"fighter/weapon\" or base_article"
                            % article.get("name"))
        if source and base_article:
            problems.append("article %s has both from and base_article" % article.get("name"))
        if source and (source.count("/") != 1 or not all(source.split("/"))):
            problems.append("article %s: from must be \"fighter/weapon\"" % article.get("name"))
        problems += hurtbox_problems(article)
    kirby = fighter.get("kirby")
    if kirby:
        if kirby.get("statuses", 0) < 0:
            problems.append("kirby statuses must not be negative")
        if "first" in kirby and kirby["first"] <= 0:
            problems.append("kirby first must be a positive status kind")
        for motion in kirby["motions"]:
            if not motion.get("name") or not motion.get("animation"):
                problems.append("a kirby motion needs name and animation")
            elif motion.get("victim"):
                problems.append("kirby motion %s: victim is for global motions" % motion["name"])
        for mesh in kirby["meshes"]:
            if not mesh.get("name"):
                problems.append("a kirby mesh needs a name")
    for motion in fighter.get("global_motions", []):
        if not motion.get("name"):
            problems.append("a global motion needs a name")
        elif not motion.get("animation") and not motion.get("template") and not motion.get("victim"):
            problems.append("global motion %s needs a template, an animation or victim = true"
                            % motion["name"])
    for grab in fighter.get("grabs", []):
        if "status" not in grab:
            problems.append("a grab needs status, the grabber status its CATCH box belongs to")
    return problems


def hurtbox_problems(article):
    hurtboxes = article.get("hurtboxes") or []
    name = article.get("name")
    if not hurtboxes:
        return []
    if not article.get("from"):
        return ["article %s: hurtboxes need from = \"fighter/weapon\"" % name]
    if len(hurtboxes) > MAX_HURTBOXES:
        return ["article %s: at most %d hurtboxes" % (name, MAX_HURTBOXES)]
    problems = []
    for hurtbox in hurtboxes:
        node = (hurtbox.get("node") or "").strip()
        if not node:
            problems.append("article %s: a hurtbox needs a node" % name)
            continue
        size = hurtbox.get("size", 0.0)
        if not (size > 0.0 and size != float("inf")):
            problems.append("article %s: hurtbox on %s: size must be above 0" % (name, node))
        shape = hurtbox.get("shape", 2 if "offset2" in hurtbox else 0)
        for key, field, value in (("part", "part", hurtbox.get("part", 1)),
                                  ("height", "height", hurtbox.get("height", 1)),
                                  ("status", "hit_status", hurtbox.get("status", 0)),
                                  ("shape", "shape", shape)):
            names = HURTBOX_FIELDS[field][1]
            if value not in names.values():
                problems.append("article %s: hurtbox on %s: %s %d is not one of %s"
                                % (name, node, key, value, ", ".join(names)))
    return problems


def read(path):
    """Every fighter the file declares. Raises ManifestError on the first fault."""
    with open(path, encoding="utf8") as handle:
        text = handle.read()
    fighters = []
    for first_line, lines in blocks(text):
        fighter = parse_lines(lines, first_line)
        problems = check(fighter)
        if problems:
            raise ManifestError(first_line, problems[0])
        fighters.append(fighter)
    return fighters
