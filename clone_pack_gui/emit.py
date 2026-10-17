#!/usr/bin/env python3
"""Turn the panels' fields into the Rust a pack's plugin compiles."""

from __future__ import annotations

import re

from . import gimmicks


def identifier(name: str) -> str:
    return "".join(character if character.isalnum() else "_"
                   for character in name).strip("_").upper() or "CLONE"


def suffix(state: dict) -> str:
    """What a pack with several parts of one kind appends to each function name."""
    return "_" + identifier(state.get("resource_name") or state.get("place") or "").lower()


DIRECT_READER_TABLES = ("fighter_param", "param_motion", "common", "param_thrown")


def split_rules(state: dict):
    """(engine rules, ParamConfig rules). The four tables the game also reads
    without the param getters are the engine's; every vl.prc param is
    ParamConfig's, the way a one-slot mod already registers it."""
    engine, config = [], []
    for rule in state.get("params") or []:
        (engine if rule.get("table", "fighter_param") in DIRECT_READER_TABLES else config).append(rule)
    return engine, config


def toml_key(rule: dict) -> str:
    table = rule.get("table", "fighter_param")
    field = rule.get("field", "")
    if table == "fighter_param" or not field:
        return field or table
    return "%s.%s" % (table, field)


def engine_param_lines(state: dict) -> list[str]:
    """The [params] and [params.mul] tables fighter.toml carries. With a plugin
    that does its own CSS and params (own_css), only the rules ParamConfig
    cannot reach; without one, every rule, and the engine applies them all."""
    engine, config = split_rules(state)
    if not state.get("own_css"):
        engine = engine + config
    if not engine:
        return []
    sets = [rule for rule in engine if rule.get("op", "Set") != "Mul"]
    muls = [rule for rule in engine if rule.get("op", "Set") == "Mul"]
    lines = []
    if sets:
        lines += ["", "[params]"]
        for rule in sets:
            value = str(rule.get("value", "0")).strip() if rule.get("integer") else float_literal(rule.get("value", "0"))
            lines.append("%s = %s" % (toml_key(rule), value))
    if muls:
        lines += ["", "[params.mul]"]
        for rule in muls:
            lines.append("%s = %s" % (toml_key(rule), float_literal(rule.get("value", "1"))))
    return lines


def costumes_constant(state: dict) -> str:
    """`WAWA_COSTUMES`: one constant drives the manifest, the CSK maps and the
    ParamConfig slots, so a pack with 6 or 12 costumes changes one line."""
    return "%s_COSTUMES" % identifier(state.get("resource_name", "wawa"))


def css_registration(state: dict, suffix: str = "") -> str:
    """The CSS row through CSK's own API, the code a one-slot mod already has:
    only fighter_kind, fighter_kind_corps and ui_chara_id change, to the
    clone's names. The manifest says own_css() so the engine writes no row of
    its own. Costume maps and layouts run over the COSTUMES constant; the base
    has eight layouts, so a costume past c07 clones layout `color % 8`. The row
    copies the base's (World of Light lists only copied rows) and every value is
    Overwrite, since an Optional value never replaces a copied one."""
    resource = state.get("resource_name", "wawa")
    base = state.get("base_resource_name", "mario")
    kind_name = state.get("fighter_kind_name") or "fighter_kind_%s" % resource
    ui_chara = state.get("ui_chara") or "ui_chara_%s" % resource
    name_id = state.get("display_name") or resource
    narration = state.get("narration") or "vc_narration_characall_%s" % base
    costumes = costumes_constant(state)
    start = int(state.get("color_start", 0) or 0)
    order = state.get("disp_order")
    q = '"'
    lines = [
        "pub fn register_css_entry%s() {" % suffix,
        "    let ui_chara = hash40(%s%s%s); // the clone's UI id: ui_chara_<name>" % (q, ui_chara, q),
        "    let mut indices = HashMap::new();",
        "    let mut hashes = HashMap::new();",
        "    for color in %s { // one set per costume the pack ships" % costume_range(start, costumes),
        "        indices.insert(hash40(&format!(%sc{color:02}_index%s)), UnsignedByteType::Overwrite(color)); // costume index" % (q, q),
        "        indices.insert(hash40(&format!(%sn{color:02}_index%s)), UnsignedByteType::Overwrite(color)); // name index" % (q, q),
        "        indices.insert(hash40(&format!(%sc{color:02}_group%s)), UnsignedByteType::Overwrite(0)); // costume group" % (q, q),
        "        hashes.insert(hash40(&format!(%scharacall_label_c{color:02}%s)), Hash40Type::Overwrite(hash40(%s%s%s))); // announcer call" % (q, q, q, narration, q),
        "        hashes.insert(hash40(&format!(%scharacall_label_article_c{color:02}%s)), Hash40Type::Overwrite(0));" % (q, q),
        "    }",
        "    indices.insert(hash40(%scolor_start_index%s), UnsignedByteType::Overwrite(%d)); // first costume" % (q, q, start),
        "    hashes.insert(hash40(%soriginal_ui_chara_hash%s), Hash40Type::Overwrite(hash40(%sui_chara_%s%s))); // the base's UI id" % (q, q, q, base, q),
        "",
        "    allow_ui_chara_hash_online(ui_chara); // let the entry be picked online",
        "    add_chara_db_entry_info(CharacterDatabaseEntry {",
        "        ui_chara_id: ui_chara,                                        // the clone's UI id",
        "        clone_from_ui_chara_id: Some(hash40(%sui_chara_%s%s)), // copy every other field from the base's entry; World of Light lists only copied rows" % (q, base, q),
        "        name_id: StringType::Overwrite(CStrCSK::new(%s%s%s)), // suffix of the nam_chr*_00_<x> labels in msg_name.xmsbt" % (q, name_id, q),
        "        fighter_kind: Hash40Type::Overwrite(hash40(%s%s%s)), // the clone's identity: fighter_kind_<name>" % (q, kind_name, q),
        "        fighter_kind_corps: Hash40Type::Overwrite(hash40(%s%s%s)), // same" % (q, kind_name, q),
    ]
    if state.get("series"):
        series = state["series"]
        if not series.startswith("ui_series_"):
            series = "ui_series_" + series
        lines.append("        ui_series_id: Hash40Type::Overwrite(hash40(%s%s%s)), // series icon" % (q, series, q))
    if isinstance(order, int):
        lines.append("        disp_order: SignedByteType::Overwrite(%d), // position on the select screen; Overwrite, an Optional keeps the base's" % order)
    if isinstance(state.get("exhibit_year"), int):
        lines.append("        exhibit_year: ShortType::Overwrite(%d), // the year the select entry shows" % state["exhibit_year"])
    save_no = state["save_no"] if isinstance(state.get("save_no"), int) else 0
    lines += [
        "        color_num: UnsignedByteType::Overwrite(%s), // number of costumes" % costumes,
        "        shop_item_tag: Hash40Type::Overwrite(hash40(%s-1%s)), // the base's DLC fields hide the entry; clear them" % (q, q),
        "        alt_chara_id: Hash40Type::Overwrite(hash40(%s-1%s))," % (q, q),
        "        save_no: SignedByteType::Overwrite(%d), // the select entry's save slot" % save_no,
        "        is_dlc: BoolType::Overwrite(false),",
        "        is_patch: BoolType::Overwrite(false),",
        "        extra_index_maps: UnsignedByteMap::Overwrite(indices),",
        "        extra_hash_maps: Hash40Map::Overwrite(hashes),",
        "        ..Default::default()",
        "    });",
        "    for color in %s { // one layout per costume; the base has eight, so wrap" % costume_range(start, costumes),
        "        add_chara_layout_db_entry_info(CharacterLayoutDatabaseEntry {",
        "            ui_layout_id: hash40(&format!(%s%s_{color:02}%s)), // ui_chara_<name>_<costume>" % (q, ui_chara, q),
        "            clone_from_ui_layout_id: Some(hash40(&format!(%sui_chara_%s_{:02}%s, color %% 8))), // the base's layout" % (q, base, q),
        "            ui_chara_id: Hash40Type::Overwrite(ui_chara),",
        "            chara_color: UnsignedByteType::Overwrite(color), // the costume",
        "            ..Default::default()",
        "        });",
        "    }",
        "}",
    ]
    return "\n".join(lines) + "\n"


