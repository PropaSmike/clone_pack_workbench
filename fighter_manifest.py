#!/usr/bin/env python3
"""Read a pack's fighter.toml the way the engine does."""
import re

FIGHTER_KEYS = {
    "name": "str", "base": "str", "display_name": "str", "costumes": "int",
    "color_count": "int", "color_start": "int", "ui_chara": "str",
    "fighter_kind_name": "str", "resource_name": "str", "base_resource_name": "str",
    "series": "str", "disp_order": "int", "save_no": "int", "exhibit_year": "int",
    "narration": "str", "staffroll": "bool", "jingle": "str",
    "owns_param_resources": "bool", "effect_namespace": "int", "article_namespace": "int",
}
ARTICLE_KEYS = {"name": "str", "from": "str", "base_article": "str", "kirby": "bool"}
KIRBY_KEYS = {"statuses": "int", "first": "int", "full_model": "bool", "model": "str"}
MOTION_KEYS = {"name": "str", "animation": "str", "template": "str", "scripts": "str",
               "game": "str", "sound": "str", "effect": "str", "expression": "str",
               "flags": "list", "loop": "bool", "blend_frames": "int",
               "cancel_frame": "int", "xlu": "list", "no_stop_intp": "bool",
               "animation_unk": "int", "no_extra": "bool"}
MESH_KEYS = {"name": "str", "visible": "bool"}
NAME_RE = re.compile(r"^[a-z0-9_]+$")


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
    fighter = {"articles": [], "kirby": None, "params": []}
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
                 "motion": MOTION_KEYS, "mesh": MESH_KEYS}[kind]
        if key not in table:
            raise ManifestError(number, "unknown %s key %s" % (kind, key))
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
    kirby = fighter.get("kirby")
    if kirby:
        if kirby.get("statuses", 0) < 0:
            problems.append("kirby statuses must not be negative")
        if "first" in kirby and kirby["first"] <= 0:
            problems.append("kirby first must be a positive status kind")
        for motion in kirby["motions"]:
            if not motion.get("name") or not motion.get("animation"):
                problems.append("a kirby motion needs name and animation")
        for mesh in kirby["meshes"]:
            if not mesh.get("name"):
                problems.append("a kirby mesh needs a name")
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
