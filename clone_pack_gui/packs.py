#!/usr/bin/env python3
"""What a pack folder is, what it ships, and how its manifest is read and written."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from .emit import engine_param_lines

from . import backups

FIGHTER = "fighter"
ITEM = "item"
STAGE = "stage"
UNKNOWN = "unknown"
KINDS = (FIGHTER, ITEM, STAGE)

STATE_FILE = "clone_pack_gui.json"
NON_ASSET_SUFFIXES = {"yml", "yaml", "lua", "md", "txt", "json", "toml", "py",
                      "gitkeep", "nro", "zip", "bak", "prcxml", "xmsbt", "msbt",
                      "stprmxml", "stdatxml", "prcx", "xml", "png", "jpg", "jpeg",
                      "psd", "7z", "rar", "ini"}
PATCH_FOLDER_SUFFIXES = (".nus3audio", ".nus3bank")
COSTUME_NAME_RE = re.compile(r"_c(\d{2,3})(?=[_.])")
ADDED_SLOT_LEFTOVERS = ("ui/param/database/ui_chara_db.prcxml",)
COLOR_RE = re.compile(r"/c(\d{2,3})(?=/|$)")
LABEL_RE = re.compile(r'label="([^"]+)"\s*>\s*<text>(.*?)</text>', re.S)
COPY_RE = re.compile(r"^copy_(.+?)_(.+)$")
ARTICLE_SKIP = {"body", "kirbycopy", "cmn"}
MESSAGE_FILE = ("ui", "message", "msg_name.xmsbt")
ASSIGN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")

ITEM_KEYS = ("base_kind", "resource_name", "base_item", "agent_name", "ui_id",
             "training_order", "spawn_per", "spawn_min", "spawn_max", "spawn_from")
STAGE_KEYS = ("place", "display_name", "id_name", "forms", "ships_battle_tree",
              "series", "disp_order", "donor", "resource_place", "bgm",
              "bgm_setting_no", "bgm_selector", "content_donor", "content_donor_tree",
              "carry_donor_scenery")
STAGE_ENGINE_KEYS = ("place", "display_name", "id_name", "forms", "ships_battle_tree",
                     "series", "disp_order", "donor", "resource_place", "bgm",
                     "bgm_setting_no", "bgm_selector")
FIGHTER_KEYS = ("name", "base", "display_name", "costumes", "color_start", "series",
                "disp_order", "narration", "staffroll", "css", "ui_chara", "fighter_kind_name",
                "owns_param_resources")
FIGHTER_MANIFEST = "fighter.toml"


def detect_kinds(folder: Path) -> list[str]:
    """Every kind this folder ships. One pack may carry a fighter, an item and a stage."""
    folder = Path(folder)
    found = []
    for kind, manifest in ((FIGHTER, FIGHTER_MANIFEST), (ITEM, "item.toml"), (STAGE, "stage.toml")):
        if (folder / kind).is_dir() or (manifest and (folder / manifest).is_file()):
            found.append(kind)
    return found


def detect(folder: Path) -> str:
    """The kind to show first, or `unknown` for a folder that ships none."""
    found = detect_kinds(folder)
    return found[0] if found else UNKNOWN


def manifest_name(kind: str) -> str | None:
    return {ITEM: "item.toml", STAGE: "stage.toml", FIGHTER: FIGHTER_MANIFEST}.get(kind)


def header_of(line: str) -> str | None:
    """The table a header line opens, `[[article]]` and `[kirby]` alike, else None."""
    text = strip_comment(line).strip()
    if text.startswith("[[") and text.endswith("]]"):
        return "[[%s]]" % text[2:-2].strip()
    if text.startswith("[") and text.endswith("]"):
        return "[%s]" % text[1:-1].strip()
    return None


def split_sections(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """The lines before the first table header, then (header, lines) per table."""
    head: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in lines:
        header = header_of(line)
        if header:
            sections.append((header, []))
        elif sections:
            sections[-1][1].append(line)
        else:
            head.append(line)
    return head, sections


def weapon_short_name(owner: str, const: str) -> str:
    """`WEAPON_KIND_SIMON_CROSS` with owner simon is `cross`."""
    prefix = "WEAPON_KIND_%s_" % owner.upper()
    if const.upper().startswith(prefix):
        return const[len(prefix):].lower()
    if const.upper().startswith("WEAPON_KIND_"):
        return const[len("WEAPON_KIND_"):].lower()
    return const.lower()


def fighter_manifest_values(state: dict) -> dict:
    """The fighter.toml keys a fighter part holds, in the names the engine reads."""
    values: dict = {}
    resource = state.get("resource_name") or ""
    if resource:
        values["name"] = resource
    base = state.get("base_resource_name") or state.get("base_fighter") or ""
    if base:
        values["base"] = base
    for key in ("display_name", "series", "narration", "ui_chara", "fighter_kind_name"):
        if state.get(key):
            values[key] = state[key]
    if isinstance(state.get("color_count"), int) and state["color_count"] > 0:
        values["costumes"] = state["color_count"]
    if isinstance(state.get("color_start"), int) and state["color_start"] > 0:
        values["color_start"] = state["color_start"]
    if isinstance(state.get("disp_order"), int):
        values["disp_order"] = state["disp_order"]
    if state.get("staffroll"):
        values["staffroll"] = True
    if state.get("own_css"):
        values["css"] = False
    if state.get("owns_param_resources"):
        values["owns_param_resources"] = True
    return values


def fighter_article_lines(articles) -> list[str]:
    """One [[article]] table per source the pack names, minted from its weapon."""
    out: list[str] = []
    for article in articles or ():
        owner = article.get("owner")
        weapon = article.get("weapon")
        name = article.get("name")
        if not (owner and weapon and name):
            continue
        out += ["", "[[article]]", "%-13s = %s" % ("name", format_value(name)),
                "%-13s = %s" % ("from", format_value("%s/%s" % (owner, weapon_short_name(owner, weapon))))]
        if article.get("kirby_copy"):
            out.append("%-13s = %s" % ("kirby", "true"))
    return out


def fighter_kirby_lines(state: dict, existing: list[str] | None) -> list[str]:
    """The [kirby] table: what the panel knows, over the lines already there."""
    values: dict = {}
    statuses = state.get("kirby_statuses")
    if isinstance(statuses, int) and statuses > 0:
        values["statuses"] = statuses
    if state.get("kirby_copy_full_model"):
        values["full_model"] = True
    if not values and not existing:
        return []
    lines, _ = merge_lines(list(existing or []), values, ("statuses", "full_model"))
    return ["", "[kirby]"] + [line for line in lines if line.strip()]


def write_fighter_manifest(path: Path, state: dict) -> list[str]:
    """fighter.toml from a fighter part: the flat keys in the head, the articles
    the panel lists as [[article]] tables, [kirby] merged, every other table
    ([params], [[kirby.motion]], ...) kept as written."""
    path = Path(path)
    values = fighter_manifest_values(state)
    lines = (path.read_text(encoding="utf-8", errors="replace").splitlines()
             if path.is_file() else [])
    head, sections = split_sections(lines)
    fighter_lines = []
    others = []
    kirby_existing = None
    param_lines = engine_param_lines(state)
    for header, body in sections:
        if header == "[fighter]":
            fighter_lines += body
        elif header == "[[article]]":
            continue
        elif header == "[kirby]":
            kirby_existing = body
        elif header in ("[params]", "[params.mul]") and param_lines:
            continue
        else:
            others.append((header, body))
    head, written = merge_lines(head + fighter_lines, values, FIGHTER_KEYS)
    while head and not head[-1].strip():
        head.pop()
    out = list(head)
    out += fighter_article_lines(state.get("articles"))
    out += fighter_kirby_lines(state, kirby_existing)
    out += param_lines
    for header, body in others:
        out += ["", header] + body
    text = "\n".join(out).rstrip("\n") + "\n"
    backups.keep(path)
    path.write_text(text, encoding="utf-8", newline="\n")
    return sorted(written)


def write_item_tables(path: Path, table_lines: list[str]) -> bool:
    """Replace the [common] and [owner_params] tables of a flat item.toml with
    these lines, keeping the flat keys and every other line. A file with
    [[item]] blocks is left alone, since a table would belong to one block."""
    path = Path(path)
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if any(is_header(line, "item") for line in lines):
        return False
    head, sections = split_sections(lines)
    kept = [(header, body) for header, body in sections
            if header not in ("[common]", "[owner_params]", "[item.common]", "[item.owner_params]")]
    while head and not head[-1].strip():
        head.pop()
    out = list(head) + list(table_lines)
    for header, body in kept:
        out += ["", header] + body
    text = "\n".join(out).rstrip("\n") + "\n"
    backups.keep(path)
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def read_fighter_manifests(path: Path) -> list[dict]:
    """Every fighter a fighter.toml declares: one flat, or one per [[fighter]]."""
    path = Path(path)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    head, blocks = split_blocks(lines, "fighter")
    if not blocks:
        found = fighter_manifest_from_lines(lines)
        return [found] if found else []
    out = []
    for block in blocks:
        found = fighter_manifest_from_lines(
            [line.replace("[[fighter.", "[[").replace("[fighter.", "[") for line in block])
        if found:
            out.append(found)
    return out


def read_fighter_manifest(path: Path) -> dict:
    found = read_fighter_manifests(path)
    return found[0] if found else {}


def fighter_manifest_from_lines(lines: list[str]) -> dict:
    """The flat fighter keys and the [[article]] tables of a fighter.toml, in the
    panel's names, so a pack written by hand loads into the window."""
    head, sections = split_sections(lines)
    values = parse_lines(head)
    articles = []
    for header, body in sections:
        if header == "[fighter]":
            values.update(parse_lines(body))
        elif header == "[[article]]":
            article = parse_lines(body)
            source = str(article.get("from") or "")
            owner, _, weapon = source.partition("/")
            if article.get("name") and owner and weapon:
                articles.append({"owner": owner,
                                 "weapon": "WEAPON_KIND_%s_%s" % (owner.upper(), weapon.upper()),
                                 "name": article["name"],
                                 "kirby_copy": bool(article.get("kirby"))})
        elif header == "[kirby]":
            kirby = parse_lines(body)
            if isinstance(kirby.get("statuses"), int):
                values["kirby_statuses"] = kirby["statuses"]
            if kirby.get("full_model"):
                values["kirby_copy_full_model"] = True
    state: dict = {}
    if values.get("name"):
        state["resource_name"] = values["name"]
    if values.get("base"):
        state["base_resource_name"] = values["base"]
    if isinstance(values.get("costumes"), int):
        state["color_count"] = values["costumes"]
    if isinstance(values.get("color_count"), int):
        state["color_count"] = values["color_count"]
    if isinstance(values.get("color_start"), int):
        state["color_start"] = values["color_start"]
    for key in ("display_name", "series", "narration", "ui_chara", "fighter_kind_name",
                "disp_order", "staffroll", "owns_param_resources", "kirby_statuses",
                "kirby_copy_full_model"):
        if key in values:
            state[key] = values[key]
    if "css" in values:
        state["own_css"] = values["css"] is False
    if articles:
        state["articles"] = articles
    return state


