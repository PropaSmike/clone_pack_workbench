#!/usr/bin/env python3
"""Turn the panels' fields into the Rust a pack's plugin compiles."""

from __future__ import annotations

FLAG_OWNS_PARAM_RESOURCES = "FLAG_OWNS_PARAM_RESOURCES"
FLAG_KIRBY_COPY_FULL_MODEL = "FLAG_KIRBY_COPY_FULL_MODEL"


def identifier(name: str) -> str:
    return "".join(character if character.isalnum() else "_"
                   for character in name).strip("_").upper() or "CLONE"


def suffix(state: dict) -> str:
    """What a pack with several parts of one kind appends to each function name."""
    return "_" + identifier(state.get("resource_name") or state.get("place") or "").lower()


def fighter_registration(state: dict, suffix: str = "") -> str:
    """The CloneRegistration block for a fighter clone, ready to paste."""
    resource = state.get("resource_name", "wawa")
    base_name = state.get("base_resource_name", "mario")
    base_kind = state.get("base_kind", 0)
    kind_name = state.get("fighter_kind_name") or "fighter_kind_%s" % resource
    ui_chara = state.get("ui_chara") or "ui_chara_%s" % resource
    colors = int(state.get("color_count", 8) or 8)
    start = int(state.get("color_start", 0) or 0)
    flags = []
    if state.get("owns_param_resources"):
        flags.append(FLAG_OWNS_PARAM_RESOURCES)
    if state.get("kirby_copy_full_model"):
        flags.append(FLAG_KIRBY_COPY_FULL_MODEL)

    lines = [
        "use clone_engine_api::{CloneRegistration, KIND_AUTO};",
        "",
        "pub const RESOURCE_NAME%s: &str = \"%s\";" % (suffix.upper(), resource),
        "",
        "pub fn register%s() -> Result<i32, clone_engine_api::Error> {" % suffix,
        "    let mut clone = CloneRegistration::new(",
        "        KIND_AUTO,",
        "        %d," % int(base_kind),
        "        \"%s\"," % ui_chara,
        "        \"%s\"," % kind_name,
        "        RESOURCE_NAME%s," % suffix.upper(),
        "        \"%s\"," % base_name,
        "    );",
    ]
    if start:
        lines.append("    clone.color_start = %d;" % start)
    lines.append("    clone.color_count = %d;" % colors)
    for flag in flags:
        lines.append("    clone.flags |= clone_engine_api::%s;" % flag)
    copy_first = state.get("copy_status_first")
    copy_count = state.get("copy_status_count")
    if copy_first and copy_count:
        lines.append("    clone.copy_status_first = %d;" % int(copy_first))
        lines.append("    clone.copy_status_count = %d;" % int(copy_count))
    lines += [
        "    clone_engine_api::allocate(&clone)",
        "}",
    ]
    return "\n".join(lines) + "\n"


def article_calls(state: dict, suffix: str = "") -> str:
    """One handle call per article the pack ships, on the fighter or on Kirby."""
    articles = state.get("articles") or []
    if not articles:
        return ""
    resource = state.get("resource_name", "wawa")
    waiting = [article.get("name") or "?" for article in articles
               if not (article.get("owner") and article.get("weapon"))]
    articles = [article for article in articles
                if article.get("owner") and article.get("weapon")]
    notes = ["// %s ships files but has no source weapon yet: pick a source "
             "fighter and weapon for it on the Identity tab." % name
             for name in waiting]
    if not articles:
        return "\n".join(notes) + "\n" if notes else ""
    lines = ["pub fn register_articles%s(base_kind: i32) {" % suffix]
    for article in articles:
        owner = article.get("owner")
        weapon = article.get("weapon")
        name = article.get("name") or "%s_article" % resource
        constant = identifier(name)
        if article.get("kirby_copy"):
            lines += [
                "    match clone_engine_api::clone_copy_article_handle(",
                "        *smash::lib::lua_const::FIGHTER_KIND_KIRBY,",
                "        \"%s\"," % owner,
                "        *smash::lib::lua_const::%s," % weapon.upper(),
                "        \"%s\"," % resource,
                "        \"%s\"," % name,
                "    ) {",
            ]
        else:
            lines += [
                "    match clone_engine_api::clone_article_handle(",
                "        \"%s\"," % owner,
                "        *smash::lib::lua_const::%s," % weapon.upper(),
                "        \"%s\"," % resource,
                "        \"%s\"," % name,
                "        base_kind,",
                "    ) {",
            ]
        lines += [
            "        Ok(handle) => {",
            "            %s.store(handle.weapon_kind(), Ordering::Relaxed);" % constant,
            "            skyline::println!(\"[%s] %s is weapon kind {}\", handle.weapon_kind());"
            % (resource, name),
            "        }",
            "        Err(error) => skyline::println!(\"[%s] %s declined: {error:?}\"),"
            % (resource, name),
            "    }",
        ]
    lines.append("}")
    statics = ["use std::sync::atomic::{AtomicI32, Ordering};", ""]
    for article in articles:
        statics.append("pub static %s: AtomicI32 = AtomicI32::new(-1);"
                       % identifier(article.get("name") or "article"))
    statics.append("")
    return "\n".join(notes + statics + lines) + "\n"


