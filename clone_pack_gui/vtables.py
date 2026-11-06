#!/usr/bin/env python3
"""Every vtable entry a part can hook, and the #[hook] the Rust tab writes for the picked ones."""

from __future__ import annotations

from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

FIGHTER = "fighter"
COMMON = "common"
COPY = "copy"
WEAPON = "weapon"
WEAPON_COMMON = "weapon_common"
ITEM = "item"
ITEM_COMMON = "item_common"
ENEMY = "enemy"
ENEMY_OBJECT = "enemy_object"
ENEMY_API = "dionysus_api::enemy::"
ENEMY_BASES = {"yellow_devil": "yellow_devil", "yellowdevil": "yellow_devil",
               "dark_emperor": "dark_emperor", "subetenoyaminoou": "dark_emperor",
               "flying_man": "flying_man", "flyingman": "flying_man",
               "metal_face": "metal_face", "metalface": "metal_face", "nabbit": "nabbit"}
ROUTED = (73, 74)
SMASHLINE_SPACES = {FIGHTER: ("fighter", "FighterVtableSlot"), WEAPON: ("weapon", "WeaponVtableSlot")}
SMASHLINE_NAMES = ("replace_fighter_vtable", "replace_fighter_vtable_costume", "get_original_fighter_vtable",
                   "FighterVtableSlot", "Costume", "replace_weapon_vtable", "get_original_weapon_vtable",
                   "WeaponVtableSlot")
SMASHLINE_NEEDS = "smashline tag v2.0.0 in Cargo.toml"

L2CVALUE = "smashline::skyline_smash::lib::L2CValue"

COMMON_SLOTS = [
    (0, "DESTRUCTOR", [("agent", "u64")], "u64"),
    (1, "DELETER", [("agent", "u64")], "u64"),
    (2, "COROUTINE_YIELD", [("agent", "u64")], "u64"),
    (3, "START_COROUTINE", [("agent", "u64"), ("index", "i32"), ("name", "u64"), ("state", "*mut i32")], "u32"),
    (4, "RESUME_COROUTINE", [("agent", "u64"), ("index", "i32"), ("state", "*mut i32")], "u32"),
    (5, "GET_UNUSED_COROUTINE_INDEX", [("agent", "u64"), ("max", "i32")], "u32"),
    (6, "CLEAN_COROUTINE", [("agent", "u64"), ("index", "i32")], "u32"),
    (7, "SET_COROUTINE_RELEASE_CONTROL", [("agent", "u64"), ("release", "u32")], "u64"),
    (8, "IS_COROUTINE_RELEASE_CONTROL", [("agent", "u64")], "u32"),
    (9, "SET_STATUS_SCRIPTS", [("agent", "u64")], "u64"),
    (10, "SYS_LINE_SYSTEM_INIT", [("agent", "u64")], L2CVALUE),
    (11, "SUB_BEGIN_ADDED_LINES", [("agent", "u64"), ("lines", L2CVALUE)], "u64"),
    (12, "SYS_LINE_STATUS_END_CONTROL", [("agent", "u64")], L2CVALUE),
    (13, "SUB_END_ADDED_LINES", [("agent", "u64")], "u64"),
    (14, "RESET", [("agent", "u64")], "u64"),
]
COMMON_NOTES = {
    10: "runs once, as the agent starts",
    12: "runs at the end of every status",
}
ITEM_COMMON_COUNT = 10
FIRST_SYSTEM_LINE = 10

_cache: dict = {}


def _load() -> dict:
    if _cache:
        return _cache
    slots: dict = {}
    path = DATA / "vtable_slots.tsv"
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) < 9:
                continue
            space, slot, name, constant, ints, floats, ret, impls, note = parts[:9]
            slots[(space, int(slot))] = {
                "name": name, "constant": constant, "ints": int(ints), "floats": int(floats),
                "ret": ret, "impls": int(impls), "note": note}
    grids: dict = {}
    for space in (FIGHTER, WEAPON, ITEM, ENEMY, "common"):
        table: dict = {}
        path = DATA / ("vtable_%s.tsv" % space)
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                label, _, entries = line.partition("\t")
                table[label] = entries.split(" ") if entries else []
        grids[space] = table
    smashline: dict = {}
    path = DATA / "vtable_smashline.tsv"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            space, slot, variant = line.split("\t")
            smashline[(space, int(slot))] = variant
    _cache.update({"slots": slots, "grids": grids, "smashline": smashline})
    return _cache


def available() -> bool:
    return bool(_load()["slots"])