def manifest_table(kind_or_path) -> str:
    """The [[table]] header that separates one declaration from the next."""
    name = Path(str(kind_or_path)).name
    return {"item.toml": "item", "stage.toml": "stage"}.get(name, name)


def identity_key(kind_or_path) -> str:
    return "place" if manifest_table(kind_or_path) == "stage" else "resource_name"


def identity(section: dict, kind_or_path) -> str:
    return str(section.get(identity_key(kind_or_path)) or "")


def strip_comment(text: str) -> str:
    """Everything before a # that is not inside a quoted string."""
    quote = ""
    for index, character in enumerate(text):
        if quote:
            if character == quote:
                quote = ""
        elif character in "\"'":
            quote = character
        elif character == "#":
            return text[:index]
    return text


def parse_value(text: str):
    """One toml scalar or string list, enough for the manifests we write."""
    text = strip_comment(text).strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1]
        return [part.strip().strip("\"'") for part in inner.split(",") if part.strip()]
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text in ("true", "false"):
        return text == "true"
    try:
        return int(text, 0)
    except ValueError:
        return text


def format_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join('"%s"' % str(item) for item in value) + "]"
    return '"%s"' % str(value)


def is_header(line: str, table: str) -> bool:
    return strip_comment(line).strip() == "[[%s]]" % table


