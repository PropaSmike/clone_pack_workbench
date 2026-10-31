#!/usr/bin/env python3
"""The manifest tables behind the table panels: their donors, key orders, checks and TOML text."""

from __future__ import annotations

import re
import sys
from pathlib import Path

HUD_DONORS = ("jack", "cloud", "inkling", "brave", "littlemac", "shulk", "reflet", "pickel",
              "trail", "dolly", "demon")
TETHER_DONORS = ("samus", "samusd", "younglink", "toonlink", "szerosuit", "lucas", "luigi")
GLIDE_PRESETS = ("META_KNIGHT", "PIT", "CHARIZARD")
GRAB_STATUSES = ("SPECIAL_N", "SPECIAL_S", "SPECIAL_HI", "SPECIAL_LW", "ATTACK", "ATTACK_DASH",
                 "ATTACK_S3", "ATTACK_HI3", "ATTACK_LW3", "ATTACK_S4", "ATTACK_HI4", "ATTACK_LW4",
                 "ATTACK_AIR", "CATCH", "CATCH_PULL", "CATCH_DASH", "CATCH_DASH_PULL", "CATCH_TURN",
                 "CATCH_WAIT", "THROW")
OWN_STATUSES = ("own 0", "own 1", "own 2", "own 3")
VICTIM_STATUSES = ("CAPTURE_PULLED", "CAPTURE_WAIT", "CATCHED_GANON", "CATCHED_AIR_GANON",
                   "CLUNG_GANON", "CLUNG_CAPTAIN", "KOOPA_DIVED", "SHOULDERED_DONKEY_START", "SWALLOWED",
                   "BITTEN_WARIO_START", "CLUNG_DIDDY", "CAPTURE_YOSHI", "CATCHED_REFLET",
                   "CATCHED_RIDLEY", "MIIFIGHTER_SUPLEX_AIR_CAPTURED", "CAPTURE_JACK_WIRE",
                   "DOLLY_SUPER_SPECIAL2_CAPTURE", "CAPTURE_MASTER_SWORD", "DEMON_DIVED")
HURTBOX_CHOICES = {
    "part": ("body", "etc", "legs", "body_legs", "head"),
    "height": ("low", "center", "high"),
    "status": ("normal", "invincible", "xlu", "off"),
    "shape": ("sphere", "aabb", "capsule"),
}
HURTBOX_NUMBERS = {key: {name: index for index, name in enumerate(names)}
                   for key, names in HURTBOX_CHOICES.items()}

ORDERS = {
    "grab": ("status", "victim", "then", "node", "offset", "catch"),
    "global_motion": ("name", "template", "animation", "victim"),
    "kirby_motion": ("name", "animation", "template", "scripts", "game", "sound", "effect", "expression",
                     "flags", "loop", "blend_frames", "cancel_frame", "xlu", "no_stop_intp", "animation_unk",
                     "no_extra"),
    "kirby_mesh": ("name", "visible"),
    "hurtbox": ("node", "size", "offset", "offset2", "part", "height", "status", "shape"),
    "lvd_vertex": ("vertex", "joint", "offset", "joint_left"),
    "tether_box": ("p1", "p2"),
    "ladder": ("x", "y", "height", "width"),
    "barrel": ("x", "y", "model", "rotation", "rotation_max", "rotation_speed", "always_rotate",
               "full_rotate", "auto_fire", "fire_rotation", "fire_delay", "speed", "decrease", "gravity",
               "fall_speed", "width", "height", "path", "path_speed"),
    "spring": ("x", "y", "model", "rotation", "speed", "width", "height", "offset_x", "offset_y",
               "launch_frame", "joint"),
    "door": ("x", "y", "width", "height", "offset_x", "offset_y", "air", "player"),
    "mode": ("id", "name", "description", "runs_as", "scene", "skip", "after_battle", "script", "button",
             "order"),
    "sequence": ("id", "code", "runs_as", "scene", "skip", "after_battle"),
    "layout": ("scene", "file", "over_side_panel", "under_movies"),
    "preload": ("after", "files"),
    "patch": ("module", "script", "root"),
    "mii_hat": ("id", "base", "model_type", "hair_model_types", "owned", "disp_order", "swing", "is_patch"),
    "mii_outfit": ("id", "fighter", "base", "gender", "name", "owned", "disp_order", "swing", "is_patch"),
}
REQUIRED = {
    "grab": ("status",),
    "global_motion": ("name",),
    "kirby_motion": ("name", "animation"),
    "kirby_mesh": ("name",),
    "hurtbox": ("node", "size"),
    "lvd_vertex": ("vertex", "joint"),
    "tether_box": ("p1", "p2"),
}
HEADERS = {
    "grab": "[[grab]]",
    "global_motion": "[[global_motion]]",
    "kirby_motion": "[[kirby.motion]]",
    "kirby_mesh": "[[kirby.mesh]]",
    "hurtbox": "[[article.hurtbox]]",
    "lvd_vertex": "[[article.lvd_vertex]]",
    "tether_box": "[[tether.box]]",
}
STAGE_TABLES = ("ladder", "barrel", "spring", "door")
MENU_TABLES = ("mode", "sequence", "layout", "preload", "patch")
MII_TABLES = ("mii_hat", "mii_outfit")
for _table in STAGE_TABLES + MENU_TABLES + MII_TABLES:
    HEADERS[_table] = "[[%s]]" % _table