def param_config_calls(state: dict, suffix: str = "") -> str:
    """param_config::update_* for every vl.prc rule, ParamConfig's own syntax
    with the clone's kind where a one-slot mod had the base's."""
    _, rules = split_rules(state)
    if not rules:
        return ""
    start = int(state.get("color_start", 0) or 0)
    costumes = costumes_constant(state)
    q = '"'
    lines = [
        "pub fn register_params%s(kind: i32) { // kind: the clone's, from register" % suffix,
        "    let slots: Vec<i32> = (%s as i32).collect(); // costumes the values apply to; vec![-1] is all" % costume_range(start, costumes),
        "    // (kind, costumes, (param table, field), value); a top-level field has 0 as its second hash",
    ]
    for rule in rules:
        table = rule.get("table", "")
        field = rule.get("field", "")
        value = rule.get("value", "0")
        second = "hash40(%s%s%s)" % (q, field, q) if field else "0"
        key = "(hash40(%s%s%s), %s)" % (q, table, q, second)
        if rule.get("integer"):
            lines.append("    param_config::update_int(kind, slots.clone(), %s, %s);"
                         % (key, str(value).strip()))
        elif rule.get("op", "Set") == "Mul":
            lines.append("    param_config::update_attribute_mul(kind, slots.clone(), %s, %s);"
                         % (key, float_literal(value)))
        else:
            lines.append("    param_config::update_float(kind, slots.clone(), %s, %s);"
                         % (key, float_literal(value)))
    lines.append("}")
    return "\n".join(lines) + "\n"


def reported(call: str, tag: str, what: str) -> list[str]:
    """A call whose Err is printed rather than dropped: an engine older than the
    call returns EngineUnavailable, and a refused value says why in its own line."""
    return ["    if let Err(error) = %s {" % call,
            "        skyline::println!(\"[%s] %s was not applied: {error:?}\");"
            % (tag, what),
            "    }"]


def item_label_calls(state: dict, suffix: str = "") -> str:
    """item_common_set_label and _hash for the fields of a clone item's common
    row that item.toml cannot carry; the floats and ints are the file's."""
    rules = [rule for rule in (state.get("item_params") or [])
             if rule.get("style") in ("label", "hash")]
    if not rules:
        return ""
    tag = state.get("resource_name") or "pack"
    lines = ["pub fn register_item_labels%s(kind: i32) {" % suffix]
    for rule in rules:
        field = rule.get("field", "")
        value = rule.get("value", "0")
        call = ("clone_engine_api::item_common_set_%s("
                "kind, smash::hash40(\"%s\"), smash::hash40(\"%s\"))"
                % (rule["style"], field, value))
        lines += reported(call, tag, field)
    lines.append("}")
    return "\n".join(lines) + "\n"


def item_table_lines(state: dict) -> list[str]:
    """The [common] and [owner_params] tables item.toml carries for the values
    the Parameters tab holds: float and int fields by name, owner words by
    fighter and field. Labels and hashes stay in the Rust tab."""
    lines: list[str] = []
    common = [rule for rule in (state.get("item_params") or [])
              if rule.get("field") and rule.get("style", "float") in ("float", "int")]
    if common:
        lines += ["", "[common]"]
        for rule in common:
            value = rule.get("value", "0")
            if rule.get("style") == "int":
                lines.append("%-13s = %s" % (rule["field"], int(float(value))))
            else:
                lines.append("%-13s = %s" % (rule["field"], float_literal(value)))
    owners = [rule for rule in (state.get("owner_params") or [])
              if rule.get("owner") and rule.get("field")]
    if owners:
        lines += ["", "[owner_params]"]
        for rule in owners:
            value = rule.get("value", "0")
            shown = int(float(value)) if rule.get("integer") else float_literal(value)
            lines.append("%-13s = %s" % ("%s.%s" % (rule["owner"], rule["field"].split("/")[-1]),
                                         shown))
    return lines


def end_statement(line: str) -> str:
    """The `;` of a builder chain goes before the line's comment, not after it."""
    code, marker, comment = line.partition(" //")
    return code + ";" + (marker + comment if marker else "")


def costume_range(start: int, costumes: str) -> str:
    """`0..WAWA_COSTUMES`, or `2..2 + WAWA_COSTUMES` for a pack starting past c00."""
    return "%d..%s" % (start, costumes) if start == 0 else "%d..%d + %s" % (start, start, costumes)


PARAM_NOTES = {
    "fighter_param": "fighter_param.prc field, read past ParamConfig",
    "param_motion": "fighter_param_motion.prc field, read past ParamConfig",
    "common": "fighter/common/param/ field, read past ParamConfig",
    "param_thrown": "throw hold position",
}


def manifest_param_calls(rules: list[dict]) -> list[str]:
    """`.param(..)`, `.param_int(..)`, `.param_mul(..)` on the manifest, one per rule."""
    q = '"'
    out = []
    for rule in rules:
        key = toml_key(rule)
        value = rule.get("value", "0")
        note = PARAM_NOTES.get(rule.get("table", "fighter_param"), "vl.prc value, pushed to ParamConfig")
        if rule.get("integer"):
            out.append("    .param_int(%s%s%s, %s) // %s, integer" % (q, key, q, str(value).strip(), note))
        elif rule.get("op", "Set") == "Mul":
            out.append("    .param_mul(%s%s%s, %s) // %s, multiplied" % (q, key, q, float_literal(value), note))
        else:
            out.append("    .param(%s%s%s, %s) // %s" % (q, key, q, float_literal(value), note))
    return out