def split_blocks(lines: list[str], table: str) -> tuple[list[str], list[list[str]]]:
    """The lines before the first [[table]] header, then the lines of each block."""
    head: list[str] = []
    blocks: list[list[str]] = []
    for line in lines:
        if is_header(line, table):
            blocks.append([])
        elif blocks:
            blocks[-1].append(line)
        else:
            head.append(line)
    return head, blocks


def parse_lines(lines) -> dict:
    """Every assignment in these lines, ignoring comments and table headers."""
    values: dict = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        match = ASSIGN_RE.match(line)
        if match:
            values[match.group(1)] = parse_value(match.group(2))
    return values


def read_manifests(path: Path) -> list[dict]:
    """Every declaration in a manifest: one for a flat file, one per [[table]]."""
    path = Path(path)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    head, blocks = split_blocks(lines, manifest_table(path))
    if not blocks:
        return [parse_lines(head)]
    return [parse_lines(block) for block in blocks]


def read_manifest(path: Path) -> dict:
    """The first declaration, for a caller that handles one part."""
    found = read_manifests(path)
    return found[0] if found else {}


def merge_lines(lines: list[str], values: dict, order=()) -> tuple[list[str], set]:
    """Set these keys in place, keep every other line, append what is new."""
    lines = list(lines)
    written = set()
    for index, line in enumerate(lines):
        match = ASSIGN_RE.match(line)
        if not match:
            continue
        key = match.group(1)
        if key in values and key not in written:
            lines[index] = "%-13s = %s" % (key, format_value(values[key]))
            written.add(key)
    missing = [key for key in (order or values) if key in values and key not in written]
    if missing and lines and lines[-1].strip():
        lines.append("")
    for key in missing:
        lines.append("%-13s = %s" % (key, format_value(values[key])))
    return lines, written | set(missing)


def write_manifest(path: Path, values: dict, order=()) -> list[str]:
    """One declaration written flat, the form every engine reads."""
    path = Path(path)
    lines = (path.read_text(encoding="utf-8", errors="replace").splitlines()
             if path.is_file() else [])
    lines, written = merge_lines(lines, values, order)
    text = "\n".join(lines).rstrip("\n") + "\n"
    backups.keep(path)
    path.write_text(text, encoding="utf-8", newline="\n")
    return sorted(written)


def write_manifests(path: Path, sections: list[dict], order=()) -> list[str]:
    """Every declaration of the pack. One is written flat; several become one
    [[table]] block each, matched to the blocks already there by name so the
    lines a maker added by hand stay with their part."""
    path = Path(path)
    table = manifest_table(path)
    if not sections:
        return []
    lines = (path.read_text(encoding="utf-8", errors="replace").splitlines()
             if path.is_file() else [])
    head, blocks = split_blocks(lines, table)
    if not blocks and parse_lines(head):
        blocks, head = [head], []
    known = {identity(parse_lines(block), table): block for block in blocks}
    while head and not head[-1].strip():
        head.pop()
    if len(sections) == 1:
        flat, written = merge_lines(head + known.get(identity(sections[0], table), []),
                                    sections[0], order)
        text = "\n".join(flat).rstrip("\n") + "\n"
        backups.keep(path)
        path.write_text(text, encoding="utf-8", newline="\n")
        return sorted(written)
    out = list(head)
    written = set()
    for section in sections:
        block, done = merge_lines(known.get(identity(section, table), []), section, order)
        written |= done
        while block and not block[0].strip():
            block.pop(0)
        while block and not block[-1].strip():
            block.pop()
        if out:
            out.append("")
        out.append("[[%s]]" % table)
        out.extend(block)
    text = "\n".join(out).rstrip("\n") + "\n"
    backups.keep(path)
    path.write_text(text, encoding="utf-8", newline="\n")
    return sorted(written)


