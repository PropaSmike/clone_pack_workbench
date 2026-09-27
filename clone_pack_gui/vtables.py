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
    for space in (FIGHTER, WEAPON, ITEM, "common"):
        table: dict = {}
        path = DATA / ("vtable_%s.tsv" % space)
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                label, _, entries = line.partition("\t")
                table[label] = entries.split(" ") if entries else []
        grids[space] = table
    _cache.update({"slots": slots, "grids": grids})
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
    return []


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
    else:
        row = None
    if not row or slot >= len(row):
        return ""
    entry = row[slot]
    if space in (FIGHTER, WEAPON, ITEM):
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
    first = [("item", "u64")] if space == ITEM else [("class", "u64"), ("object", "u64")]
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
                    "signature": describe(sig), "offered": sig["offered"], "note": note})
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