def fighter_manifest_lines(state: dict, constant: str) -> list[str]:
    """The Manifest in main: the same declaration fighter.toml carries, so a
    pack with a plugin registers from code. With the plugin flag (own_css) the
    select entry and the vl.prc values stay CSK's and ParamConfig's calls;
    without it the manifest carries them all and the engine publishes the
    entry."""
    from .packs import weapon_short_name
    resource = state.get("resource_name", "wawa")
    base = state.get("base_resource_name") or state.get("base_fighter") or "mario"
    own = bool(state.get("own_css"))
    q = '"'
    costumes = costumes_constant(state)
    lines = [
        "    let manifest = Manifest::new(",
        "        %s%s%s, // name: folder under fighter/, Smashline agent name, identity" % (q, resource, q),
        "        %s%s%s, // base: the vanilla fighter it is built on" % (q, base, q),
        "    )",
        "    .costumes(%s as u32) // the costume count" % costumes,
    ]
    start = state.get("color_start")
    if isinstance(start, int) and start > 0:
        lines.append("    .color_start(%d) // first costume" % start)
    if own:
        lines.append("    .own_css() // register_css_entry below publishes the select entry")
    else:
        if state.get("display_name"):
            lines.append("    .name_label(%s%s%s) // suffix of the nam_chr*_00_<x> labels" % (q, state["display_name"], q))
        if state.get("series"):
            lines.append("    .series(%s%s%s) // series icon" % (q, state["series"], q))
        if isinstance(state.get("disp_order"), int):
            lines.append("    .disp_order(%d) // position on the select screen" % state["disp_order"])
        if state.get("narration"):
            lines.append("    .narration(%s%s%s) // announcer call" % (q, state["narration"], q))
        if isinstance(state.get("save_no"), int):
            lines.append("    .save_no(%d) // the select entry's save slot" % state["save_no"])
        if isinstance(state.get("exhibit_year"), int):
            lines.append("    .exhibit_year(%d) // the year the select entry shows" % state["exhibit_year"])
    for key in ("ui_chara", "fighter_kind_name"):
        if state.get(key):
            lines.append("    .%s(%s%s%s) // overrides the name derived from name" % (key, q, state[key], q))
    if state.get("staffroll"):
        lines.append("    .staffroll() // the pack's credits picture")
    if state.get("jingle"):
        lines.append("    .jingle(%s%s%s) // victory theme; accepted, not served yet" % (q, state["jingle"], q))
    if state.get("owns_param_resources"):
        lines.append("    .owns_param_resources() // the pack ships the whole camera and CPU param trees")
    for article in state.get("articles") or []:
        name, owner, weapon = article.get("name"), article.get("owner"), article.get("weapon")
        if not (name and owner and weapon):
            continue
        source = "%s/%s" % (owner, weapon_short_name(owner, weapon))
        if article.get("kirby_copy"):
            lines.append("    .kirby_article(%s%s%s, %s%s%s) // article for Kirby's copy, from that vanilla weapon" % (q, name, q, q, source, q))
        else:
            lines.append("    .article(%s%s%s, %s%s%s) // fighter/%s/model/%s, copied from that vanilla weapon" % (q, name, q, q, source, q, resource, name))
    for article in state.get("base_articles") or []:
        if article.get("name") and article.get("base_article"):
            lines.append("    .base_article(%s%s%s, %s%s%s) // renames the base's own article into fighter/%s/model/%s"
                         % (q, article["name"], q, q, article["base_article"], q, resource, article["name"]))
    statuses = state.get("kirby_statuses")
    if isinstance(statuses, int) and statuses > 0:
        lines.append("    .kirby(%d) // status numbers reserved for Kirby's copy" % statuses)
    if isinstance(state.get("kirby_first"), int):
        lines.append("    .kirby_first(%#x) // the first of those numbers, pinned" % state["kirby_first"])
    if state.get("kirby_copy_full_model"):
        lines.append("    .kirby_full_model() // Kirby gets the whole body, not a hat")
    if state.get("kirby_model"):
        lines.append("    .kirby_model(%s%s%s) // an extra model folder under fighter/kirby/model/" % (q, state["kirby_model"], q))
    tables = (state.get("kirby_tables") or "").strip()
    if tables:
        fence = raw_fence(tables)
        lines.append("    .raw(r%s\"" % fence)
        lines += tables.splitlines()
        lines.append("\"%s) // Kirby's copy motions and meshes, as fighter.toml carries them" % fence)
    lines += article_gimmick_calls(state)
    engine, config = split_rules(state)
    rules = engine if own else engine + config
    if rules:
        lines += manifest_param_calls(rules)
    lines[-1] = end_statement(lines[-1])
    if "global_motions" in state:
        lines += guarded_tables(row_tables("global_motion", state.get("global_motions")), "CAP_GLOBAL_MOTIONS",
                                "motions added to every fighter's motion list")
    else:
        lines += guarded_tables(state.get("global_motion_tables"), "CAP_GLOBAL_MOTIONS",
                                "motions added to every fighter's motion list")
    if "grabs" in state:
        lines += guarded_tables(row_tables("grab", state.get("grabs")), "CAP_GRAB_RULES",
                                "command grabs the engine accepts")
    else:
        lines += guarded_tables(state.get("grab_tables"), "CAP_GRAB_RULES",
                                "command grabs the engine accepts")
    if "hud" in state:
        lines += hud_manifest_lines(state)
    else:
        lines += guarded_tables(state.get("hud_tables"), "CAP_HUD",
                                "the fighter's HUD, borrowed or its own layout")
    lines += guarded_tables(state.get("final_tables"), "CAP_FINAL_SMASH",
                            "the Final Smash borrowed from another fighter")
    if "tether" in state:
        lines += tether_manifest_lines(state)
    else:
        lines += guarded_tables(state.get("tether_tables"), "CAP_TETHER",
                                "the tether borrowed from another fighter and its ledge reach")
    lines += command_lines(state)
    lines += entry_group_lines(state)
    lines += [
        "    let Ok(kind) = %s.register(manifest) else {" % constant,
        "        return; // the fault is in the log",
        "    };",
        "    skyline::println!(\"[%s] registered as fighter kind {kind}\");" % resource,
    ]
    return lines


COMMAND_SETTING_NOTES = (
    ("special_command_life_max", "frames between two directions"),
    ("super_special_command_life_max", "the same for super commands"),
    ("special_command_ab_button_life", "frames a button press counts"),
    ("special_command_neutral_threshold", "stick distance that reads as neutral"),
)