def shipped_files(folder: Path) -> list[str]:
    """Arc paths this pack ships, the same set the generator declares: no
    patches (prcxml, xmsbt, tones inside a `<bank>.nus3audio/` folder), no
    dot-prefixed paths (ARCropolis skips them), no sources or pictures."""
    folder = Path(folder)
    found = []
    for root, _, names in os.walk(folder):
        for name in names:
            suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if suffix in NON_ASSET_SUFFIXES:
                continue
            relative = Path(root, name).relative_to(folder).as_posix()
            parts = relative.split("/")
            if "/" not in relative or any(part.startswith(".") for part in parts) \
                    or any(part.lower().endswith(PATCH_FOLDER_SUFFIXES) for part in parts[:-1]):
                continue
            found.append(relative)
    return sorted(found)


def summarize(folder: Path) -> dict:
    """Counts a maker can read at a glance: trees, costumes, article directories."""
    files = shipped_files(folder)
    kinds = detect_kinds(folder)
    trees: dict[str, int] = {}
    colors: dict[str, int] = {}
    article_dirs = set()
    for path in files:
        trees[path.split("/", 1)[0]] = trees.get(path.split("/", 1)[0], 0) + 1
        match = COLOR_RE.search("/" + path)
        if match:
            colors[match.group(1)] = colors.get(match.group(1), 0) + 1
        parts = path.split("/")
        if len(parts) > 3 and parts[0] == "fighter" and parts[2] in ("model", "motion") \
                and parts[3] not in ARTICLE_SKIP and not parts[3].startswith("copy_"):
            article_dirs.add("%s/%s" % (parts[1], parts[3]))
    return {
        "files": len(files),
        "kinds": kinds,
        "manifests": [name for name in ("item.toml", "stage.toml")
                      if (Path(folder) / name).is_file()],
        "trees": dict(sorted(trees.items())),
        "colors": sorted(colors),
        "color_counts": colors,
        "articles": sorted(article_dirs),
        "config": (Path(folder) / "config.json").is_file(),
        "plugin": (Path(folder) / "plugin.nro").is_file(),
    }


def config_summary(folder: Path) -> dict:
    """What the pack's existing config.json declares, or an empty report."""
    path = Path(folder) / "config.json"
    if not path.is_file():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        return {"error": str(error)}
    groups = config.get("new-dir-files", {}) or {}
    return {
        "new-dir-infos": len(config.get("new-dir-infos", []) or []),
        "new-dir-infos-base": len(config.get("new-dir-infos-base", {}) or {}),
        "share-to-vanilla": len(config.get("share-to-vanilla", {}) or {}),
        "new-dir-files": len(groups),
        "declared": sum(len(members) for members in groups.values()),
    }


def read_state(folder: Path) -> dict:
    """The parts of each kind that hold what no manifest can, as lists. A file
    from before there were several parts per kind, or before there were kinds,
    reads as one part."""
    sections: dict = {kind: [] for kind in KINDS}
    path = Path(folder) / STATE_FILE
    if not path.is_file():
        return sections
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return sections
    if any(isinstance(raw.get(kind), (dict, list)) for kind in KINDS):
        for kind in KINDS:
            if isinstance(raw.get(kind), dict):
                sections[kind] = [raw[kind]]
            elif isinstance(raw.get(kind), list):
                sections[kind] = [part for part in raw[kind] if isinstance(part, dict)]
        return sections
    first = detect(folder)
    sections[first if first != UNKNOWN else FIGHTER] = [raw]
    return sections


def write_state(folder: Path, sections: dict) -> Path:
    """Write the parts that hold something, a list per kind."""
    kept = {kind: [part for part in parts if part]
            for kind, parts in sections.items() if any(parts)}
    path = Path(folder) / STATE_FILE
    backups.keep(path)
    path.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def own_names(folder: Path, tree: str, vanilla) -> list[str]:
    """The names under a tree that are not a vanilla owner's, so the pack's own."""
    root = Path(folder) / tree
    if not root.is_dir():
        return []
    return sorted(entry.name for entry in root.iterdir()
                  if entry.is_dir() and entry.name not in set(vanilla))


def costumes(folder: Path, tree: str, resource: str) -> list[int]:
    """The cNN numbers this pack actually ships for one owner."""
    root = Path(folder) / tree / resource
    found = set()
    if root.is_dir():
        for path in root.rglob("c[0-9][0-9]*"):
            if path.is_dir() and path.name[1:].isdigit() and len(path.name) <= 4:
                found.add(int(path.name[1:]))
    return sorted(found)


def vanilla_slot_names(folder: Path, tree: str, vanilla) -> list[str]:
    """Vanilla owners whose own body this pack ships under their own name: an
    added-slot moveset, the shape every community pack has before it becomes
    a clone. `fighter/kirby` holding only `copy_*` hats does not count."""
    root = Path(folder) / tree
    if not root.is_dir():
        return []
    return sorted(entry.name for entry in root.iterdir()
                  if entry.is_dir() and entry.name in set(vanilla)
                  and ((entry / "model" / "body").is_dir() or (entry / "motion" / "body").is_dir()))


def body_costumes(folder: Path, resource: str) -> list[int]:
    """The costume numbers of the fighter's body model, the reference every
    other part of the pack is numbered against; every cNN under the fighter
    when no body is shipped."""
    root = Path(folder) / FIGHTER / resource / "model" / "body"
    found = set()
    if root.is_dir():
        for entry in root.iterdir():
            if entry.is_dir() and entry.name[1:].isdigit() and 3 <= len(entry.name) <= 4:
                found.add(int(entry.name[1:]))
    return sorted(found) or costumes(folder, FIGHTER, resource)


