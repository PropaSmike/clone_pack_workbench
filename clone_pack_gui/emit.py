#!/usr/bin/env python3
"""Turn the panels' fields into the Rust a pack's plugin compiles."""

from __future__ import annotations


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
    has eight layouts, so a costume past c07 clones layout `color % 8`."""
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
        "        clone_from_ui_chara_id: Some(hash40(%sui_chara_%s%s)), // copy every other field from the base's entry" % (q, base, q),
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
        lines.append("        disp_order: SignedByteType::Optional(Some(%d)), // position on the select screen" % order)
    lines += [
        "        color_num: UnsignedByteType::Overwrite(%s), // number of costumes" % costumes,
        "        shop_item_tag: Hash40Type::Overwrite(hash40(%s-1%s)), // the base's DLC fields hide the entry; clear them" % (q, q),
        "        alt_chara_id: Hash40Type::Overwrite(hash40(%s-1%s))," % (q, q),
        "        save_no: SignedByteType::Overwrite(0),",
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
    for key in ("ui_chara", "fighter_kind_name"):
        if state.get(key):
            lines.append("    .%s(%s%s%s) // overrides the name derived from name" % (key, q, state[key], q))
    if state.get("staffroll"):
        lines.append("    .staffroll() // the pack's credits picture")
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
    statuses = state.get("kirby_statuses")
    if isinstance(statuses, int) and statuses > 0:
        lines.append("    .kirby(%d) // status numbers reserved for Kirby's copy" % statuses)
    if state.get("kirby_copy_full_model"):
        lines.append("    .kirby_full_model() // Kirby gets the whole body, not a hat")
    engine, config = split_rules(state)
    rules = engine if own else engine + config
    if rules:
        lines += manifest_param_calls(rules)
    lines[-1] = end_statement(lines[-1])
    lines += [
        "    let Ok(kind) = %s.register(manifest) else {" % constant,
        "        return; // the fault is in the log",
        "    };",
        "    skyline::println!(\"[%s] registered as fighter kind {kind}\");" % resource,
    ]
    return lines


def float_literal(value) -> str:
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text
    return "%r" % number if "." in text or "e" in text.lower() else "%.1f" % number


def fighter_part(state: dict, suffix: str = "") -> dict:
    """What one fighter adds to the plugin: its declaration, its lines in main
    and, when its plugin keeps a one-slot mod's code, the CSK and ParamConfig
    functions with the clone's names."""
    resource = state.get("resource_name", "wawa")
    constant = identifier(resource)
    own = bool(state.get("own_css"))
    _, config_rules = split_rules(state)
    uses = {"v2:fighter", "v2:Line", "v2:Manifest", "use smashline::{Agent, Main, Priority};"}
    if own:
        uses |= {"use std::collections::HashMap;", "use smash::hash40;",
                 "use the_csk_collection_api::*;"}
    main = fighter_manifest_lines(state, constant)
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
    for article in state.get("articles") or []:
        name = article.get("name")
        if not name:
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
    statuses = state.get("kirby_statuses")
    if isinstance(statuses, int) and statuses > 0:
        main += ["    Agent::new(\"kirby\")",
                 "        // .status(Main, %s.kirby_status(0), kirby_special_n_main)" % constant,
                 "        .install();",
                 "    %s.arm_kirby();" % constant]
    tail = []
    if own:
        tail.append(css_registration(state, suffix))
        config = param_config_calls(state, suffix)
        if config:
            tail.append(config)
    colors = int(state.get("color_count", 8) or 8)
    return {"name": resource, "uses": uses,
            "decls": ["fighter!(%s, \"%s\"); // the handle, and the identity" % (constant, resource),
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


def item_part(state: dict, suffix: str = "", taken: set | None = None) -> dict:
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
    return {"name": resource, "uses": {"v2:item", "v2:ItemManifest"},
            "decls": ["item!(%s, \"%s\"); // the handle, and the resource name" % (constant, resource)],
            "main": main, "tail": [labels] if labels else []}


def use_lines(uses: set) -> list[str]:
    """The use block: std first, then the crates by name; the v2 names in one line."""
    v2 = sorted((use[3:] for use in uses if use.startswith("v2:")), key=str.lower)
    plain = {use for use in uses if not use.startswith("v2:")}
    if v2:
        plain.add("use clone_engine_api::v2::{%s};" % ", ".join(v2))
    std = sorted(use for use in plain if use.startswith("use std::"))
    crates = sorted(use for use in plain if not use.startswith("use std::"))
    return std + crates


def plugin_source(fighters: list[dict], items: list[dict]) -> str:
    """One lib.rs for the pack: each part registers from a manifest in main
    (a fighter.toml or item.toml beside it is read first and wins), then adds
    its code. With several parts of one kind, each part's functions carry its
    name."""
    parts = [fighter_part(state, suffix(state) if len(fighters) > 1 else "")
             for state in fighters]
    taken = {identifier(state.get("resource_name", "wawa")) for state in fighters}
    parts += [item_part(state, suffix(state) if len(items) > 1 else "", taken)
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