def weapon_label(owner: str, const: str) -> str:
    """`koopajr::cannonball` for owner koopajr and WEAPON_KIND_KOOPAJR_CANNONBALL."""
    from .packs import weapon_short_name
    return "%s::%s" % (owner, weapon_short_name(owner, const))


def sourced_articles(state: dict) -> list[dict]:
    """The part's articles that have a source weapon and are its own (not Kirby's)."""
    return [article for article in state.get("articles") or []
            if article.get("name") and article.get("owner") and article.get("weapon")
            and not article.get("kirby_copy")]


def tables(kind: str, state: dict) -> list[tuple[str, str]]:
    """(table id, label) for every table this part can hook."""
    if kind == "fighter":
        out = [(FIGHTER, "Fighter vtable (this clone's own copy)"),
               (COMMON, "Agent common: L2CFighterCommon (this clone's agent)"),
               (COPY, "Kirby copy: L2CFighterCommon on Kirby while he holds the ability")]
        for article in sourced_articles(state):
            out.append(("%s:%s" % (WEAPON, article["name"]),
                        "Article %s: weapon vtable" % article["name"]))
            out.append(("%s:%s" % (WEAPON_COMMON, article["name"]),
                        "Article %s: agent common (L2CWeaponCommon)" % article["name"]))
        return out
    if kind == "item":
        return [(ITEM, "Item vtable (this item's own copy)"),
                (ITEM_COMMON, "Item agent common (entries 0 to 9)")]
    if kind == "enemy":
        return [(ENEMY, "Enemy class vtable (this clone's own entries)"),
                (ENEMY_OBJECT, "Enemy object vtable (this clone's own copy)")]
    return []


def enemy_base(state: dict) -> str:
    """The enemy.toml base as the catalog labels it: nabbit, flying_man, yellow_devil..."""
    return ENEMY_BASES.get(str(state.get("base") or "nabbit").lower(), "nabbit")


def _space(table: str) -> tuple[str, str]:
    base, _, article = table.partition(":")
    return base, article


def _base_fighter(state: dict) -> str:
    return state.get("base_resource_name") or state.get("base_fighter") or ""


def _article(state: dict, name: str) -> dict | None:
    return next((article for article in sourced_articles(state) if article["name"] == name), None)


def _address(space: str, state: dict, article: str, slot: int) -> str:
    grids = _load()["grids"]
    if space == FIGHTER:
        row = grids[FIGHTER].get(_base_fighter(state))
    elif space == WEAPON:
        found = _article(state, article)
        row = grids[WEAPON].get(weapon_label(found["owner"], found["weapon"])) if found else None
    elif space == ITEM:
        row = grids[ITEM].get("item")
    elif space in (COMMON, COPY):
        row = grids["common"].get("fighter_common")
    elif space == WEAPON_COMMON:
        row = grids["common"].get("weapon_common")
    elif space == ITEM_COMMON:
        row = grids["common"].get("item_common:%s" % state.get("base_kind"))
    elif space == ENEMY:
        row = grids[ENEMY].get(enemy_base(state))
    elif space == ENEMY_OBJECT:
        row = grids[ENEMY].get(ENEMY_OBJECT)
    else:
        row = None
    if not row or slot >= len(row):
        return ""
    entry = row[slot]
    if space in (FIGHTER, WEAPON, ITEM, ENEMY, ENEMY_OBJECT):
        return "main+0x%s" % entry
    return entry.replace("extern=", "")


def signature(space: str, slot: int) -> dict:
    """{params: [(name, type)], ret, offered, why, summary} for one slot."""
    if space in (COMMON, COPY, WEAPON_COMMON, ITEM_COMMON):
        _, constant, params, ret = COMMON_SLOTS[slot]
        return {"params": params, "ret": ret, "offered": True, "why": "",
                "constant": constant, "name": constant,
                "summary": "declared by the game's own symbols"}
    row = _load()["slots"].get((space, slot))
    if row is None:
        return {"params": [], "ret": "", "offered": False, "why": "not in the catalog",
                "constant": "", "name": "", "summary": ""}
    first = {ITEM: [("item", "u64")], ENEMY: [("instance", "u64")],
             ENEMY_OBJECT: [("object", "u64")]}.get(space, [("class", "u64"), ("object", "u64")])
    ints = max(row["ints"], len(first))
    params = list(first) + [("a%d" % index, "u64") for index in range(len(first), ints)]
    params += [("f%d" % index, "f64") for index in range(row["floats"])]
    ret = {"f64": "f64", "x8": None, "x8?": None, "mixed": None}.get(row["ret"], "u64")
    why = ""
    if row["ret"] in ("x8", "x8?"):
        why = "returns a struct through x8 (or may); no signature passes it through"
    elif row["ret"] == "mixed":
        why = "some implementations return an integer, others a float"
    summary = "read off %d implementation%s" % (row["impls"], "" if row["impls"] == 1 else "s")
    return {"params": params, "ret": ret, "offered": not why, "why": why,
            "constant": row["constant"], "name": row["name"], "summary": summary}