PLAIN_KEYS = ("article", "file", "key", "value")
TEXT_KINDS = ("str", "text")
LIST_KINDS = ("vec2", "vec3", "numbers")
TEXT_LIST_KINDS = ("texts",)
NAMED_KINDS = ("status", "part", "height", "hit_status", "shape", "mode")

TETHER = {
    "samus": {"articles": ("samus/gbeam",), "lasso": ("gbeam", None, 1), "joint": "gbeam27"},
    "samusd": {"articles": ("samusd/gbeam",), "lasso": ("gbeam", None, 1), "joint": "gbeam27"},
    "younglink": {"articles": ("younglink/hookshot", "younglink/hookshothand"),
                  "lasso": ("hookshot", "hookshothand", 1), "joint": "hookshot22"},
    "toonlink": {"articles": ("toonlink/hookshot", "toonlink/hookshothand"),
                 "lasso": ("hookshot", "hookshothand", 1), "joint": "hookshot22"},
    "szerosuit": {"articles": ("szerosuit/whip2",), "lasso": ("whip2", None, 1), "joint": "plasmawhip9"},
    "lucas": {"articles": ("lucas/himohebi", "lucas/himohebi2"), "lasso": ("himohebi2", None, 1),
              "joint": "joint8"},
    "luigi": {"articles": ("luigi/obakyumu", "luigi/plunger"), "lasso": (None, None, 0), "joint": None},
}
TETHER_EXTRAS = {
    "samus": "its reach end names the beam's status before status_end_AirLassoReach",
    "samusd": "its reach end names the beam's status before status_end_AirLassoReach",
    "younglink": "its reach spawns the hookshot pair again when it is gone",
    "toonlink": "its reach spawns the hookshot pair again when it is gone",
    "szerosuit": "air_catch and air_catch_hit lay material motions over the whip",
    "lucas": "its reach end names the rope's status; it flips when hanging facing left and plays "
             "the snake backwards on landing; air_catch_pose aims the rope",
    "luigi": "it never hangs, and its landing sets itself up",
}

