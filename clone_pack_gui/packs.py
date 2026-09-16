#!/usr/bin/env python3
"""What a pack folder is, what it ships, and how its manifest is read and written."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import backups

FIGHTER = "fighter"
ITEM = "item"
STAGE = "stage"
UNKNOWN = "unknown"
KINDS = (FIGHTER, ITEM, STAGE)

STATE_FILE = "clone_pack_gui.json"
NON_ASSET_SUFFIXES = {"yml", "yaml", "lua", "md", "txt", "json", "toml", "py",
                      "gitkeep", "nro", "zip", "bak"}
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


def detect_kinds(folder: Path) -> list[str]:
    """Every kind this folder ships. One pack may carry a fighter, an item and a stage."""
    folder = Path(folder)
    found = []
    for kind, manifest in ((FIGHTER, None), (ITEM, "item.toml"), (STAGE, "stage.toml")):
        if (folder / kind).is_dir() or (manifest and (folder / manifest).is_file()):
            found.append(kind)
    return found


def detect(folder: Path) -> str:
    """The kind to show first, or `unknown` for a folder that ships none."""
    found = detect_kinds(folder)
    return found[0] if found else UNKNOWN


def manifest_name(kind: str) -> str | None:
    return {ITEM: "item.toml", STAGE: "stage.toml"}.get(kind)


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
    """Arc paths this pack ships, the same set the generator declares."""
    folder = Path(folder)
    found = []
    for root, _, names in os.walk(folder):
        for name in names:
            suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if suffix in NON_ASSET_SUFFIXES:
                continue
            relative = Path(root, name).relative_to(folder).as_posix()
            if "/" in relative:
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
    for resource in own_fighters:
        part = {"resource_name": resource, "declare_shipped": True}
        numbers = costumes(folder, FIGHTER, resource)
        if numbers:
            part["color_start"] = numbers[0]
            part["color_count"] = numbers[-1] - numbers[0] + 1
            notes.append("costumes c%02d to c%02d" % (numbers[0], numbers[-1]))
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
        if (folder / FIGHTER / resource / "param").is_dir():
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
