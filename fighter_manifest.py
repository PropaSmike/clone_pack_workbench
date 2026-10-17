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
    "partner": "partner", "switch": "list",
}
PARTNER_PARAMS = {
    "jostle_data_nana.speed_x_gg": "float", "jostle_data_nana.speed_x_ga": "float",
    "jostle_data_nana.speed_x_ag": "float", "jostle_data_nana.speed_x_aa": "float",
    "jostle_data_nana.speed_z": "float", "jostle_data_nana.max_pos_z": "float",
    "jostle_data_nana_small.speed_x_gg": "float", "jostle_data_nana_small.speed_x_ga": "float",
    "jostle_data_nana_small.speed_x_ag": "float", "jostle_data_nana_small.speed_x_aa": "float",
    "jostle_data_nana_small.speed_z": "float", "jostle_data_nana_small.max_pos_z": "float",
    "rebirth_diff_x": "float", "nana_damage_mul": "float", "nana_damage_reaction_mul": "float",
    "unk_1435e39667": "float", "nana_different_damage_motion_rate": "float",
    "nana_opt_dst": "float", "nana_delay": "int", "nana_pos_x_offset": "float",
    "nana_partner_comp_rate_x": "float", "nana_opt_dst_max": "float", "nana_opt_near_dst": "float",
    "nana_partner_near_comp_rate_x": "float", "nana_roulette_pos_x_offset": "float",
    "nana_warp_sync_dst": "float", "popo_modify_jostle_range": "float",
    "popo_jostle_add_back": "float", "popo_jostle_weight_mul": "float",
    "nana_partner_modify_jostle_comp_rate_x": "float",
    "nana_partner_modify_jostle_comp_rate_continual_frame": "int", "unk_219438148d": "float",
    "unk_214f2437da": "float", "nana_cp_rank_for_2": "int", "nana_cp_rank_for_3": "int",
    "nana_cp_rank_for_4": "int", "nana_cp_rank_for_5": "int", "nana_cp_rank_for_6": "int",
    "nana_cp_rank_for_7": "int", "nana_cp_rank_for_8": "int", "final_couple_distance": "float",
    "final_couple_condor_distance": "float", "unk_1a4d9acd60": "int", "final_scroll_rate": "float",
    "final_scroll_rate_change_frame": "int",
}
PARTNER_BASES = ("popo",)
NO_SWITCH_BASES = ("popo", "nana")
MAX_SWITCH_MEMBERS = 2
ARTICLE_KEYS = {"name": "str", "from": "str", "base_article": "str", "kirby": "bool",
                "lvd": "str"}
LVD_VERTEX_KEYS = {"vertex": "int", "joint": "str", "offset": "vec3", "joint_left": "str"}
MAX_LVD_VERTICES = 32
MAX_LVD_VERTEX_INDEX = 0xFFFF
KIRBY_KEYS = {"statuses": "int", "first": "int", "full_model": "bool", "model": "str"}
MOTION_KEYS = {"name": "str", "animation": "str", "template": "str", "scripts": "str",
               "game": "str", "sound": "str", "effect": "str", "expression": "str",
               "flags": "list", "loop": "bool", "blend_frames": "int",
               "cancel_frame": "int", "xlu": "list", "no_stop_intp": "bool",
               "animation_unk": "int", "no_extra": "bool", "victim": "bool"}
MESH_KEYS = {"name": "str", "visible": "bool"}
HUD_KEYS = {"from": "str", "layout": "str"}
HUD_LAYOUT_BYTES = set("abcdefghijklmnopqrstuvwxyz0123456789_-./")
HUD_DONORS = ("jack", "cloud", "inkling", "brave", "littlemac", "shulk", "reflet", "pickel",
              "trail", "dolly", "demon")
FINAL_KEYS = {"from": "str"}
FINAL_DONORS = ("donkey", "pikachu", "purin", "peach", "daisy", "pichu", "marth", "lucina",
                "younglink", "roy", "chrom", "pikmin", "toonlink", "wiifit")