def param_calls(state: dict, suffix: str = "") -> str:
    """param_override_full lines for every fighter surface a clone can own."""
    rules = state.get("params") or []
    if not rules:
        return ""
    tag = state.get("resource_name") or "pack"
    lines = ["pub fn register_params%s(kind: i32) {" % suffix,
             "    use clone_engine_api::{ParamOp, ANY_SLOT};"]
    for rule in rules:
        table = rule.get("table", "fighter_param")
        field = rule.get("field", "")
        value = rule.get("value", "0")
        operation = rule.get("op", "Set")
        if rule.get("integer"):
            call = ("clone_engine_api::param_int_override_full("
                    "kind, ANY_SLOT, \"%s\", \"%s\", %s)" % (table, field, value))
        else:
            call = ("clone_engine_api::param_override_full("
                    "kind, ANY_SLOT, \"%s\", \"%s\", ParamOp::%s, %s)"
                    % (table, field, operation, float_literal(value)))
        lines += ["    if !%s {" % call,
                  "        skyline::println!(\"[%s] %s %s was not applied\");"
                  % (tag, table, field),
                  "    }"]
    lines.append("}")
    return "\n".join(lines) + "\n"


def reported(call: str, tag: str, what: str) -> list[str]:
    """A call whose Err is printed rather than dropped: an engine older than the
    call returns EngineUnavailable, and a refused value says why in its own line."""
    return ["    if let Err(error) = %s {" % call,
            "        skyline::println!(\"[%s] %s was not applied: {error:?}\");"
            % (tag, what),
            "    }"]


def item_registration(state: dict, suffix: str = "") -> str:
    """The allocate_item block for an item pack that ships a plugin. An item.toml
    beside it may have registered the item first, so the kind is looked up before
    it is allocated, and the Training cell and spawns are only added on the
    allocating path; the param blocks apply either way."""
    resource = state.get("resource_name") or "wawa"
    base_kind = int(state.get("base_kind", 0) or 0)
    base_name = state.get("base_item") or "base item"
    agent = state.get("agent_name") or resource
    ui_id = state.get("ui_id") or "ui_item_%s" % resource
    order = int(state.get("training_order", 0) or 0)
    handle = identifier(resource)
    params = [name + suffix for name, block in
              (("register_item_params", item_common_calls(state)),
               ("register_owner_params", item_owner_param_calls(state)))
              if block]
    spawns = bool(item_generate_calls(state))
    lines = [
        "pub static %s: clone_engine_api::CloneItemKind ="
        " clone_engine_api::CloneItemKind::new(\"%s\");" % (handle, resource),
        "",
        "pub fn register_item%s() -> Option<i32> {" % suffix,
        "    if let Some(kind) = clone_engine_api::item_kind_for_identity(\"%s\") {"
        % resource,
        "        // item.toml registered it first; its Training cell and spawns stand",
        "        %s.store(kind);" % handle,
    ]
    lines += ["        %s(kind);" % name for name in params]
    lines += [
        "        return Some(kind);",
        "    }",
        "    let registration = clone_engine_api::ItemCloneRegistration::new(",
        "        clone_engine_api::KIND_AUTO,",
        "        %d, // %s" % (base_kind, base_name),
        "        \"%s\", // item/%s" % (resource, resource),
        "        \"%s\", // agent name" % agent,
        "    );",
        "    let kind = match clone_engine_api::allocate_item(&registration) {",
        "        Ok(kind) => kind,",
        "        Err(error) => {",
        "            skyline::println!(\"[%s] item was not registered: {error:?}\");"
        % resource,
        "            return None;",
        "        }",
        "    };",
        "    %s.store(kind);" % handle,
        "    let %scell = clone_engine_api::ItemUiRegistration::training(kind, \"%s\");"
        % ("mut " if order else "", ui_id),
    ]
    if order:
        lines.append("    cell.training_order = %d;" % order)
    lines += [
        "    if let Err(error) = clone_engine_api::register_item_ui(&cell) {",
        "        skyline::println!(\"[%s] Training cell was not added: {error:?}\");" % resource,
        "    }",
    ]
    lines += ["    %s(kind);" % name for name in params]
    if spawns:
        lines.append("    register_spawns%s(kind);" % suffix)
    lines += ["    Some(kind)", "}"]
    return "\n".join(lines) + "\n"