def costume_paths(folder: Path, resource: str):
    """(relative path, number, kind) for every path of this fighter's that
    carries a costume: `cNN` directories under its trees, its camera, its
    Kirby copy models and body animations, and `_cNN` in the names of its
    sound banks, one-slot effects and trail textures. kind is "dir" or
    "file"."""
    folder = Path(folder)
    found = []
    dir_roots = [Path(FIGHTER, resource), Path("camera", FIGHTER, resource)]
    kirby = folder / FIGHTER / "kirby"
    for tree in ("model", "motion"):
        for entry in (kirby / tree).glob("copy_%s_*" % resource) if (kirby / tree).is_dir() else []:
            dir_roots.append(entry.relative_to(folder))
    if (kirby / "motion" / (resource + "body")).is_dir():
        dir_roots.append(Path(FIGHTER, "kirby", "motion", resource + "body"))
    effect = folder / "effect" / FIGHTER / resource
    if effect.is_dir():
        for entry in effect.iterdir():
            if entry.is_dir() and re.fullmatch(r"trail_c\d{2,3}", entry.name):
                found.append((entry.relative_to(folder).as_posix(),
                              int(entry.name.rsplit("_c", 1)[1]), "dir"))
        for entry in effect.rglob("*"):
            if entry.is_file() and COSTUME_NAME_RE.search(entry.name) \
                    and (entry.name.startswith("ef_%s_" % resource) or entry.parent.name == "trail"):
                found.append((entry.relative_to(folder).as_posix(),
                              int(COSTUME_NAME_RE.search(entry.name).group(1)), "file"))
    for root in dir_roots:
        base = folder / root
        if not base.is_dir():
            continue
        for entry in base.rglob("c[0-9][0-9]*"):
            relative = entry.relative_to(folder).as_posix()
            if entry.is_dir() and entry.name[1:].isdigit() and 3 <= len(entry.name) <= 4 \
                    and not any(part.startswith(".") for part in relative.split("/")):
                found.append((relative, int(entry.name[1:]), "dir"))
    for bank, prefix in (("fighter", "se_"), ("fighter_voice", "vc_")):
        base = folder / "sound" / "bank" / bank
        if not base.is_dir():
            continue
        for entry in base.iterdir():
            if (entry.is_file() or entry.name.lower().endswith(PATCH_FOLDER_SUFFIXES)) \
                    and entry.name.startswith(prefix + resource + "_") \
                    and COSTUME_NAME_RE.search(entry.name):
                found.append((entry.relative_to(folder).as_posix(),
                              int(COSTUME_NAME_RE.search(entry.name).group(1)), "file"))
    return sorted(set(found))


def renumbered(relative: str, kind: str, new: int) -> str:
    """The same path with its costume replaced."""
    head, _, name = relative.rpartition("/")
    if kind == "dir":
        name = re.sub(r"^(trail_)?c\d{2,3}$", lambda m: "%sc%02d" % (m.group(1) or "", new), name)
    else:
        name = COSTUME_NAME_RE.sub("_c%02d" % new, name, count=1)
    return head + "/" + name if head else name


def renumber_plan(folder: Path, resource: str) -> dict:
    """Move the fighter's costumes to c00, c01, ... in the order the body ships
    them: the engine's select screen offers costumes from c00, so a pack at
    c120-c127 (every added-slot moveset) must become c00-c07 before it can
    load. moves: (from, to) in the order to apply; kept: paths already in
    range that the body does not number; unmapped: numbers past the range
    that nothing maps, left alone; blocked: moves whose target exists;
    effect: the one-slot effect copied to the main name, if any; leftovers:
    added-slot files a clone must not ship."""
    folder = Path(folder)
    body = body_costumes(folder, resource)
    mapping = {old: rank for rank, old in enumerate(body)}
    moves, kept, unmapped, blocked = [], [], [], []
    targets = set()
    for relative, number, kind in sorted(costume_paths(folder, resource), key=lambda t: (t[1], t[0])):
        if number in mapping:
            new = mapping[number]
            if new == number:
                continue
            target = renumbered(relative, kind, new)
            if (folder / target).exists() and target not in targets:
                blocked.append((relative, target))
            else:
                moves.append((relative, target))
                targets.add(target)
        elif number < len(mapping):
            kept.append(relative)
        else:
            unmapped.append(relative)
    effect = None
    main = Path("effect", FIGHTER, resource, "ef_%s.eff" % resource)
    if not (folder / main).is_file():
        slots = sorted(((folder / "effect" / FIGHTER / resource).glob("ef_%s_c*.eff" % resource)
                        if (folder / "effect" / FIGHTER / resource).is_dir() else []),
                       key=lambda path: (int(COSTUME_NAME_RE.search(path.name).group(1))
                                         if COSTUME_NAME_RE.search(path.name) else 0, path.name))
        if slots:
            effect = (slots[0].relative_to(folder).as_posix(), main.as_posix())
    leftovers = [name for name in ADDED_SLOT_LEFTOVERS if (folder / name).is_file()]
    return {"resource": resource, "mapping": mapping, "moves": moves, "kept": kept,
            "unmapped": unmapped, "blocked": blocked, "effect": effect,
            "leftovers": leftovers}