def smashline_slot(space: str, slot: int) -> str:
    """`FighterVtableSlot::OnFrame3` when Smashline 2.0 replaces this entry, else empty."""
    route = SMASHLINE_SPACES.get(space)
    variant = _load()["smashline"].get((space, slot)) if route else None
    return "%s::%s" % (route[1], variant) if variant else ""


def costume_list(text) -> list[int]:
    """The costumes a line such as "4, c05" names; ValueError on anything else."""
    if isinstance(text, (list, tuple)):
        text = ",".join(str(part) for part in text)
    out = set()
    for part in str(text or "").replace(" ", ",").split(","):
        part = part.strip().lower()
        if part:
            value = int(part[1:] if part.startswith("c") else part)
            if not 0 <= value < 256:
                raise ValueError(part)
            out.add(value)
    return sorted(out)


def picked_text(hook: dict) -> str:
    """What the Hooked column shows: yes, or the costumes the entry is limited to."""
    costumes = hook.get("costumes") or []
    return ", ".join("c%02d" % costume for costume in costumes) if costumes else "yes"


def describe(sig: dict) -> str:
    """`(class, object, a2) -> u64`, the way the tab shows it."""
    if not sig["offered"]:
        return "not offered: " + sig["why"]
    ret = sig["ret"]
    shown = "L2CValue" if ret == L2CVALUE else ret
    params = ", ".join(name if kind in ("u64",) else "%s: %s" % (name, "L2CValue" if kind == L2CVALUE else kind)
                       for name, kind in sig["params"])
    return "(%s) -> %s" % (params, shown)


def entries(table: str, state: dict) -> list[dict]:
    """One row per slot of the table, for the tab."""
    space, article = _space(table)
    if space in (COMMON, WEAPON_COMMON):
        slots = range(len(COMMON_SLOTS))
    elif space == COPY:
        slots = range(FIRST_SYSTEM_LINE, len(COMMON_SLOTS))
    elif space == ITEM_COMMON:
        slots = range(ITEM_COMMON_COUNT)
    else:
        slots = sorted(slot for (s, slot) in _load()["slots"] if s == space)
    out = []
    for slot in slots:
        sig = signature(space, slot)
        note = COMMON_NOTES.get(slot, "") if space in (COMMON, COPY, WEAPON_COMMON) else \
            _load()["slots"].get((space, slot), {}).get("note", "")
        out.append({"table": table, "slot": slot, "name": sig["name"], "address": _address(space, state, article, slot),
                    "signature": describe(sig), "offered": sig["offered"], "note": note,
                    "via": smashline_slot(space, slot) or "#[hook]"})
    return out


def identifier(text: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "_" for ch in text)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_") or "hook"