def stick_range_literal(text) -> str | None:
    """special_command_stick_range as a Rust array of seven [min, max] pairs."""
    numbers = re.findall(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?", str(text))
    if len(numbers) != 14:
        return None
    pairs = ["[%s, %s]" % (float_literal(numbers[i]), float_literal(numbers[i + 1]))
             for i in range(0, 14, 2)]
    return "[%s]" % ", ".join(pairs)


def command_call(command: dict) -> str:
    q = '"'
    call = "Command::new(%s%s%s, %s%s%s)" % (q, command.get("name", ""), q, q, command.get("input", ""), q)
    button = command.get("button", "either")
    if button != "either":
        call += ".button(Button::%s)" % str(button).capitalize()
    if command.get("super"):
        call += ".super_command()"
    if isinstance(command.get("life"), int):
        call += ".life(%d)" % command["life"]
    if command.get("neutral_resets") is False:
        call += ".neutral_resets(false)"
    if command.get("reverse"):
        call += ".reverse()"
    if command.get("cpu"):
        call += ".cpu(%s)" % float_literal(command["cpu"])
    return call


def command_lines(state: dict) -> list[str]:
    """[commands] and [[command]] as Manifest calls, added only when the engine has them."""
    settings = state.get("command_settings") or {}
    commands = [command for command in state.get("commands") or [] if command.get("name")]
    calls = []
    if settings.get("vanilla"):
        calls.append(".vanilla_commands(true) // the game's own commands, read with get_command_flag_cat")
    for key, note in COMMAND_SETTING_NOTES:
        value = settings.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        literal = float_literal(value) if key == "special_command_neutral_threshold" else str(int(value))
        calls.append(".%s(%s) // %s" % (key, literal, note))
    stick = stick_range_literal(settings.get("special_command_stick_range", ""))
    if stick:
        calls.append(".special_command_stick_range(%s) // up, up-forward, forward, down-forward, "
                     "then the back three, in degrees" % stick)
    for command in commands:
        calls.append(".%s // read with fight::command(fighter, \"%s\")"
                     % ("command(%s)" % command_call(command), command["name"]))
    if not calls:
        return []
    return (["    let manifest = if clone_engine_api::runtime_capabilities() & clone_engine_api::CAP_COMMAND_INPUTS != 0 {",
             "        manifest"]
            + ["            " + call for call in calls]
            + ["    } else {",
               "        manifest // an older engine would refuse the whole manifest",
               "    };"])


def command_uses(state: dict) -> set:
    commands = [command for command in state.get("commands") or [] if command.get("name")]
    if not commands:
        return set()
    if any(command.get("button", "either") != "either" for command in commands):
        return {"use clone_engine_api::fight::{Button, Command};"}
    return {"use clone_engine_api::fight::Command;"}


STATUS_TABLE_OWNERS = {"chrom": "roy", "daisy": "peach", "ken": "ryu", "koopag": "koopa", "lucina": "marth",
                       "nana": "popo", "pichu": "pikachu", "pitb": "pit", "richter": "simon", "samusd": "samus",
                       "toonlink": "link", "wolf": "fox", "younglink": "link"}
STATUS_TABLE_MAX = ("donkey", "koopa", "peach", "pit")
FLOATING_BASES = ("peach", "daisy")
FLOAT_DEFAULTS = (("frames", 150), ("start_y", 1.5), ("water_height", 14.0))
FLOAT_MOTIONS = ("fuwafuwa_start", "fuwafuwa")


def status_total(base: str) -> str:
    """The constant the base's SetStatusScripts sizes its status table with."""
    owner = STATUS_TABLE_OWNERS.get(base, base)
    return "*FIGHTER_%s_STATUS_KIND_%s" % (owner.upper(), "MAX" if owner in STATUS_TABLE_MAX else "NUM")


def float_call(settings: dict) -> str:
    """Float::PEACH with a builder call for each value the panel changed."""
    call = "Float::PEACH"
    for key, default in FLOAT_DEFAULTS:
        value = settings.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value == default:
            continue
        call += ".%s(%s)" % (key, str(int(value)) if key == "frames" else float_literal(value))
    start, hover = settings.get("start_motion") or "", settings.get("motion") or ""
    if (start or hover) and (start, hover) != FLOAT_MOTIONS:
        call += ".motions(%s, %s)" % tuple('smashline::skyline_smash::hash40("%s")' % name for name in
                                          (start or FLOAT_MOTIONS[0], hover or FLOAT_MOTIONS[1]))
    item = settings.get("item")
    if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
        call += ".item(%d)" % item
    return call


def float_lines(state: dict, resource: str) -> list[str]:
    """Peach's float from clone_engine_api::float: its two statuses past the
    base's own, the way in and the aerial that keeps it going."""
    settings = state.get("float") or {}
    if not settings.get("on"):
        return []
    base = state.get("base_resource_name") or state.get("base_fighter") or "mario"
    if base in FLOATING_BASES:
        return ["    // %s floats already: a clone of it keeps the float" % base]
    item = settings.get("item")
    call = float_call(settings)
    note = "Peach's float: jump held in the air, or down and jump on the ground"
    if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
        note += "; down special throws %s mid-float" % (settings.get("item_name") or "item %d" % item)
    return [
        "    let float_status = %s; // %s's status count: the float takes it and the next one, "
        "so number statuses of your own from float_status + 2" % (status_total(base), base),
        '    float::register("%s", %s, float_status); // %s' % (resource, call, note),
        '    Agent::new("%s") // the float, under the clone\'s own name' % resource,
        "        .on_start(float::on_start) // the way in, from the jump checks",
        "        .on_line(Main, float::frame) // one float per airtime, and the jump out of water",
        "        .status(Pre, float_status, float::start_pre)",
        "        .status(Init, float_status, float::start_init)",
        "        .status(Main, float_status, float::start_main)",
        "        .status(End, float_status, float::end)",
        "        .status(Pre, float_status + 1, float::float_pre)",
        "        .status(Main, float_status + 1, float::float_main)",
        "        .status(End, float_status + 1, float::end)",
        "        .status(Pre, *FIGHTER_STATUS_KIND_ATTACK_AIR, float::attack_air_pre) // an aerial "
        "keeps the float going; an aerial status of your own calls these",
        "        .status(Main, *FIGHTER_STATUS_KIND_ATTACK_AIR, float::attack_air_main)",
        "        .install();",
    ]


def row_tables(table: str, rows) -> str:
    """Panel rows as the fighter.toml tables a guarded raw() carries."""
    lines: list[str] = []
    for row in rows or []:
        lines += gimmicks.table_lines(table, row)
    return "\n".join(lines).strip("\n")


def vec_literal(text: str, count: int) -> str | None:
    values = gimmicks.numbers(text)
    if len(values) != count:
        return None
    return ", ".join(float_literal(value) for value in values)


def hurtbox_call(row: dict) -> tuple[str, str]:
    """Hurtbox::new and a builder call for each key the row sets, and the names of its numbers."""
    call = 'Hurtbox::new("%s", %s)' % (gimmicks.display(row.get("node", "")),
                                       float_literal(gimmicks.display(row.get("size", "0"))))
    notes = []
    for key in ("offset", "offset2"):
        literal = vec_literal(row.get(key, ""), 3)
        if literal:
            call += ".%s(%s)" % (key, literal)
    for key in ("part", "height", "status", "shape"):
        found = gimmicks.named_number(key, row[key]) if key in row else None
        if found:
            call += ".%s(%d)" % (key, found[0])
            notes.append("%s %s" % (key, found[1]))
    return call, ", ".join(notes)


def lvd_vertex_parts(row: dict) -> tuple[int, str, str | None, str | None]:
    try:
        vertex = int(gimmicks.display(row.get("vertex", "0")), 0)
    except ValueError:
        vertex = 0
    left = gimmicks.display(row["joint_left"]) if "joint_left" in row else None
    return vertex, gimmicks.display(row.get("joint", "top")), vec_literal(row.get("offset", ""), 3), left


def lvd_expression(file: str, rows) -> tuple[str, bool]:
    """ArticleLvd for one article, and whether it needs LvdVertex for a vertex with both an
    offset and a joint_left."""
    parts = [lvd_vertex_parts(row) for row in rows]
    if not any(offset and left for _, _, offset, left in parts):
        call = 'ArticleLvd::new("%s")' % file
        for vertex, joint, offset, left in parts:
            if offset:
                call += '.vertex_at(%d, "%s", %s)' % (vertex, joint, offset)
            elif left:
                call += '.vertex_facing(%d, "%s", "%s")' % (vertex, joint, left)
            else:
                call += '.vertex(%d, "%s")' % (vertex, joint)
        return call, False
    pushes = []
    for vertex, joint, offset, left in parts:
        expression = 'LvdVertex::new(%d, "%s")' % (vertex, joint)
        if offset:
            expression += ".offset(%s)" % offset
        if left:
            expression += '.joint_left("%s")' % left
        pushes.append("lvd.vertices.push(%s);" % expression)
    return '{ let mut lvd = ArticleLvd::new("%s"); %s lvd }' % (file, " ".join(pushes)), True


def article_gimmick_calls(state: dict) -> list[str]:
    """The articles' hurtboxes and platforms, as Manifest calls."""
    lines = []
    declared = {article.get("name") for article in state.get("articles") or []
                if article.get("owner") and article.get("weapon")}
    for row in state.get("article_hurtboxes") or []:
        if row.get("article") in declared:
            call, notes = hurtbox_call(row)
            lines.append('    .article_hurtbox("%s", %s) // a hurtbox on that article%s'
                         % (row["article"], call, ": " + notes if notes else ""))
    for article in state.get("articles") or []:
        if not (article.get("name") and article.get("lvd")):
            continue
        rows = [row for row in state.get("article_lvd_vertices") or [] if row.get("article") == article["name"]]
        expression, _ = lvd_expression(article["lvd"], rows)
        lines.append('    .article_lvd("%s", %s) // a platform from the article\'s own .lvd'
                     % (article["name"], expression))
    return lines


def article_gimmick_uses(state: dict) -> set:
    uses = set()
    declared = {article.get("name") for article in state.get("articles") or []
                if article.get("owner") and article.get("weapon")}
    if any(row.get("article") in declared for row in state.get("article_hurtboxes") or []):
        uses.add("v2:Hurtbox")
    for article in state.get("articles") or []:
        if article.get("name") and article.get("lvd"):
            uses.add("v2:ArticleLvd")
            rows = [row for row in state.get("article_lvd_vertices") or [] if row.get("article") == article["name"]]
            if lvd_expression(article["lvd"], rows)[1]:
                uses.add("v2:LvdVertex")
    return uses


def guarded_calls(capability: str, calls: list[str]) -> list[str]:
    if not calls:
        return []
    return (["    let manifest = if clone_engine_api::runtime_capabilities() & clone_engine_api::%s != 0 {"
             % capability, "        manifest"]
            + ["            " + call for call in calls]
            + ["    } else {",
               "        manifest // an older engine would refuse the whole manifest",
               "    };"])


def hud_manifest_lines(state: dict) -> list[str]:
    hud = state.get("hud") or {}
    calls = []
    if hud.get("from"):
        calls.append('.hud("%s") // that fighter\'s HUD by this fighter\'s portrait' % hud["from"])
    if hud.get("layout"):
        calls.append('.hud_layout("%s") // the pack\'s own layout on the damage card' % hud["layout"])
    return guarded_calls("CAP_HUD", calls)


def tether_manifest_lines(state: dict) -> list[str]:
    tether = state.get("tether") or {}
    calls = []
    if tether.get("from"):
        calls.append('.tether("%s") // its air_lasso_data and ledge boxes; the tether statuses below '
                     "are blank until you port its own" % tether["from"])
    for row in tether.get("boxes") or []:
        first, second = vec_literal(row.get("p1", ""), 2), vec_literal(row.get("p2", ""), 2)
        if first and second:
            calls.append(".tether_box([%s], [%s]) // a ledge box of your own, two corners from the fighter"
                         % (first, second))
    return guarded_calls("CAP_TETHER", calls)


def blank(name: str, returns: bool, body: list[str]) -> str:
    """A status or line function left for the modder to fill in."""
    signature = "unsafe extern \"C\" fn %s(fighter: &mut L2CFighterCommon)%s {" % (
        name, " -> L2CValue" if returns else "")
    return "\n".join(["#[allow(unused_variables)]", signature] + ["    " + line for line in body]
                     + (["    0.into()"] if returns else []) + ["}"])


def minted_name(state: dict, source: str) -> str | None:
    owner, _, weapon = source.partition("/")
    from .packs import weapon_short_name
    for article in state.get("articles") or []:
        if article.get("owner") == owner and article.get("weapon") and \
                weapon_short_name(owner, article["weapon"]) == weapon:
            return article.get("name")
    return None


def hud_code(state: dict, constant: str, resource: str, suffix: str) -> tuple[list[str], list[str], set]:
    """A blank line function with the calls the picked HUD takes."""
    hud = state.get("hud") or {}
    if not (hud.get("from") or hud.get("layout")):
        return [], [], set()
    name = "hud%s" % suffix
    body = ["// called every frame: tell the HUD what to show, here or from your moves"]
    calls = list(gimmicks.HUD_CALLS.get(hud.get("from"), ())) + (
        list(gimmicks.LAYOUT_CALLS) if hud.get("layout") else [])
    for call in calls:
        code, _, note = call.partition(" // ")
        body.append("// %s.hud(&*fighter, %s);%s" % (constant, code, " // " + note if note else ""))
    main = ['    Agent::new("%s").on_line(Main, %s).install(); // the HUD, driven from your code' % (resource, name)]
    uses = {"use smashline::skyline_smash::lua2cpp::L2CFighterCommon;"}
    return main, ["\n" + blank(name, False, body) + "\n"], uses


TETHER_STATUSES = (
    ("AIR_LASSO", "Main", "air_lasso_main"),
    ("AIR_LASSO_REACH", "Main", "air_lasso_reach_main"),
    ("AIR_LASSO_REACH", "End", "air_lasso_reach_end"),
    ("AIR_LASSO_HANG", "Main", "air_lasso_hang_main"),
    ("AIR_LASSO_REWIND", "Main", "air_lasso_rewind_main"),
    ("AIR_LASSO_FAILURE", "Main", "air_lasso_failure_main"),
    ("AIR_LASSO_LANDING", "Main", "air_lasso_landing_main"),
)


def tether_bodies(state: dict, constant: str) -> dict:
    """The donor's own calls for each tether status, as comments."""
    donor = (state.get("tether") or {}).get("from") or ""
    info = gimmicks.TETHER.get(donor)
    if info is None:
        return {}
    first, second, data = info["lasso"]
    names = {}
    for source in info["articles"]:
        minted = minted_name(state, source)
        names[source.partition("/")[2]] = minted
    def index(weapon):
        if weapon is None:
            return "(*ARTICLE_ID_NONE)"
        return '%s.article("%s").index().unwrap_or(*ARTICLE_ID_NONE)' % (
            constant, names.get(weapon) or "<your %s>" % weapon)
    articles = ", ".join("%s (from %s)" % (names.get(source.partition("/")[2]) or "not minted yet", source)
                         for source in info["articles"])
    bodies = {
        "air_lasso_main": ["// %s's tether: its articles, cliff hang data %d" % (donor, data),
                           "// fighter.status_AirLasso(%s.into(), %s.into(), %d.into(), true.into());"
                           % (index(first), index(second), data)],
        "air_lasso_reach_main": ["// fighter.status_AirLassoReach(7.into()); // the article's REACH status"],
        "air_lasso_reach_end": ["// fighter.status_end_AirLassoReach();"],
        "air_lasso_rewind_main": ["// fighter.status_AirLassoRewind(6.into()); // the article's HANG_REWIND status"],
        "air_lasso_failure_main": [
            "// a function of yours calls fighter.sub_air_lasso_failure_uniq(3.into()):",
            "// fighter.status_AirLassoFailure(L2CValue::Ptr(failure_uniq as *const () as _), "
            "hash40(\"air_catch\").into(), 3.into());"],
        "air_lasso_landing_main": ["// fighter.status_AirLassoLanding(2.into()); // the article's EXHAUST status"],
    }
    if donor in ("samus", "samusd", "lucas"):
        bodies["air_lasso_reach_end"].insert(0, "// WorkModule::set_int(fighter.module_accessor, %s, "
                                                "*FIGHTER_STATUS_AIR_LASSO_REACH_WORK_INT_ARTICLE_STATUS);"
                                             % index(first))
    if info["joint"]:
        bodies["air_lasso_hang_main"] = ['// fighter.status_AirLassoHang(hash40("%s").into(), 2.into(), '
                                         'hash40("rot").into()); // the joint it hangs from' % info["joint"]]
    else:
        bodies["air_lasso_hang_main"] = ["// %s's tether never hangs" % donor]
    bodies["air_lasso_main"].append("// its articles: %s" % articles)
    return bodies


def tether_code(state: dict, constant: str, resource: str, suffix: str) -> tuple[list[str], list[str], set]:
    """Blank tether statuses with the donor's own calls in comments."""
    tether = state.get("tether") or {}
    donor = tether.get("from")
    if not donor:
        return [], [], set()
    bodies = tether_bodies(state, constant)
    window = "frame 7 only" if donor == "lucas" else "frames 0 to 5"
    tail = ["\n// %s's tether, blank: port each status from %s's own (the comments are its calls), then its\n"
            "// aircatch scripts, which spawn, shoot, rewind and remove the articles and hold\n"
            "// FIGHTER_STATUS_AIR_LASSO_FLAG_CHECK on for %s. List air_catch, air_catch_pose,\n"
            "// air_catch_hang, air_catch_hit and air_catch_landing in the motion list, and ship\n"
            "// %s_vl.prc in fighter/%s/param/. Also: %s." % (
                donor, donor, window, donor, resource, gimmicks.TETHER_EXTRAS.get(donor, ""))]
    for _, _, name in TETHER_STATUSES:
        tail.append(blank(name + suffix, True, bodies.get(name, [])))
    tail[-1] += "\n"
    main = ['    Agent::new("%s") // the tether statuses, blank until ported' % resource]
    for status, line, name in TETHER_STATUSES:
        main.append("        .status(%s, *FIGHTER_STATUS_KIND_%s, %s%s)" % (line, status, name, suffix))
    main.append("        .install();")
    uses = {"use smashline::skyline_smash::lua2cpp::L2CFighterCommon;", "use smashline::skyline_smash::lib::L2CValue;",
            "use smashline::skyline_smash::lib::lua_const::*;", "smashline:End"}
    return main, ["\n\n".join(tail)], uses


GLIDE_FUNCTIONS = (("glide_start_init", "Init", "GLIDE_START"), ("glide_start_exec", "Exec", "GLIDE_START"),
                   ("glide_init", "Init", "GLIDE"), ("glide_exec", "Exec", "GLIDE"))


def glide_code(state: dict, resource: str, suffix: str) -> tuple[list[str], list[str], set]:
    """Brawl's glide from clone_engine_api::glide, unless the float is on."""
    settings = state.get("glide") or {}
    if not settings.get("on") or (state.get("float") or {}).get("on"):
        return [], [], set()
    preset = settings.get("preset") if settings.get("preset") in gimmicks.GLIDE_PRESETS else "META_KNIGHT"
    call = "Glide::%s" % preset
    frames = settings.get("button_frame")
    if isinstance(frames, int) and not isinstance(frames, bool) and frames != 8:
        call += ".button_frame(%d)" % frames
    constant = "GLIDE%s" % suffix.upper()
    tail = ["\n/// Brawl's glide: %s's values; jump held through the top of the midair jump.\n"
            "/// The motion list needs glide_start, glide, glide_attack, glide_end and glide_landing.\n"
            "const %s: Glide = %s;" % (preset.replace("_", " ").title(), constant, call),
            "unsafe extern \"C\" fn glide_entry%s(fighter: &mut L2CFighterCommon) {\n"
            "    glide::frame(fighter, &%s);\n}" % (suffix, constant)]
    for name, _, _ in GLIDE_FUNCTIONS:
        tail.append("unsafe extern \"C\" fn %s%s(fighter: &mut L2CFighterCommon) -> L2CValue {\n"
                    "    glide::%s(fighter, &%s)\n}" % (name, suffix, name, constant))
    main = ['    Agent::new("%s") // Brawl\'s glide' % resource,
            "        .on_line(Main, glide_entry%s) // the way in, checked every frame" % suffix]
    for name, line, status in GLIDE_FUNCTIONS:
        main.append("        .status(%s, *FIGHTER_STATUS_KIND_%s, %s%s)" % (line, status, name, suffix))
    main.append("        .install();")
    uses = {"use clone_engine_api::glide::{self, Glide};", "use smashline::skyline_smash::lua2cpp::L2CFighterCommon;",
            "use smashline::skyline_smash::lib::L2CValue;", "use smashline::skyline_smash::lib::lua_const::*;",
            "smashline:Exec", "smashline:Init"}
    return main, ["\n\n".join(tail) + "\n"], uses


def fight_code(state: dict, resource: str, suffix: str) -> tuple[list[str], list[str], set]:
    """Facing the opponent, and a blank reader for each of the clone's own commands."""
    commands = [command.get("name") for command in state.get("commands") or [] if command.get("name")]
    face = bool(state.get("face_opponent"))
    if not (face or commands):
        return [], [], set()
    name = "fight_frame%s" % suffix
    body = []
    if face:
        body.append("fight::face_opponent(fighter); // in a 1-on-1 on the ground, turn toward the opponent")
    for command in commands:
        body += ['// if let Some(lr) = fight::command_lr(fighter, "%s") { // lr: the way it was input for' % command,
                 '//     fight::clear_command(fighter, "%s"); // used up' % command,
                 "//     // the move it does",
                 "// }"]
    main = ['    Agent::new("%s").on_line(Main, %s).install(); // %s' % (
        resource, name, "facing the opponent and the commands" if face and commands
        else "facing the opponent" if face else "reading the commands")]
    uses = {"use clone_engine_api::fight;", "use smashline::skyline_smash::lua2cpp::L2CFighterCommon;"}
    return main, ["\n" + blank(name, False, body) + "\n"], uses


def raw_fence(text: str) -> str:
    """The #s a raw string needs so the text cannot close it early."""
    fence = "#"
    while ('"' + fence) in text:
        fence += "#"
    return fence


def guarded_tables(tables, capability: str, note: str) -> list[str]:
    """fighter.toml tables added to the manifest only when the engine has the
    feature: an engine without it refuses the whole manifest."""
    tables = (tables or "").strip()
    if not tables:
        return []
    fence = raw_fence(tables)
    return (["    let manifest = if clone_engine_api::runtime_capabilities() & clone_engine_api::%s != 0 {"
             % capability,
             "        manifest.raw(r%s\"" % fence]
            + tables.splitlines()
            + ["\"%s) // %s, as fighter.toml carries them" % (fence, note),
               "    } else {",
               "        manifest // an older engine would refuse the whole manifest",
               "    };"])


GAME_SWITCH_BASES = ("eflame", "elight", "pzenigame", "pfushigisou", "plizardon")


def entry_group_lines(state: dict) -> list[str]:
    """`switch_with`, `partner` and `partner_with`, added only when the engine has them."""
    from .packs import partner_value, switch_members
    base = state.get("base_resource_name") or state.get("base_fighter") or ""
    calls = []
    any_base = False
    members = switch_members(state)
    if members:
        game_set = base in GAME_SWITCH_BASES
        calls.append("switch_with(&[%s]) // %s"
                     % (", ".join('"%s"' % name for name in members),
                        "the clones down special cycles through" if game_set
                        else "the clones clone_engine_api::switch::next cycles through"))
        any_base = not game_set
    partner = partner_value(state)
    if partner is False:
        calls.append("partner(false) // no partner")
    elif partner is True:
        calls.append("partner(true) // a copy of this fighter follows it the way Nana follows Popo")
        any_base = any_base or base != "popo"
    elif partner:
        calls.append('partner_with("%s") // that clone follows this fighter the way Nana follows Popo'
                     % partner)
        any_base = True
    lines = []
    if calls:
        capability = "CAP_ANY_BASE_GROUPS" if any_base else "CAP_ENTRY_GROUPS"
        chain = ["        manifest." + calls[0]] + ["            ." + call for call in calls[1:]]
        lines = (["    let manifest = if clone_engine_api::runtime_capabilities() & clone_engine_api::%s != 0 {"
                  % capability]
                 + chain
                 + ["    } else {",
                    "        manifest // an older engine would refuse the whole manifest",
                    "    };"])
    if "partner_params" in state:
        params = [row for row in state.get("partner_params") or [] if row.get("key")]
        tables = ("[partner_params]\n" + "\n".join("%s = %s" % (row["key"], row["value"]) for row in params)
                  if params else "")
    else:
        tables = state.get("partner_tables")
    return lines + guarded_tables(tables, "CAP_ANY_BASE_GROUPS",
                                  "the partner's follow params, the Ice Climbers' own names")


def float_literal(value) -> str:
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text
    return "%r" % number if "." in text or "e" in text.lower() else "%.1f" % number


def hook_lines(kind: str, state: dict, constant: str, resource: str,
               names_taken: set | None) -> tuple[list[str], list[str]]:
    """The install line for main and the #[hook] functions, for the entries
    this part picked on the Vtables tab."""
    from . import vtables
    names, blocks = vtables.hook_source(kind, state, constant, resource,
                                        names_taken if names_taken is not None else set())
    if not names:
        return [], []
    install = ["    clone_engine_api::install_hooks!(%s); // the entries picked on the Vtables tab"
               % ", ".join(names)]
    return install, ["\n" + "\n\n".join(blocks) + "\n"]


def fighter_part(state: dict, suffix: str = "", first: bool = True,
                 names_taken: set | None = None) -> dict:
    """What one fighter adds to the plugin: its declaration, its lines in main
    and, when its plugin keeps a one-slot mod's code, the CSK and ParamConfig
    functions with the clone's names."""
    resource = state.get("resource_name", "wawa")
    constant = identifier(resource)
    own = bool(state.get("own_css"))
    _, config_rules = split_rules(state)
    uses = {"v2:fighter", "v2:Line", "v2:Manifest", "smashline:Agent", "smashline:Main", "smashline:Priority"}
    if own:
        uses |= {"use std::collections::HashMap;", "use smash::hash40;",
                 "use the_csk_collection_api::*;"}
    main = fighter_manifest_lines(state, constant)
    uses |= command_uses(state)
    if own:
        main.append("    register_css_entry%s(); // CSK's own call, with the clone's names" % suffix)
        if config_rules:
            main.append("    register_params%s(kind); // ParamConfig's own calls, with the clone's kind" % suffix)
    main += [
        "    Agent::new(\"%s\") // scripts under the clone's own name" % resource,
        "        // .game_acmd(\"game_attack11\", game_attack11, Priority::Default)",
        "        // .status(Main, *FIGHTER_STATUS_KIND_SPECIAL_N, special_n_main)",
        "        .install();",
    ]
    floating = float_lines(state, resource)
    main += floating
    if len(floating) > 1:
        uses |= {"use clone_engine_api::float::{self, Float};", "use smashline::skyline_smash::lib::lua_const::*;",
                 "smashline:End", "smashline:Init", "smashline:Pre"}
    uses |= article_gimmick_uses(state)
    gimmick_tail: list[str] = []
    for code_main, code_tail, code_uses in (glide_code(state, resource, suffix),
                                            tether_code(state, constant, resource, suffix),
                                            hud_code(state, constant, resource, suffix),
                                            fight_code(state, resource, suffix)):
        main += code_main
        gimmick_tail += code_tail
        uses |= code_uses
    if (state.get("hud") or {}).get("from") or (state.get("hud") or {}).get("layout"):
        uses |= {"v2:Hud"} | ({"v2:MenuCommand"} if (state.get("hud") or {}).get("from") == "brave" else set())
    if (state.get("tether") or {}).get("from"):
        uses |= {"use smashline::skyline_smash::app::lua_bind::*;", "use smashline::skyline_smash::hash40;"}
    if state.get("grabs"):
        main.append("    // a grab rule's CATCH box goes in that status's game script: "
                    "macros::CATCH(agent, 0, Hash40::new(\"top\"), size, x, y, z, None, None, None, "
                    "*FIGHTER_STATUS_KIND_CAPTURE_PULLED, *COLLISION_SITUATION_MASK_GA)")
    victims = [gimmicks.display(row.get("name", "")) for row in state.get("global_motions") or []
               if row.get("victim") == "true"]
    if victims:
        main.append("    // %s: play it on the opponent your throw holds, from the throw's status: "
                    "MotionModule::change_motion(opponent, Hash40::new(\"%s\"), 0.0, 1.0, false, 0.0, false, false), "
                    "the opponent from LinkModule::get_node_object_id(boma, *LINK_NO_CAPTURE)"
                    % (", ".join(victims), victims[0]))
    renamed =[article["name"] for article in state.get("base_articles") or []
               if article.get("name") and article.get("base_article")]
    for article in state.get("articles") or []:
        name = article.get("name")
        if not name or name in renamed:
            continue
        if not (article.get("owner") and article.get("weapon")):
            main.append("    // %s ships files but has no source weapon yet: pick a source "
                        "fighter and weapon for it on the Identity tab." % name)
            continue
        short = identifier(name).lower()
        if article.get("kirby_copy"):
            main += ["    %s.copy_article(\"%s\")" % (constant, name),
                     "        // .status(Line::Main, STATUS, %s_main)" % short,
                     "        .install();"]
        else:
            main += ["    Agent::new(\"%s_%s\")" % (resource, name),
                     "        // .game_acmd(\"game_fly\", %s_fly, Priority::Default)" % short,
                     "        .install();",
                     "    %s.article(\"%s\")" % (constant, name),
                     "        // .status(Line::Main, STATUS, %s_main)" % short,
                     "        .install();"]
    for name in renamed:
        short = identifier(name).lower()
        main += ["    Agent::new(\"%s_%s\")" % (resource, name),
                 "        // .game_acmd(\"game_fly\", %s_fly, Priority::Default)" % short,
                 "        .install();",
                 "    %s.article(\"%s\")" % (constant, name),
                 "        // .status(Line::Main, STATUS, %s_main)" % short,
                 "        .install();"]
    statuses = state.get("kirby_statuses")
    if isinstance(statuses, int) and statuses > 0:
        main += ["    Agent::new(\"kirby\")",
                 "        // .status(Main, %s.kirby_status(0), kirby_special_n_main)" % constant,
                 "        .install();",
                 "    %s.arm_kirby();" % constant]
    tail = list(gimmick_tail)
    if own:
        tail.append(css_registration(state, suffix))
        config = param_config_calls(state, suffix)
        if config:
            tail.append(config)
    install, hooks = hook_lines("fighter", state, constant, resource, names_taken)
    if install:
        uses |= {"v2:hook"} | ({"v2:slot"} if any("slot::" in block for block in hooks) else set())
        main += install
        tail += hooks
    colors = int(state.get("color_count", 8) or 8)
    if first:
        handle = "fighter!(%s, \"%s\"); // the handle, and the identity" % (constant, resource)
    else:
        handle = ("pub static %s: clone_engine_api::v2::Fighter = clone_engine_api::v2::Fighter::new(\"%s\"); "
                  "// the handle, and the identity" % (constant, resource))
    return {"name": resource, "uses": uses,
            "decls": [handle,
                      "const %s: u8 = %d; // costumes the pack ships (c00..)" % (costumes_constant(state), colors)],
            "main": main, "tail": tail}


def item_manifest_lines(state: dict, constant: str) -> list[str]:
    """The ItemManifest in main: the same declaration item.toml carries."""
    q = '"'
    resource = state.get("resource_name", "wawa")
    base_kind = state.get("base_kind")
    try:
        base_kind = int(base_kind)
    except (TypeError, ValueError):
        base_kind = 0
    lines = [
        "    let manifest = ItemManifest::new(",
        "        %s%s%s, // resource name: files under item/%s, script name" % (q, resource, q, resource),
        "        %d, // base kind: the vanilla item it is built on%s" % (base_kind, "" if base_kind else " (fill in)"),
        "    )",
    ]
    if state.get("base_item"):
        lines.append("    .base_item(%s%s%s) // the base's name, for the log" % (q, state["base_item"], q))
    if state.get("agent_name"):
        lines.append("    .agent_name(%s%s%s) // script name" % (q, state["agent_name"], q))
    if state.get("ui_id"):
        lines.append("    .ui_id(%s%s%s) // Training menu id" % (q, state["ui_id"], q))
    for key, note in (("training_order", "position in the Training list"),
                      ("spawn_per", "natural drop weight")):
        value = state.get(key)
        if value not in (None, ""):
            try:
                lines.append("    .%s(%d) // %s" % (key, int(value), note))
            except (TypeError, ValueError):
                pass
    low, high = state.get("spawn_min"), state.get("spawn_max")
    if low not in (None, "") or high not in (None, ""):
        try:
            lines.append("    .spawn_range(%d, %d) // how many appear at once" % (int(low or 1), int(high or 1)))
        except (TypeError, ValueError):
            pass
    spawn_from = state.get("spawn_from")
    if isinstance(spawn_from, str):
        spawn_from = [part.strip() for part in spawn_from.split(",") if part.strip()]
    if spawn_from:
        lines.append("    .spawn_from(&[%s]) // containers that can hold it"
                     % ", ".join("%s%s%s" % (q, name, q) for name in spawn_from))
    for rule in state.get("item_params") or []:
        if not rule.get("field") or rule.get("style", "float") not in ("float", "int"):
            continue
        value = rule.get("value", "0")
        if rule.get("style") == "int":
            lines.append("    .common_int(%s%s%s, %d) // a field of item/common/param/param.prc" % (q, rule["field"], q, int(float(value))))
        else:
            lines.append("    .common(%s%s%s, %s) // a field of item/common/param/param.prc" % (q, rule["field"], q, float_literal(value)))
    for rule in state.get("owner_params") or []:
        if not (rule.get("owner") and rule.get("field")):
            continue
        field = rule["field"].split("/")[-1]
        value = rule.get("value", "0")
        if rule.get("integer"):
            lines.append("    .owner_param_int(%s%s%s, %s%s%s, %d) // owner fighter, a field of its vl.prc, value" % (q, rule["owner"], q, q, field, q, int(float(value))))
        else:
            lines.append("    .owner_param(%s%s%s, %s%s%s, %s) // owner fighter, a field of its vl.prc, value" % (q, rule["owner"], q, q, field, q, float_literal(value)))
    lines[-1] = end_statement(lines[-1])
    lines += [
        "    let Ok(kind) = %s.register(manifest) else {" % constant,
        "        return; // the fault is in the log",
        "    };",
        "    skyline::println!(\"[%s] registered as item kind {kind:#x}\");" % resource,
    ]
    return lines


def item_part(state: dict, suffix: str = "", taken: set | None = None,
              names_taken: set | None = None) -> dict:
    """What one item adds to the plugin: its declaration, its ItemManifest in
    main, and the label and hash fields of its common row, which the manifest
    cannot carry. An item named like a fighter of the pack is NAME_ITEM."""
    resource = state.get("resource_name", "wawa")
    constant = identifier(resource)
    if taken and constant in taken:
        constant += "_ITEM"
    labels = item_label_calls(state, suffix)
    main = item_manifest_lines(state, constant)
    if labels:
        main.append("    register_item_labels%s(kind); // label and hash fields, by name" % suffix)
    main.append("    // %s.status(clone_engine_api::ItemStatusLine::Main, \"STATUS\", %s_main); // status line, a status name of the base item, function"
                % (constant, constant.lower()))
    uses = {"v2:item", "v2:ItemManifest"}
    tail = [labels] if labels else []
    install, hooks = hook_lines("item", state, constant, resource, names_taken)
    if install:
        uses |= {"v2:hook"} | ({"v2:slot"} if any("slot::" in block for block in hooks) else set())
        main += install
        tail += hooks
    return {"name": resource, "uses": uses,
            "decls": ["item!(%s, \"%s\"); // the handle, and the resource name" % (constant, resource)],
            "main": main, "tail": tail}


def use_lines(uses: set) -> list[str]:
    """The use block: std first, then the crates by name; the v2 and the
    smashline names each in one line."""
    plain = set(uses)
    for prefix, path in (("v2:", "clone_engine_api::v2"), ("smashline:", "smashline")):
        names = sorted((use[len(prefix):] for use in uses if use.startswith(prefix)), key=str.lower)
        plain -= {prefix + name for name in names}
        if names:
            plain.add("use %s::{%s};" % (path, ", ".join(names)))
    std = sorted(use for use in plain if use.startswith("use std::"))
    crates = sorted(use for use in plain if not use.startswith("use std::"))
    return std + crates


def plugin_source(fighters: list[dict], items: list[dict]) -> str:
    """One lib.rs for the pack: each part registers from a manifest in main
    (a fighter.toml or item.toml beside it is read first and wins), then adds
    its code. With several parts of one kind, each part's functions carry its
    name."""
    names_taken: set = set()
    parts = [fighter_part(state, suffix(state) if len(fighters) > 1 else "",
                          first=index == 0, names_taken=names_taken)
             for index, state in enumerate(fighters)]
    taken = {identifier(state.get("resource_name", "wawa")) for state in fighters}
    parts += [item_part(state, suffix(state) if len(items) > 1 else "", taken, names_taken)
              for state in items]
    if not parts:
        return ""
    uses: set = set()
    for part in parts:
        uses |= part["uses"]
    lines = use_lines(uses) + [""]
    for part in parts:
        lines += part["decls"]
    lines += ["", "#[skyline::main(name = \"%s\")]" % parts[0]["name"], "pub fn main() {"]
    for part in parts:
        lines += part["main"]
    lines += ["}", ""]
    blocks = ["\n".join(lines)]
    for part in parts:
        blocks += part["tail"]
    return "\n".join(blocks)