def apply_renumber(folder: Path, plan: dict) -> list[str]:
    """Copy the one-slot effect to the main name, move the paths lowest
    costume first (targets are always lower than sources, so nothing is
    overwritten), keep and remove the leftovers, and set the manifest's and
    the saved state's first costume to 0. config.json is not touched: write
    it again."""
    folder = Path(folder)
    lines = []
    if plan.get("effect"):
        source, target = plan["effect"]
        shutil.copy2(folder / source, folder / target)
        lines.append("copied %s to %s (the engine loads the main name)" % (source, target))
    for source, target in plan["moves"]:
        destination = folder / target
        if destination.exists():
            lines.append("left %s alone: %s already exists" % (source, target))
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        (folder / source).rename(destination)
        lines.append("moved %s -> %s" % (source, target))
    for source, target in plan["blocked"]:
        lines.append("left %s alone: %s already exists" % (source, target))
    for relative in plan["unmapped"]:
        lines.append("left %s alone: no body costume maps its number" % relative)
    for name in plan.get("leftovers", []):
        backups.remove(folder / name, folder)
        lines.append("removed %s (a clone's select screen row comes from the manifest "
                     "or the plugin)" % name)
    resource = plan["resource"]
    manifest = folder / FIGHTER_MANIFEST
    if manifest.is_file():
        text = manifest.read_text(encoding="utf-8")
        edited = re.sub(r"(?m)^\s*color_start\s*=.*\n?", "", text)
        if edited != text:
            backups.keep(manifest, folder)
            manifest.write_text(edited, encoding="utf-8", newline="\n")
            lines.append("dropped color_start from %s" % FIGHTER_MANIFEST)
    sections = read_state(folder)
    changed = False
    for part in sections.get(FIGHTER, []):
        if part.get("resource_name") == resource and part.get("color_start"):
            part["color_start"] = 0
            changed = True
    if changed:
        write_state(folder, sections)
        lines.append("first costume set to 0 in %s" % STATE_FILE)
    if plan["moves"] or plan.get("effect"):
        lines.append("write config.json again: it still names the old costumes")
    return lines


NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
NAME_TEXT_SUFFIXES = {".toml", ".json", ".xmsbt", ".prcxml", ".xml"}
NAME_BINARY_SUFFIXES = {".nro", ".prc", ".nus3bank", ".nus3audio", ".eff", ".bntx"}
TREE_OF_KIND = {FIGHTER: "fighter", ITEM: "item", STAGE: "stage"}


def name_pattern(name: str) -> re.Pattern:
    """The name the way the game's paths and labels carry it: on its own between
    characters that are not letters or digits (fighter/wawa/, vc_wawa_c00,
    nam_chr1_00_wawa, ui_chara_wawa), or run into the dNN of a Kirby copy
    animation (wawad00specialn.nuanmb). wawaman is another name."""
    escaped = re.escape(name)
    return re.compile(r"(?<![a-z0-9])%s(?![a-z0-9])|(?<![a-z0-9])%s(?=d\d\d[a-z])"
                      % (escaped, escaped))


def read_text_any(path: Path) -> tuple[str, str]:
    """A text file and the encoding it was in; xmsbt is UTF-16 with a mark."""
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    return raw.decode("utf-8"), "utf-8"


def rename_plan(folder: Path, old: str, new: str) -> dict:
    """Everything in the pack that carries the old name. moves: (from, to) for
    every file and directory whose own name holds it, deepest first so a file
    moves before its folder does. edits: the text files that mention it
    (config.json, the manifests, the saved state, msg_name.xmsbt, prcxml).
    stuck: binary files that hold it and need a rebuild or a hand edit."""
    folder = Path(folder)
    pattern = name_pattern(old)
    moves, edits, stuck = [], [], []
    for path in sorted(folder.rglob("*"), key=lambda entry: len(entry.parts), reverse=True):
        relative = path.relative_to(folder)
        if path.is_file():
            suffix = path.suffix.lower()
            if suffix in NAME_TEXT_SUFFIXES:
                try:
                    text, _ = read_text_any(path)
                except UnicodeDecodeError:
                    text = ""
                if pattern.search(text):
                    edits.append(relative)
            elif suffix in NAME_BINARY_SUFFIXES and pattern.search(
                    path.read_bytes().decode("latin-1")):
                stuck.append(relative)
        if pattern.search(path.name):
            moves.append((relative, relative.with_name(pattern.sub(new, path.name))))
    edits.sort()
    stuck.sort()
    return {"old": old, "new": new, "moves": moves, "edits": edits, "stuck": stuck}


def rename_refusal(folder: Path, kind: str, old: str, new: str, vanilla) -> str:
    """Why this rename must not happen, or an empty string."""
    tree = TREE_OF_KIND[kind]
    if not NAME_RE.match(new or ""):
        return "the new name must be lowercase letters, digits and underscores, starting with a letter"
    if new == old:
        return "the new name is the old one"
    if new in set(vanilla):
        return "%s is a name the game already uses" % new
    if not (Path(folder) / tree / old).is_dir():
        return "%s/%s is not in this pack" % (tree, old)
    if (Path(folder) / tree / new).exists():
        return "%s/%s already exists" % (tree, new)
    return ""