def hook_source(kind: str, state: dict, constant: str, resource: str, taken: set) -> tuple[list[str], list[str]]:
    """(function names, source) for the part's picked hooks, in pick order."""
    names, blocks = [], []
    for hook in state.get("hooks") or []:
        table = hook.get("table", "")
        slot = hook.get("slot")
        if not isinstance(slot, int):
            continue
        space, article = _space(table)
        if space in (ENEMY, ENEMY_OBJECT) or smashline_slot(space, slot):
            continue
        sig = signature(space, slot)
        if not sig["offered"]:
            continue
        if space in (WEAPON, WEAPON_COMMON) and _article(state, article) is None:
            continue
        slot_path = {FIGHTER: "slot::fighter::", WEAPON: "slot::weapon::", ITEM: "slot::item::"}.get(
            space, "slot::common::") + sig["constant"] if sig["constant"] else str(slot)
        key = {FIGHTER: "slot", WEAPON: "slot", ITEM: "slot", COMMON: "common_slot",
               WEAPON_COMMON: "common_slot", ITEM_COMMON: "common_slot", COPY: "copy_slot"}[space]
        arguments = ["%s = %s" % (key, slot_path)]
        if space in (WEAPON, WEAPON_COMMON):
            arguments.append('article = "%s"' % article)
        if kind == "item":
            arguments.append("item = %s" % constant)
        else:
            arguments.append("of = &%s" % constant)
        stem = {FIGHTER: "", COMMON: "common_", COPY: "kirby_", WEAPON: article + "_",
                WEAPON_COMMON: article + "_common_", ITEM: "", ITEM_COMMON: "common_"}[space]
        name = identifier("%s_%s%s" % (resource, stem, sig["name"] or "slot_%d" % slot))
        if name in taken:
            name = "%s_%d" % (name, slot)
        taken.add(name)
        names.append(name)
        params = ", ".join("%s: %s" % (param, kind_) for param, kind_ in sig["params"])
        passed = ", ".join(param for param, _ in sig["params"])
        ret = " -> %s" % sig["ret"] if sig["ret"] else ""
        address = _address(space, state, article, slot)
        where = {FIGHTER: "fighter vtable", COMMON: "agent common", COPY: "agent common, on Kirby holding the copy",
                 WEAPON: "article %s weapon vtable" % article, WEAPON_COMMON: "article %s agent common" % article,
                 ITEM: "item vtable", ITEM_COMMON: "item agent common"}[space]
        first = sig["params"][0][0]
        subject = {"class": "class is the class object, object the %s" % ("weapon" if space == WEAPON else "fighter"),
                   "item": "item is the item object", "agent": "agent is the %s's script agent"
                   % ("Kirby" if space == COPY else "item" if kind == "item" else "weapon" if space == WEAPON_COMMON else "fighter")}[first]
        blocks.append("\n".join([
            "// %s slot %d%s%s; signature %s" % (where, slot, (" " + sig["name"]) if sig["name"] else "",
                                                 (", base " + address) if address else "", sig["summary"]),
            "#[hook(%s)]" % ", ".join(arguments),
            "unsafe fn %s(%s)%s {" % (name, params, ret),
            "    call_original!(%s) // %s; add yours before or after" % (passed, subject),
            "}",
        ]))
    return names, blocks


def smashline_source(state: dict, constant: str, resource: str, taken: set) -> tuple[list[str], list[str]]:
    """(lines for main, functions) for the picked entries Smashline 2.0 replaces: a fighter's
    own vtable and its articles' weapon vtables. The other tables have no Smashline call."""
    fighter_lines, weapon_lines, blocks = [], {}, []
    for hook in state.get("hooks") or []:
        slot = hook.get("slot")
        if not isinstance(slot, int):
            continue
        space, article = _space(hook.get("table", ""))
        path = smashline_slot(space, slot)
        sig = signature(space, slot) if path else None
        if not path or not sig["offered"] or (space == WEAPON and _article(state, article) is None):
            continue
        stem = "" if space == FIGHTER else article + "_"
        name = identifier("%s_%s%s" % (resource, stem, sig["name"] or "slot_%d" % slot))
        if name in taken:
            name = "%s_%d" % (name, slot)
        taken.add(name)
        params = ", ".join("%s: %s" % (param, kind) for param, kind in sig["params"])
        types = ", ".join(kind for _, kind in sig["params"])
        passed = ", ".join(param for param, _ in sig["params"])
        ret = " -> %s" % sig["ret"] if sig["ret"] else ""
        address = _address(space, state, article, slot)
        slot_text = "slot %d%s%s; signature %s" % (slot, (" " + sig["name"]) if sig["name"] else "",
                                                   (", base " + address) if address else "", sig["summary"])
        if space == FIGHTER:
            where = "fighter vtable"
            kind_of = "%s.kind().get().unwrap_or(-1)" % constant
            getter = "get_original_fighter_vtable"
            subject = "class is the class object, object the fighter"
            costumes = hook.get("costumes") or []
            if costumes:
                listed = ", ".join(str(costume) for costume in costumes)
                fighter_lines.append("    replace_fighter_vtable_costume(kind, Costume::from_vec(vec![%s]), %s, %s as usize); "
                                     "// costumes %s run only the entries that list them" % (listed, path, name, listed))
            else:
                fighter_lines.append("    replace_fighter_vtable(kind, %s, %s as usize);" % (path, name))
        else:
            where = "article %s weapon vtable" % article
            holder = "%s_%s_KIND" % (constant, identifier(article).upper())
            kind_of = "%s.load(core::sync::atomic::Ordering::Acquire)" % holder
            getter = "get_original_weapon_vtable"
            subject = "class is the class object, object the weapon"
            if article not in weapon_lines:
                weapon_lines[article] = (holder, [])
                blocks.append("static %s: core::sync::atomic::AtomicI32 = core::sync::atomic::AtomicI32::new(-1); "
                              "// the article's kind, from main" % holder)
            weapon_lines[article][1].append("        replace_weapon_vtable(weapon, %s, %s as usize);" % (path, name))
        blocks.append("\n".join([
            "// %s %s" % (where, slot_text),
            "unsafe extern \"C\" fn %s(%s)%s {" % (name, params, ret),
            "    let original: unsafe extern \"C\" fn(%s)%s = core::mem::transmute(%s(%s, %s));"
            % (types, ret, getter, kind_of, path),
            "    original(%s) // %s; add yours before or after" % (passed, subject),
            "}",
        ]))
    lines = list(fighter_lines)
    for article, (holder, replaced) in weapon_lines.items():
        lines.append("    if let Some(weapon) = %s.article(\"%s\").weapon_kind() { // the article's own kind" % (constant, article))
        lines.append("        %s.store(weapon, core::sync::atomic::Ordering::Release);" % holder)
        lines += replaced
        lines.append("    } else {")
        lines.append("        skyline::println!(\"[%s] article %s has no kind; its vtable entries stay the game's\");"
                     % (resource, article))
        lines.append("    }")
    if lines:
        lines.insert(0, "    // the entries picked on the Vtables tab, through Smashline 2.0 (%s)" % SMASHLINE_NEEDS)
    return lines, blocks