HUD_CALLS = {
    "jack": ("Hud::Gauge(0.5) // the Rebellion gauge, 0 empty to 1 full",),
    "cloud": ("Hud::Gauge(0.5) // the Limit gauge, charged at 1",),
    "inkling": ("Hud::Gauge(0.5) // the ink tank, 0 empty to 1 full",),
    "littlemac": ("Hud::Gauge(0.5) // the KO meter, KO at 1",),
    "brave": ("Hud::Gauge(0.5) // the MP bar, 1 is 100 MP",
              "Hud::MenuOpen([MenuCommand::new(2, 8.0), MenuCommand::new(14, 8.0), "
              "MenuCommand::new(5, 37.0).unusable(), MenuCommand::new(1, 7.0)]) // command, MP cost",
              "Hud::MenuCursor(0) // the row the cursor is on, from 0",
              "Hud::MenuDecide(0) // the row picked",
              "Hud::MenuClose"),
    "shulk": ("Hud::Select(0) // the art: 0 Jump, 1 Speed, 2 Shield, 3 Buster, 4 Smash",
              "Hud::Gauge(0.5) // the art's timer, hidden at 0 and 1"),
    "reflet": ("Hud::Slot(0, 0.5) // a tome and its uses left: 0 Levin Sword, 1 Elwind, 2 Thunder, "
               "3 Arcfire, 4 Nosferatu",),
    "pickel": ("Hud::Slot(0, 12.0) // a material and its count: 0 dirt, 1 wood, 2 stone, 3 iron, "
               "4 gold, 5 redstone, 6 diamond",),
    "trail": ("Hud::Select(0) // the spell: 0 Firaga, 1 Blizzaga, 2 Thundaga",),
    "dolly": ("Hud::State(true) // GO!",),
    "demon": ("Hud::State(true) // Rage",),
}
LAYOUT_CALLS = (
    'Hud::Play("animation") // play one of the layout\'s animations',
    'Hud::Frame("animation", 30.0) // hold one at a frame',
    'Hud::Show("part", false) // hide or show a part',
    'Hud::Text("part", "12") // set a text box',
)


def _tool(name: str):
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        return __import__(name)
    except ImportError:
        return None


def _manifest():
    return _tool("fighter_manifest")


def schema(table: str) -> dict:
    if table in STAGE_TABLES:
        stage = _tool("lint_stage_pack")
        return dict(stage.GIMMICK_KEYS[table]) if stage is not None else {}
    if table in MENU_TABLES:
        menu = _tool("lint_menu_pack")
        return dict(menu.KEYS[table]) if menu is not None else {}
    if table in MII_TABLES:
        mii = _tool("lint_mii_pack")
        return dict(mii.KEYS[table]) if mii is not None else {}
    manifest = _manifest()
    if manifest is None:
        return {}
    return {"grab": manifest.GRAB_KEYS, "global_motion": manifest.MOTION_KEYS,
            "kirby_motion": {key: kind for key, kind in manifest.MOTION_KEYS.items() if key != "victim"},
            "kirby_mesh": manifest.MESH_KEYS,
            "hurtbox": manifest.HURTBOX_KEYS, "lvd_vertex": manifest.LVD_VERTEX_KEYS,
            "tether_box": manifest.TETHER_BOX_KEYS}.get(table, {})


def is_plain(table: str, key: str) -> bool:
    """A key the panel keeps as typed, outside any TOML table of its own."""
    return key in PLAIN_KEYS and table not in STAGE_TABLES + MENU_TABLES + MII_TABLES


def to_toml(table: str, key: str, text: str) -> str:
    """What the panel shows for one key, as fighter.toml writes it."""
    text = text.strip()
    kind = schema(table).get(key, "str")
    if kind in TEXT_KINDS:
        return text if text.startswith('"') else '"%s"' % text
    if kind in LIST_KINDS and not text.startswith("["):
        return "[%s]" % text
    if kind in TEXT_LIST_KINDS and not text.startswith("["):
        items = [item.strip() for item in text.split(",") if item.strip()]
        return "[%s]" % ", ".join(item if item.startswith('"') else '"%s"' % item for item in items)
    if kind in NAMED_KINDS:
        try:
            int(text, 0)
            return text
        except ValueError:
            return text if text.startswith('"') else '"%s"' % text
    return text