def folder_summary(paths, limit: int = 6) -> list[str]:
    """These paths as a few lines: a folder holding several of them becomes one
    line with a count, and anything past `limit` lines becomes a last line
    saying how much was left out. A list of 76 UI textures does not fit in a
    message box."""
    groups: dict[str, list[str]] = {}
    for path in paths:
        text = path.as_posix() if isinstance(path, Path) else str(path).replace("\\", "/")
        head, _, name = text.rpartition("/")
        groups.setdefault(head, []).append(name)
    lines = []
    for head, names in groups.items():
        if len(names) == 1:
            lines.append("%s/%s" % (head, names[0]) if head else names[0])
        else:
            lines.append("%s/ (%d files)" % (head, len(names)))
    if len(lines) > limit:
        hidden = sum(len(names) for names in list(groups.values())[limit:])
        lines = lines[:limit] + ["and %d more in %d other folder(s)"
                                 % (hidden, len(lines) - limit)]
    return lines


def apply_rename(folder: Path, plan: dict) -> list[str]:
    """Edit the text files first (each kept in backups), then move deepest
    first. Returns one line per change, and one per file left alone."""
    folder = Path(folder)
    pattern = name_pattern(plan["old"])
    new = plan["new"]
    lines = []
    for relative in plan["edits"]:
        path = folder / relative
        text, encoding = read_text_any(path)
        changed, count = pattern.subn(new, text)
        backups.keep(path, folder)
        path.write_bytes(changed.encode(encoding))
        lines.append("edited %s (%d)" % (relative.as_posix(), count))
    for source, target in plan["moves"]:
        path = folder / source
        destination = folder / target
        if destination.exists():
            lines.append("left %s alone: %s already exists" % (source.as_posix(), target.name))
            continue
        path.rename(destination)
        lines.append("renamed %s -> %s" % (source.as_posix(), target.name))
    if plan["stuck"]:
        lines.append("%d file(s) still hold '%s' inside: rebuild or hand edit"
                     % (len(plan["stuck"]), plan["old"]))
        lines += ["    " + line for line in folder_summary(plan["stuck"], limit=12)]
    return lines