TETHER_KEYS = {"from": "str"}
TETHER_BOX_KEYS = {"p1": "vec2", "p2": "vec2"}
TETHER_DONORS = ("samus", "samusd", "luigi", "younglink", "szerosuit", "lucas", "toonlink")
MAX_TETHER_BOXES = 8
SWITCH_BASES = ("eflame", "elight", "pzenigame", "pfushigisou", "plizardon")
GRAB_KEYS = {"status": "status", "victim": "status", "then": "status", "node": "str",
             "offset": "vec3", "catch": "bool"}
COMMANDS_KEYS = {"vanilla": "bool", "special_command_life_max": "frames",
                 "super_special_command_life_max": "frames", "special_command_ab_button_life": "frames",
                 "special_command_neutral_threshold": "threshold",
                 "special_command_stick_range": "stick_range"}
COMMAND_KEYS = {"name": "str", "input": "input", "button": "button", "super": "bool",
                "life": "frames", "neutral_resets": "bool", "reverse": "bool", "cpu": "chance"}
COMMAND_BUTTONS = ("special", "attack", "either", "none")
MAX_COMMANDS = 32
MAX_COMMAND_STEPS = 12
STICK_SECTORS = 7
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
    if kind == "partner":
        if text.startswith('"'):
            return parse_scalar(text, "str", line, key)
        if text in ("true", "false"):
            return text == "true"
        raise ManifestError(line, '%s must be true, false or a fighter\'s name in quotes' % key)
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
    if kind == "frames":
        value = parse_scalar(text, "int", line, key)
        if not 1 <= value <= 255:
            raise ManifestError(line, "%s must be 1 to 255 frames" % key)
        return value
    if kind == "chance":
        value = parse_scalar(text, "float", line, key)
        if not 0.0 <= value <= 1.0:
            raise ManifestError(line, "%s must be a chance from 0 to 1" % key)
        return value
    if kind == "threshold":
        value = parse_scalar(text, "float", line, key)
        if not 0.0 <= value < 1.0:
            raise ManifestError(line, "%s must be a number from 0 to below 1" % key)
        return value
    if kind == "stick_range":
        if not (text.startswith("[") and text.endswith("]")):
            raise ManifestError(line, "%s must be a list of %d [min, max] pairs" % (key, STICK_SECTORS))
        pairs = re.findall(r"\[([^\[\]]*)\]", text[1:-1])
        if len(pairs) != STICK_SECTORS:
            raise ManifestError(line, "%s must have exactly %d [min, max] pairs" % (key, STICK_SECTORS))
        out = []
        for index, pair in enumerate(pairs):
            low_high = parse_scalar("[%s]" % pair, "vec2", line, key)
            if low_high[0] > low_high[1] or not all(-180.0 <= v <= 180.0 for v in low_high):
                raise ManifestError(line, "%s[%d] needs min <= max within -180..180 degrees" % (key, index))
            out.append(low_high)
        return out
    if kind == "input":
        digits = parse_scalar(text, "str", line, key) if text.startswith('"') else text
        if not digits or any(char not in "123456789" for char in digits):
            raise ManifestError(line, 'input "%s" must be numpad digits 1 to 9' % digits)
        if any(a == b for a, b in zip(digits, digits[1:])):
            raise ManifestError(line, 'input "%s" repeats a direction; put 5 between two of the same' % digits)
        if digits[0] == "5" or digits[-1] == "5":
            raise ManifestError(line, 'input "%s" must start and end on a direction, not 5' % digits)
        if len(digits) > MAX_COMMAND_STEPS:
            raise ManifestError(line, 'input "%s" has more than %d directions' % (digits, MAX_COMMAND_STEPS))
        return digits
    if kind == "button":
        name = parse_scalar(text, "str", line, key)
        if name not in COMMAND_BUTTONS:
            raise ManifestError(line, 'button "%s" must be special, attack, either or none' % name)
        return name
    if kind == "vec2":
        parts = parse_scalar(text, "list", line, key)
        if len(parts) != 2:
            raise ManifestError(line, "%s must be [x, y]" % key)
        try:
            return [float(part) for part in parts]
        except ValueError:
            raise ManifestError(line, "%s must be [x, y] numbers" % key)
    if kind == "vec3":
        parts = parse_scalar(text, "list", line, key)
        if len(parts) != 3:
            raise ManifestError(line, "%s must be [x, y, z]" % key)
        try:
            return [float(part) for part in parts]
        except ValueError:
            raise ManifestError(line, "%s must be [x, y, z] numbers" % key)
    raise ManifestError(line, "unknown kind for %s" % key)