def enemy_hook_source(state: dict, upper: str, resource: str, taken: set) -> tuple[list[str], list[str]]:
    """(lines for main, functions) for an enemy's picked entries: enemies have no
    #[hook], so each is a function its main hands to set_vtable_entry or
    set_object_vtable_entry, calling the entry it replaced."""
    registrations, blocks = [], []
    driven = enemy_base(state) == "nabbit"
    for hook in state.get("hooks") or []:
        space = hook.get("table", "")
        slot = hook.get("slot")
        if space not in (ENEMY, ENEMY_OBJECT) or not isinstance(slot, int):
            continue
        sig = signature(space, slot)
        if not sig["offered"]:
            continue
        object_table = space == ENEMY_OBJECT
        module = "object_slot::" if object_table else "slot::"
        slot_path = ENEMY_API + module + sig["constant"] if sig["constant"] else str(slot)
        name = identifier("%s_%s%s" % (resource, "object_" if object_table else "", sig["name"] or "slot_%d" % slot))
        if name in taken:
            name = "%s_%d" % (name, slot)
        taken.add(name)
        params = ", ".join("%s: %s" % (param, kind) for param, kind in sig["params"])
        types = ", ".join(kind for _, kind in sig["params"])
        passed = ", ".join(param for param, _ in sig["params"])
        ret = " -> %s" % sig["ret"] if sig["ret"] else ""
        fallback = "0.0" if sig["ret"] == "f64" else "0"
        address = _address(space, state, "", slot)
        if object_table:
            original = "%soriginal_object_entry(%s)" % (ENEMY_API, slot_path)
            setter = "set_object_vtable_entry"
            where = "enemy object vtable"
            subject = "object is the enemy's battle object"
        else:
            original = "%soriginal_entry(%s_KIND.load(core::sync::atomic::Ordering::Acquire), %s)" % (
                ENEMY_API, upper, slot_path)
            setter = "set_vtable_entry"
            where = "enemy class vtable"
            subject = "instance is the enemy's class instance"
        routed = " (a driven clone's original is the engine's routing to its driver)" \
            if driven and not object_table and slot in ROUTED else ""
        registrations.append("        let _ = %s%s(kind, %s, %s as *const ()); // %s slot %d of this clone"
                             % (ENEMY_API, setter, slot_path, name, where, slot))
        blocks.append("\n".join([
            "// %s slot %d%s%s; signature %s%s" % (where, slot, (" " + sig["name"]) if sig["name"] else "",
                                                 (", base " + address) if address else "", sig["summary"], routed),
            "unsafe extern \"C\" fn %s(%s)%s {" % (name, params, ret),
            "    let Some(original) = %s else {" % original,
            "        return %s;" % fallback,
            "    };",
            "    let original: unsafe extern \"C\" fn(%s)%s = core::mem::transmute(original);" % (types, ret),
            "    original(%s) // %s; add yours before or after" % (passed, subject),
            "}",
            ""]))
    return registrations, blocks