def item_owner_param_calls(state: dict, suffix: str = "") -> str:
    """The two calls that give a clone item its own copy of a fighter's vl.prc words."""
    rules = state.get("owner_params") or []
    if not rules:
        return ""
    tag = state.get("resource_name") or "pack"
    lines = ["pub fn register_owner_params%s(kind: i32) {" % suffix]
    for rule in rules:
        owner = rule.get("owner_kind", 0)
        offset = int(str(rule.get("offset", "0")), 0)
        value = rule.get("value", "0")
        what = rule.get("field") or "%s word +%#x" % (rule.get("owner", owner), offset)
        if rule.get("integer"):
            call = ("clone_engine_api::item_owner_param_set_i32(kind, %s, %#x, %s)"
                    % (owner, offset, int(float(value))))
        else:
            call = ("clone_engine_api::item_owner_param_set_f32(kind, %s, %#x, %s)"
                    % (owner, offset, float_literal(value)))
        if rule.get("field"):
            lines.append("    // %s" % rule["field"])
        lines += reported(call, tag, what)
    lines.append("}")
    return "\n".join(lines) + "\n"


def item_common_calls(state: dict, suffix: str = "") -> str:
    """item_common_set lines for a clone item's own row of the common param."""
    rules = state.get("item_params") or []
    if not rules:
        return ""
    tag = state.get("resource_name") or "pack"
    lines = ["pub fn register_item_params%s(kind: i32) {" % suffix]
    for rule in rules:
        field = rule.get("field", "")
        value = rule.get("value", "0")
        style = rule.get("style", "float")
        if style == "label":
            call = ("clone_engine_api::item_common_set_label("
                    "kind, smash::hash40(\"%s\"), smash::hash40(\"%s\"))" % (field, value))
        elif style == "hash":
            call = ("clone_engine_api::item_common_set_hash("
                    "kind, smash::hash40(\"%s\"), smash::hash40(\"%s\"))" % (field, value))
        elif style == "int":
            call = ("clone_engine_api::item_common_set_i32("
                    "kind, smash::hash40(\"%s\"), %s)" % (field, int(float(value))))
        else:
            call = ("clone_engine_api::item_common_set("
                    "kind, smash::hash40(\"%s\"), %s)" % (field, float_literal(value)))
        lines += reported(call, tag, field)
    lines.append("}")
    return "\n".join(lines) + "\n"


def containers(state: dict) -> list[str]:
    """The container names a manifest carries, however it wrote them."""
    value = state.get("spawn_from")
    if not value:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(part).strip() for part in value if str(part).strip()]


def spawn_note(state: dict) -> str:
    """The item.toml keys that let an item drop on its own."""
    per = state.get("spawn_per")
    if not per:
        return ""
    lines = ["spawn_per     = %s" % per,
             "spawn_min     = %s" % state.get("spawn_min", 1),
             "spawn_max     = %s" % state.get("spawn_max", 1)]
    names = containers(state)
    if names:
        lines.append('spawn_from    = "%s"' % ", ".join(names))
    return "\n".join(lines) + "\n"


def item_generate_calls(state: dict, suffix: str = "") -> str:
    """The same spawn rules as calls, for an item pack that ships a plugin."""
    per = state.get("spawn_per")
    if not per:
        return ""
    generators = ["item_genid_random"] + ["item_kind_%s" % name
                                          for name in containers(state)]
    tag = state.get("resource_name") or "pack"
    lines = ["pub fn register_spawns%s(kind: i32) {" % suffix,
             "    for generator in [%s] {"
             % ", ".join('"%s"' % name for name in generators),
             "        if let Err(error) = clone_engine_api::item_generate_add(",
             "            kind,",
             "            smash::hash40(generator),",
             "            %s," % per,
             "            %s," % state.get("spawn_min", 1),
             "            %s," % state.get("spawn_max", 1),
             "            clone_engine_api::ITEM_VARIATION_AUTO,",
             "        ) {",
             "            skyline::println!(\"[%s] spawns from {generator} were not "
             "applied: {error:?}\");" % tag,
             "        }",
             "    }",
             "}"]
    return "\n".join(lines) + "\n"


def float_literal(value) -> str:
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text
    return "%r" % number if "." in text or "e" in text.lower() else "%.1f" % number


def plugin_source(state: dict, suffix: str = "") -> str:
    """Everything the panels describe, in the order a lib.rs would carry it."""
    blocks = [block for block in (
        fighter_registration(state, suffix),
        article_calls(state, suffix),
        param_calls(state, suffix),
        item_common_calls(state, suffix),
        item_owner_param_calls(state, suffix),
    ) if block]
    return "\n".join(blocks)