def partner_param(key, text, line):
    """A [partner_params] value checked against the Ice Climbers' word of that name."""
    name = key[len("param_private."):] if key.startswith("param_private.") else key
    kind = PARTNER_PARAMS.get(name)
    if kind is None:
        raise ManifestError(line, "%s is not one of the Ice Climbers' partner params" % key)
    text = text.strip()
    try:
        return int(text, 10) if kind == "int" else float(text)
    except ValueError:
        raise ManifestError(line, "%s must be %s" % (key, "a whole number" if kind == "int" else "a number"))


def has_partner(fighter):
    """The engine's partner default: the Ice Climbers' own pair unless switch or partner says otherwise."""
    partner = fighter.get("partner")
    if partner is None:
        return fighter.get("base") in PARTNER_BASES and not fighter.get("switch")
    return partner is not False


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
    fighter = {"articles": [], "kirby": None, "params": [], "global_motions": [], "grabs": [],
               "partner_params": [], "command_settings": {}, "commands": []}
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
            elif (name, array) == ("article.lvd_vertex", True):
                if not fighter["articles"]:
                    raise ManifestError(number, "[[article.lvd_vertex]] must follow the [[article]] it belongs to")
                fighter["articles"][-1].setdefault("lvd_vertices", []).append({})
                section = ("lvd_vertex", fighter["articles"][-1]["lvd_vertices"][-1])
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
            elif (name, array) == ("hud", False):
                fighter["hud"] = fighter.get("hud") or {}
                section = ("hud", fighter["hud"])
            elif (name, array) == ("final", False):
                fighter["final"] = fighter.get("final") or {}
                section = ("final", fighter["final"])
            elif (name, array) == ("tether", False):
                fighter["tether"] = fighter.get("tether") or {"boxes": []}
                section = ("tether", fighter["tether"])
            elif (name, array) == ("tether.box", True):
                fighter["tether"] = fighter.get("tether") or {"boxes": []}
                fighter["tether"]["boxes"].append({})
                section = ("tether_box", fighter["tether"]["boxes"][-1])
            elif (name, array) == ("partner_params", False):
                section = ("partner_params", None)
            elif (name, array) == ("commands", False):
                section = ("commands", fighter["command_settings"])
            elif (name, array) == ("command", True):
                fighter["commands"].append({})
                section = ("command", fighter["commands"][-1])
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
        if kind == "partner_params":
            fighter["partner_params"].append(
                {"name": key, "value": partner_param(key, value, number)})
            continue
        table = {"fighter": FIGHTER_KEYS, "article": ARTICLE_KEYS, "kirby": KIRBY_KEYS,
                 "motion": MOTION_KEYS, "mesh": MESH_KEYS, "global_motion": MOTION_KEYS,
                 "grab": GRAB_KEYS, "hurtbox": HURTBOX_KEYS, "lvd_vertex": LVD_VERTEX_KEYS,
                 "hud": HUD_KEYS, "final": FINAL_KEYS, "tether": TETHER_KEYS,
                 "tether_box": TETHER_BOX_KEYS, "commands": COMMANDS_KEYS,
                 "command": COMMAND_KEYS}[kind]
        if key not in table:
            label = {"global_motion": "motion", "tether_box": "tether.box"}.get(kind, kind)
            raise ManifestError(number, "unknown %s key %s" % (label, key))
        parsed = parse_scalar(value, table[key], number, key)
        if kind == "hud" and key == "from" and parsed not in HUD_DONORS:
            raise ManifestError(number, 'hud from "%s" is not a HUD the engine drives; use %s'
                                % (parsed, ", ".join('"%s"' % name for name in HUD_DONORS)))
        if kind == "hud" and key == "layout" and not (
                parsed.endswith(".arc") and not parsed.startswith("/") and "//" not in parsed
                and set(parsed) <= HUD_LAYOUT_BYTES):
            raise ManifestError(number, 'hud layout "%s" must be a lowercase arc path ending in .arc, '
                                        'such as "ui/layout/hud/my_fighter/layout.arc"' % parsed)
        if kind == "final" and key == "from" and parsed not in FINAL_DONORS:
            raise ManifestError(number, 'final from "%s" is not a Final Smash a clone can borrow; use %s'
                                % (parsed, ", ".join('"%s"' % name for name in FINAL_DONORS)))
        if kind == "tether" and key == "from" and parsed not in TETHER_DONORS:
            raise ManifestError(number, 'tether from "%s" has no tether; use %s'
                                % (parsed, ", ".join('"%s"' % name for name in TETHER_DONORS)))
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
    name = fighter.get("name")
    if fighter.get("switch"):
        if len(fighter["switch"]) > MAX_SWITCH_MEMBERS:
            problems.append("%s switches with at most two other fighters" % name)
        if fighter.get("base") in NO_SWITCH_BASES:
            problems.append("%s is on the Ice Climbers, who cannot switch" % name)
        if name in fighter["switch"]:
            problems.append("%s cannot switch with itself" % name)
    if fighter.get("partner") == name:
        problems.append("%s cannot name itself as its partner; partner = true gives it a copy of itself"
                        % name)
    if fighter.get("partner") not in (None, False) and fighter.get("switch"):
        problems.append("%s has both a partner and a switch group; a player slot holds one or the other"
                        % name)
    if fighter.get("partner_params") and not has_partner(fighter):
        problems.append("%s has partner_params but no partner" % name)
    tether = fighter.get("tether")
    if tether is not None:
        if len(tether["boxes"]) > MAX_TETHER_BOXES:
            problems.append("at most %d tether boxes" % MAX_TETHER_BOXES)
        for index, shape in enumerate(tether["boxes"], 1):
            if "p1" not in shape or "p2" not in shape:
                problems.append("tether box %d needs p1 and p2" % index)
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
        problems += lvd_problems(article)
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
    commands = fighter.get("commands", [])
    if len(commands) > MAX_COMMANDS:
        problems.append("at most %d commands" % MAX_COMMANDS)
    seen = set()
    for command in commands:
        if not command.get("name"):
            problems.append("a command needs a name")
            continue
        if not NAME_RE.match(command["name"]):
            problems.append("command %s: name must be lowercase letters, digits and underscores"
                            % command["name"])
        if "input" not in command:
            problems.append("command %s needs an input" % command["name"])
        if command.get("cpu", 0) > 0 and command.get("button") == "none":
            problems.append("command %s: cpu needs a button, a computer player gets the command when it presses it"
                            % command["name"])
        if command["name"] in seen:
            problems.append("command %s is declared twice" % command["name"])
        seen.add(command["name"])
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