def messages(folder: Path) -> dict:
    """label to text from the pack's msg_name.xmsbt, whatever it is encoded as."""
    path = Path(folder).joinpath(*MESSAGE_FILE)
    if not path.is_file():
        return {}
    raw = path.read_bytes()
    for encoding in ("utf-16", "utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
        if "<entry" in text:
            return {label: value.strip()
                    for label, value in LABEL_RE.findall(text.replace("\x00", ""))}
    return {}


def read_config(folder: Path) -> dict:
    path = Path(folder) / "config.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def base_from_config(config: dict, tree: str, resource: str, vanilla) -> str | None:
    """Which vanilla owner this part is built on, as its config.json shows: the
    owner its own directories are based on or share from, counted for this
    resource alone, since a pack may hold several parts of one kind."""
    known = set(vanilla)
    counts: dict[str, int] = {}
    ours = "%s/%s/" % (tree, resource)

    def count(path) -> None:
        parts = str(path).split("/")
        if len(parts) > 1 and parts[0] == tree and parts[1] != resource:
            if not known or parts[1] in known:
                counts[parts[1]] = counts.get(parts[1], 0) + 1

    for own, donor in (config.get("new-dir-infos-base") or {}).items():
        if str(own).startswith(ours):
            count(donor)
    for key in ("share-to-vanilla", "share-to-added"):
        for source, targets in (config.get(key) or {}).items():
            if any(str(target).startswith(ours) for target in (targets or [])):
                count(source)
    if not counts:
        return None
    return max(sorted(counts), key=lambda name: counts[name])


def articles_on_disk(folder: Path, resource: str) -> list[str]:
    """Directory names beside `body` under the fighter's model and motion trees."""
    found = set()
    for tree in ("model", "motion"):
        root = Path(folder) / "fighter" / resource / tree
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if entry.is_dir() and entry.name not in ARTICLE_SKIP \
                    and not entry.name.startswith("copy_"):
                found.add(entry.name)
    return sorted(found)


def copy_suffixes(folder: Path, resource: str) -> list[str]:
    """The suffixes of any copy_<resource>_<suffix> directory the pack ships."""
    found = set()
    root = Path(folder) / "fighter"
    if not root.is_dir():
        return []
    for path in root.glob("*/model/copy_*"):
        match = COPY_RE.match(path.name)
        if match and match.group(1) == resource:
            found.add(match.group(2))
    return sorted(found)


def scan(folder: Path, fighters=(), items=(), places=()) -> dict:
    """What the folder itself says about each part, for pre-filling the forms.

    The vanilla name lists come from the arc index and are what tells a pack's
    own `fighter/wawa` from the `fighter/kirby` tree a copy model ships under.
    """
    folder = Path(folder)
    config = read_config(folder)
    text = messages(folder)
    found: dict = {kind: [] for kind in KINDS}
    notes: list[str] = []

    own_fighters = own_names(folder, FIGHTER, fighters)
    slot_fighters = vanilla_slot_names(folder, FIGHTER, fighters)
    found["vanilla_slot"] = slot_fighters
    for resource in slot_fighters:
        numbers = costumes(folder, FIGHTER, resource)
        notes.append("fighter/%s is %s's own tree%s: an added-slot moveset. Rename files "
                     "gives it the clone's name, then Renumber costumes moves it to c00"
                     % (resource, resource,
                        " at c%02d to c%02d" % (numbers[0], numbers[-1]) if numbers else ""))
    for resource in own_fighters:
        part = {"resource_name": resource, "declare_shipped": True}
        numbers = costumes(folder, FIGHTER, resource)
        if numbers:
            part["color_start"] = numbers[0]
            part["color_count"] = numbers[-1] - numbers[0] + 1
            notes.append("costumes c%02d to c%02d" % (numbers[0], numbers[-1]))
            if numbers[0] != 0 or len(numbers) != part["color_count"]:
                notes.append("%s's costumes do not run from c00 without a gap; the select "
                             "screen offers c00 to c%02d, so use Renumber costumes before "
                             "writing config.json" % (resource, len(numbers) - 1))
        for name in ADDED_SLOT_LEFTOVERS:
            if (folder / name).is_file():
                notes.append("%s is an added-slot leftover that patches the base's row; "
                             "Renumber costumes removes it" % name)
        base = base_from_config(config, FIGHTER, resource, fighters)
        if base:
            part["base_resource_name"] = base
            notes.append("built on %s, as config.json shows" % base)
        for label, value in text.items():
            if label.startswith("nam_chr1_") and (
                    len(own_fighters) == 1 or label.endswith("_" + resource)):
                stem = label.rsplit("_", 1)[-1]
                part["ui_chara"] = "ui_chara_%s" % stem
                notes.append('%s is named "%s" in msg_name.xmsbt' % (resource, value))
                break
        for stem in (folder / "ui" / "replace" / "chara").glob("chara_*/chara_*_*.bntx") \
                if (folder / "ui" / "replace" / "chara").is_dir() else []:
            middle = stem.stem.split("_")
            if len(middle) >= 4 and (len(own_fighters) == 1 or middle[2] == resource):
                part.setdefault("ui_chara", "ui_chara_%s" % middle[2])
                break
        if any((folder / FIGHTER / resource / "param").glob("*.prc")):
            part["owns_param_resources"] = True
            notes.append("ships its own param tree")
        names = articles_on_disk(folder, resource)
        if names:
            part["articles"] = [{"name": name, "owner": "", "weapon": ""}
                                for name in names]
            notes.append("article directories: %s" % ", ".join(names))
        suffixes = copy_suffixes(folder, resource)
        if suffixes:
            part["kirby_copy_suffix"] = ",".join(suffixes)
            notes.append("Kirby copy models under copy_%s_%s" % (resource, suffixes[0]))
        found[FIGHTER].append(part)
    if len(own_fighters) > 1:
        notes.append("fighter trees for %s" % ", ".join(own_fighters))

    own_items = own_names(folder, ITEM, items)
    for resource in own_items:
        part = {"resource_name": resource, "declare_shipped": True}
        base = base_from_config(config, ITEM, resource, items)
        if base:
            part["base_item"] = base
            notes.append("%s is built on %s" % (resource, base))
        found[ITEM].append(part)
    if len(own_items) > 1:
        notes.append("item trees for %s" % ", ".join(own_items))
    found["item_candidates"] = own_items

    own_places = own_names(folder, STAGE, places) or own_names(folder, STAGE, ())
    for place in own_places:
        part = {"place": place}
        tree = folder / STAGE / place
        part["ships_battle_tree"] = (tree / "battle").is_dir()
        if (tree / "normal").is_dir():
            part["forms"] = ["normal"]
        donor = base_from_config(config, STAGE, place, places)
        if donor:
            part["donor"] = donor
            notes.append("%s fills its gaps from %s" % (place, donor))
        for label, value in text.items():
            if label.startswith("nam_stg1_") and (
                    len(own_places) == 1 or label[len("nam_stg1_"):].lower() == place):
                part["id_name"] = label[len("nam_stg1_"):]
                part["display_name"] = value
                notes.append('%s is called "%s"' % (place, value))
                break
        found[STAGE].append(part)
    if len(own_places) > 1:
        notes.append("stage trees for %s" % ", ".join(own_places))

    found["notes"] = notes
    return found


def add_declaration(path: Path, values: dict, order=()) -> list[str]:
    """Put this part into the manifest beside the parts already declared there."""
    sections = read_manifests(path)
    name = identity(values, path)
    for index, known in enumerate(sections):
        if identity(known, path) == name or not identity(known, path):
            sections[index] = dict(known, **values)
            break
    else:
        sections.append(dict(values))
    return write_manifests(path, sections, order)


def scaffold(folder: Path, kind: str, values: dict) -> list[str]:
    """Create a new pack folder with the manifest and trees its kind needs."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    made = []
    resource = values.get("resource_name") or values.get("place") or "wawa"
    if kind == FIGHTER:
        for tree in ("model", "motion", "sound", "effect", "camera"):
            (folder / "fighter" / resource / tree).mkdir(parents=True, exist_ok=True)
        made.append("fighter/%s/{model,motion,sound,effect,camera}" % resource)
    elif kind == ITEM:
        for tree in ("model", "motion", "param", "script"):
            (folder / "item" / resource / tree).mkdir(parents=True, exist_ok=True)
        made.append("item/%s/{model,motion,param,script}" % resource)
        add_declaration(folder / "item.toml", values, ITEM_KEYS)
        made.append("item.toml")
    elif kind == STAGE:
        (folder / "stage" / resource / "normal").mkdir(parents=True, exist_ok=True)
        made.append("stage/%s/normal" % resource)
        add_declaration(folder / "stage.toml", values, STAGE_KEYS)
        made.append("stage.toml")
    info = folder / "info.toml"
    if not info.is_file():
        display = values.get("display_name") or resource
        info.write_text(
            'display_name = "%s"\nauthors = ""\nversion = "0.1.0"\n'
            'description = "Built with the Clone Engine pack workbench."\n' % display,
            encoding="utf-8", newline="\n")
        made.append("info.toml")
    return made