def display(text: str) -> str:
    """One TOML value as the panel shows it: no quotes or brackets."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        items = [item.strip() for item in text[1:-1].split(",")]
        return ", ".join(item[1:-1] if len(item) >= 2 and item[0] == item[-1] == '"' else item
                         for item in items if item)
    return text


def row_problem(table: str, row: dict) -> str:
    """What the manifest would refuse in this row, from the engine's own rules."""
    if table in STAGE_TABLES:
        stage = _tool("lint_stage_pack")
        return stage.gimmick_problem(table, row) if stage is not None else ""
    if table in MENU_TABLES:
        menu = _tool("lint_menu_pack")
        return menu.block_problem(table, row) if menu is not None else ""
    if table in MII_TABLES:
        mii = _tool("lint_mii_pack")
        return mii.block_problem(table, row) if mii is not None else ""
    manifest = _manifest()
    if manifest is None:
        return ""
    if table == "partner":
        try:
            manifest.partner_param(row.get("key", ""), row.get("value", ""), 0)
        except manifest.ManifestError as problem:
            return problem.message
        return ""
    keys = schema(table)
    for key in REQUIRED.get(table, ()):
        if not row.get(key):
            return "%s needs %s" % (HEADERS[table], key)
    for key, text in row.items():
        if key in PLAIN_KEYS:
            continue
        if key not in keys:
            return "%s has no key %s" % (HEADERS[table], key)
        try:
            manifest.parse_scalar(text, keys[key], 0, key)
        except manifest.ManifestError as problem:
            return problem.message
    return ""


def single_problem(table: str, key: str, value: str) -> str:
    """What fighter.toml would refuse in [hud] or [tether]."""
    manifest = _manifest()
    if manifest is None or not value:
        return ""
    if table == "hud" and key == "from" and value not in manifest.HUD_DONORS:
        return 'hud from "%s" is not a HUD the engine drives' % value
    if table == "hud" and key == "layout" and not (
            value.endswith(".arc") and not value.startswith("/") and "//" not in value
            and set(value) <= manifest.HUD_LAYOUT_BYTES):
        return 'hud layout "%s" must be a lowercase arc path ending in .arc' % value
    if table == "tether" and value not in manifest.TETHER_DONORS:
        return 'tether from "%s" has no tether' % value
    return ""


def table_lines(table: str, row: dict) -> list[str]:
    """One row as a fighter.toml table: its keys in the engine's order, then the rest."""
    order = ORDERS.get(table, ())
    keys = [key for key in order if key in row] + [key for key in row if key not in order
                                                   and not is_plain(table, key)]
    return ["", HEADERS[table]] + ["%s = %s" % (key, row[key]) for key in keys]


def family_names(state: dict) -> list[str]:
    """The family members a part lists, its own resource name first, each once."""
    text = state.get("family_members") or state.get("members") or ""
    if isinstance(text, (list, tuple)):
        text = ",".join(str(name) for name in text)
    names = [name.strip().strip('"') for name in str(text).strip("[]").split(",") if name.strip().strip('"')]
    if not names:
        return []
    resource = state.get("resource_name") or names[0]
    return [resource] + [name for name in dict.fromkeys(names) if name != resource]


def member_names(resource: str, members: list[str]) -> list[str]:
    """Resource names for a clone of a family: the clone's own name, then its name with each
    member's part past the owner's (galleommissile -> <name>_missile)."""
    owner = members[0]
    names = [resource]
    for member in members[1:]:
        tail = member[len(owner):] if member.startswith(owner) and len(member) > len(owner) else member
        names.append("%s_%s" % (resource, tail.strip("_")))
    return names


def numbers(text: str) -> list[float]:
    """The numbers in a TOML value, for the Rust tab."""
    return [float(part) for part in re.findall(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?", text or "")]


def named_number(key: str, text: str) -> tuple[int, str] | None:
    """A hurtbox part, height, status or shape as the number its builder call takes, and its name."""
    value = display(text)
    try:
        number = int(value, 0)
    except ValueError:
        names = HURTBOX_NUMBERS.get(key, {})
        bare = value.lower()
        for prefix in ("collision_part_", "hit_height_", "hit_status_", "collision_shape_type_"):
            if bare.startswith(prefix):
                bare = bare[len(prefix):]
        if bare not in names:
            return None
        return names[bare], bare
    names = HURTBOX_CHOICES.get(key, ())
    return number, names[number] if 0 <= number < len(names) else str(number)


def tether_articles(donor: str) -> tuple[str, ...]:
    return TETHER.get(donor, {}).get("articles", ())


def partner_param_names() -> list[str]:
    manifest = _manifest()
    return sorted(manifest.PARTNER_PARAMS) if manifest is not None else ["nana_delay", "nana_opt_dst"]