def lvd_problems(article):
    vertices = article.get("lvd_vertices") or []
    file = (article.get("lvd") or "").strip()
    name = article.get("name")
    if "lvd" not in article and not vertices:
        return []
    prefix = "article %s: " % name
    if not article.get("from"):
        return [prefix + "lvd needs from = \"fighter/weapon\""]
    if not file:
        return [prefix + "[[article.lvd_vertex]] needs lvd = \"file.lvd\" on its article"]
    if any("vertex" not in vertex for vertex in vertices):
        return [prefix + "every [[article.lvd_vertex]] needs vertex"]
    if "/" in file or "\\" in file or not file.lower().endswith(".lvd") or len(file) <= 4:
        return [prefix + "lvd = \"%s\" must be a file name in the article's model folder, "
                         "like \"platform.lvd\"" % file]
    if not vertices:
        return [prefix + "lvd %s needs at least one lvd_vertex tying a vertex to a joint" % file]
    if len(vertices) > MAX_LVD_VERTICES:
        return [prefix + "lvd %s: at most %d lvd_vertex entries" % (file, MAX_LVD_VERTICES)]
    seen = set()
    for vertex in vertices:
        index = vertex["vertex"]
        if index < 0 or index > MAX_LVD_VERTEX_INDEX:
            return [prefix + "lvd %s: vertex %d is above %d" % (file, index, MAX_LVD_VERTEX_INDEX)]
        joint = (vertex.get("joint") or "").strip()
        if not joint or ("joint_left" in vertex and not vertex["joint_left"].strip()):
            return [prefix + "lvd %s: vertex %d needs a joint" % (file, index)]
        if index in seen:
            return [prefix + "lvd %s: vertex %d is listed twice" % (file, index)]
        seen.add(index)
    return []


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
