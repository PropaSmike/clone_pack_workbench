#!/usr/bin/env python3
"""Generate an ARCropolis config.json for a fighter clone from the arc index."""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def default_arc_index() -> Path:
    """The arc index beside this script, or above it. SSBU_ARC_INDEX overrides."""
    override = os.environ.get("SSBU_ARC_INDEX")
    roots = [Path(override)] if override else []
    roots += [HERE / "arc_index", HERE.parent / "arc_index",
              HERE.parent.parent / "arc_index"]
    for root in roots:
        if (root / "arc_files.tsv").is_file():
            return root
    return roots[-1]


ARC_INDEX = default_arc_index()
ARC_FILES = ARC_INDEX / "arc_files.tsv"
ARC_DIRS = ARC_INDEX / "arc_dirs.tsv"


def _rows(source: Path, what: str):
    if not source.is_file():
        raise SystemExit(
            f"no arc index at {source}. Put {source.name} beside this script "
            f"under arc_index/, or set SSBU_ARC_INDEX to the directory holding it."
        )
    with source.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            value = line.split("\t", 1)[0].strip()
            if value:
                yield value


def arc_dirs():
    """Every directory in the index. Item trees have some that hold no files."""
    return _rows(ARC_DIRS, "arc_dirs.tsv")


def arc_paths():
    """Every file path in the index, whatever the column count."""
    return _rows(ARC_FILES, "arc_files.tsv")


VANILLA_COLORS = 8
DEFAULT_COLORS = list(range(VANILLA_COLORS))
FIGHTER_OWNED_TREES = ("finalsmash",)

NON_ASSET_SUFFIXES = {"yml", "yaml", "lua", "md", "txt", "json", "toml", "py", "gitkeep"}

COLOR_RE = re.compile(r"/c(\d{2,3})(?=/|$)")
SOUND_COLOR_RE = re.compile(r"_c(\d{2,3})(\.[^/]+)$")
COPY_MODEL_RE = re.compile(r"^fighter/kirby/model/copy_(.+?)_([^/]+)/")


def base_files(base: str) -> list[str]:
    """Every vanilla path a clone of `base` has to re-own, by prefix."""
    wanted = (
        f"fighter/{base}/model/",
        f"fighter/{base}/motion/",
        f"camera/fighter/{base}/",
        f"effect/fighter/{base}/",
    )
    out = []
    for path in arc_paths():
        if path.startswith(wanted):
            out.append(path)
        elif path.startswith(("sound/bank/fighter/", "sound/bank/fighter_voice/")):
            if re.search(rf"_{re.escape(base)}(?:_[a-z0-9]+)*_c\d\d\.", path.rsplit("/", 1)[-1]):
                out.append(path)
    return out


def uncovered_trees(base: str, covered: set[str]) -> dict[str, int]:
    """Base-owned paths the census does not carry, by top-level tree."""
    missed: dict[str, int] = collections.Counter()
    for path in arc_paths():
        if path in covered:
            continue
        head = path.split("/", 1)[0]
        if head in FIGHTER_OWNED_TREES and path.startswith(f"{head}/{base}/"):
            missed[head] += 1
    return dict(missed)


def split_color(path: str) -> tuple[str, int | None, str, str]:
    """(head, colour, tail, separator): the path with its costume lifted out, so
    `head + separator + cNN + tail` puts any costume back. Sound banks carry the
    costume in the file name, everything else as a directory."""
    if path.startswith("sound/bank/"):
        found = SOUND_COLOR_RE.search(path)
        if found:
            return path[:found.start()], int(found.group(1)), found.group(2), "_"
        return path, None, "", ""
    found = COLOR_RE.search(path)
    if found:
        return path[:found.start()], int(found.group(1)), path[found.end():], "/"
    return path, None, "", ""


def with_color(head: str, color: int, tail: str, separator: str) -> str:
    return "%s%sc%02d%s" % (head, separator, color, tail)


def color_of(path: str) -> int | None:
    return split_color(path)[1]


def recolor(path: str, color: int) -> str:
    head, found, tail, separator = split_color(path)
    if found is None:
        return path
    return with_color(head, color, tail, separator)


def retarget(path: str, base: str, clone: str, color: int | None = None) -> str:
    """The clone's name for a base path, moved to `color` when it has a costume."""
    if path.startswith("camera/fighter/") or path.startswith("effect/fighter/"):
        head, rest = path.split("/", 2)[0], path.split("/", 2)[2]
        rest = rest.replace(base, clone, 1)
        if head == "effect" and rest == f"{clone}/ef_{base}.eff":
            rest = f"{clone}/ef_{clone}.eff"
        out = f"{head}/fighter/{rest}"
    elif path.startswith("sound/bank/"):
        head, name = path.rsplit("/", 1)
        out = f"{head}/{name.replace(base, clone, 1)}"
    else:
        out = path.replace(f"fighter/{base}/", f"fighter/{clone}/", 1)
    return out if color is None else recolor(out, color)


def is_asset(path: str) -> bool:
    if any(".bak" in part for part in path.split("/")[:-1]):
        return False
    return path.rsplit(".", 1)[-1].lower() not in NON_ASSET_SUFFIXES


def own_paths(shipped, clone: str) -> set[str]:
    """The shipped files that are this clone's: its trees, its camera, effect and
    sound banks, and any Kirby copy model or body animation carrying its name."""
    prefixes = (f"fighter/{clone}/", f"camera/fighter/{clone}/", f"effect/fighter/{clone}/",
                f"sound/bank/fighter/se_{clone}_", f"sound/bank/fighter_voice/vc_{clone}_",
                f"fighter/kirby/model/copy_{clone}_", f"fighter/kirby/motion/{clone}body/")
    return {path for path in shipped if path.startswith(prefixes) and is_asset(path)}


def group_for(target: str, clone: str, color: int | None):
    """The `new-dir-files` group a path of the clone's belongs to at one costume,
    or None when it belongs to every costume group."""
    if color is None:
        return None
    if target.startswith(f"camera/fighter/{clone}/"):
        return f"fighter/{clone}/camera/c{color:02d}"
    if target.startswith(f"fighter/kirby/motion/{clone}body/"):
        return f"fighter/{clone}/kirbycopy/c{color:02d}/bodymotion"
    if target.startswith(f"fighter/kirby/model/copy_{clone}_"):
        return f"fighter/{clone}/kirbycopy/c{color:02d}"
    return f"fighter/{clone}/c{color:02d}"


def pack_colors(own: set[str]) -> list[int]:
    """The costumes the pack ships, from its body model first."""
    body = {color_of(path) for path in own if "/model/body/" in path}
    found = {color for color in body if color is not None}
    if not found:
        found = {color for color in map(color_of, own) if color is not None}
    return sorted(found)


class Census:
    """The config of one clone, assembled group by group."""

    def __init__(self, base: str, clone: str, colors, shipped=frozenset(),
                 copy_suffix: str = "fitkirby"):
        self.base = base
        self.clone = clone
        self.colors = list(colors)
        self.copy_suffix = copy_suffix
        self.groups: dict[str, set[str]] = collections.defaultdict(set)
        self.share_vanilla: dict[str, list[str]] = {}
        self.share_added: dict[str, list[str]] = {}
        self.declared: set[str] = set()
        self.borrowed: set[str] = set()
        self.origin: dict[str, str] = {}
        self.own = own_paths(shipped, clone)
        self.sets: dict[str, dict[int, list[tuple[str, str]]]] = collections.defaultdict(
            lambda: collections.defaultdict(list))

    def base_color(self, color: int) -> int:
        """The base costume a clone costume borrows from: its own number while
        the base has it, c00 past the vanilla eight."""
        return color if color < VANILLA_COLORS else 0

    def place(self, target: str, color: int | None) -> None:
        """Into the group of its costume, or of every costume when it has none."""
        group = group_for(target, self.clone, color)
        if group is None:
            for index in self.colors:
                self.groups[f"fighter/{self.clone}/c{index:02d}"].add(target)
        else:
            self.groups[group].add(target)

    def share(self, table: dict, source: str, target: str) -> None:
        targets = table.setdefault(source, [])
        if target not in targets:
            targets.append(target)

    def add_own(self) -> None:
        """Declare the pack's files, aliasing a stored copy model into Kirby's
        name for it, and note which costumes each per-costume directory covers."""
        stored = f"fighter/{self.clone}/model/kirbycopy/"
        copies = f"fighter/kirby/model/copy_{self.clone}_{self.copy_suffix}/"
        has_copies = any(path.startswith(copies) for path in self.own)
        for path in sorted(self.own):
            color = color_of(path)
            self.place(path, color)
            self.declared.add(path)
            if path.startswith(stored) and not has_copies and color is not None:
                alias = copies + path[len(stored):]
                self.share(self.share_added, path, alias)
                self.place(alias, color)
                self.declared.add(alias)
                self.origin[alias] = path
        for target in sorted(self.declared):
            head, color, tail, separator = split_color(target)
            if color is not None and not target.startswith(stored):
                self.sets[head][color].append((tail, separator))

    def add_aliases(self) -> None:
        """Whatever the lowest costume ships in a directory, a costume that lacks
        it gets from that costume, so shipping c00 alone still fills every slot."""
        for head, by_color in sorted(self.sets.items()):
            lowest = min(by_color)
            for color in self.colors:
                missing = set(by_color[lowest]) - set(by_color.get(color, []))
                for tail, separator in sorted(missing):
                    source = with_color(head, lowest, tail, separator)
                    target = with_color(head, color, tail, separator)
                    self.share(self.share_added, self.origin.get(source, source), target)
                    self.place(target, color)
                    self.declared.add(target)

    def owns(self, target: str, color: int) -> bool:
        """Whether the pack's own files replace the base's for this path: an
        effect tree with its own .eff, a model directory with its own model, a
        sound bank it ships in any costume."""
        if target.startswith(f"effect/fighter/{self.clone}/"):
            return any(path.endswith(".eff") for path in self.own
                       if path.startswith(f"effect/fighter/{self.clone}/"))
        head, _, _, separator = split_color(target)
        if target.startswith("sound/bank/fighter_voice/") and head.endswith("_cheer"):
            head = head[:-len("_cheer")]
        if head not in self.sets:
            return False
        if target.startswith("sound/bank/"):
            return True
        if head.startswith(f"fighter/{self.clone}/model/"):
            shipped = self.sets[head]
            pack_color = color if color in shipped else min(shipped)
            return with_color(head, pack_color, "/model.numdlb", "/") in self.own
        return False

    def add_base(self) -> None:
        for path in base_files(self.base):
            color = color_of(path)
            for index in self.colors:
                if color is not None and color != self.base_color(index):
                    continue
                target = retarget(path, self.base, self.clone, index if color is not None else None)
                if target in self.declared or target in self.borrowed:
                    continue
                if self.owns(target, index):
                    continue
                self.share(self.share_vanilla, path, target)
                self.place(target, index if color is not None else None)
                self.borrowed.add(target)
                if color is None:
                    break

    def config(self) -> dict:
        clone, base = self.clone, self.base
        infos = []
        infos_base = {}
        own_camera = {color for color in self.colors
                      if self.groups.get(f"fighter/{clone}/camera/c{color:02d}")
                      and any(target in self.declared for target in
                              self.groups[f"fighter/{clone}/camera/c{color:02d}"])}
        for index in self.colors:
            color = f"c{index:02d}"
            for kind in ("", "camera/", "movie/", "result/"):
                infos.append(f"fighter/{clone}/{kind}{color}")
                self.groups.setdefault(f"fighter/{clone}/{kind}{color}", set())
            borrowed = f"c{self.base_color(index):02d}"
            if index in own_camera:
                infos.append(f"fighter/{clone}/{color}/camera")
                self.groups[f"fighter/{clone}/{color}/camera"] = set(
                    self.groups[f"fighter/{clone}/camera/{color}"])
            else:
                infos_base[f"fighter/{clone}/{color}/camera"] = f"fighter/{base}/{borrowed}/camera"
            infos_base[f"fighter/{clone}/{color}/cmn"] = f"fighter/{base}/{borrowed}/cmn"
            copy_group = f"fighter/{clone}/kirbycopy/{color}"
            if self.groups.get(copy_group):
                infos.append(copy_group)
                motion_group = f"{copy_group}/bodymotion"
                if self.groups.get(motion_group):
                    infos.append(motion_group)
                else:
                    infos_base[f"{motion_group}"] = f"fighter/{base}/kirbycopy/{borrowed}/bodymotion"
                for leaf in ("cmn", "sound"):
                    infos_base[f"{copy_group}/{leaf}"] = f"fighter/{base}/kirbycopy/{borrowed}/{leaf}"
        for index in self.colors:
            self.groups[f"fighter/{clone}/c{index:02d}"].update(
                self.groups.get(f"fighter/{clone}/kirbycopy/c{index:02d}", ()))
        return {
            "new-dir-infos": infos,
            "new-dir-infos-base": infos_base,
            "share-to-vanilla": self.share_vanilla,
            "share-to-added": self.share_added,
            "new-dir-files": {key: sorted(value) for key, value in sorted(self.groups.items())
                              if value or "/movie/" in key or "/result/" in key},
        }


def build(base: str, clone: str, shipped=frozenset(), colors=None,
          copy_suffix: str = "fitkirby") -> dict:
    """The clone's config: its own files declared, costumes it lacks aliased from
    the ones it ships, and the base fighter's files shared for the rest."""
    census = Census(base, clone, colors or DEFAULT_COLORS, shipped, copy_suffix)
    census.add_own()
    census.add_aliases()
    census.add_base()
    return census.config()


def add_kirby_copy(config: dict, base: str, clone: str, donor: str, suffix: str,
                   donor_suffix: str = "cap", colors=None) -> None:
    """Alias a donor fighter's Kirby copy model into the clone's own copy name,
    for every costume that has no copy model of its own."""
    colors = list(colors or DEFAULT_COLORS)
    share = config["share-to-vanilla"]
    groups = config["new-dir-files"]
    donor_root = f"fighter/kirby/model/copy_{donor}_{donor_suffix}/"
    members = [path for path in arc_paths() if path.startswith(donor_root)]
    wanted = [index for index in colors
              if not groups.get(f"fighter/{clone}/kirbycopy/c{index:02d}")]
    for path in members:
        color = color_of(path)
        if color is None:
            continue
        name = path.rsplit("/", 1)[-1]
        for index in wanted:
            if (index if index < VANILLA_COLORS else 0) != color:
                continue
            target = f"fighter/kirby/model/copy_{clone}_{suffix}/c{index:02d}/{name}"
            share.setdefault(path, [])
            if target not in share[path]:
                share[path].append(target)
            groups.setdefault(f"fighter/{clone}/kirbycopy/c{index:02d}", []).append(target)
            groups.setdefault(f"fighter/{clone}/c{index:02d}", []).append(target)
    for index in wanted:
        group = f"fighter/{clone}/kirbycopy/c{index:02d}"
        if not groups.get(group):
            continue
        config["new-dir-infos"].append(group)
        borrowed = index if index < VANILLA_COLORS else 0
        for leaf in ("bodymotion", "cmn", "sound"):
            config["new-dir-infos-base"].setdefault(
                f"{group}/{leaf}", f"fighter/{base}/kirbycopy/c{borrowed:02d}/{leaf}")
    for key in list(config["new-dir-files"]):
        config["new-dir-files"][key] = sorted(set(config["new-dir-files"][key]))


def add_kirby_copy_motions(config: dict, base: str, clone: str, donor: str,
                           colors=None) -> None:
    """Alias a donor's Kirby copy BODY animations into the clone's own namespace,
    for every costume that ships none."""
    colors = list(colors or DEFAULT_COLORS)
    share = config["share-to-vanilla"]
    groups = config["new-dir-files"]
    donor_root = f"fighter/kirby/motion/{donor}body/"
    wanted = [index for index in colors
              if not groups.get(f"fighter/{clone}/kirbycopy/c{index:02d}/bodymotion")]
    for path in arc_paths():
        if not path.startswith(donor_root):
            continue
        color = color_of(path)
        if color is None:
            continue
        name = path.rsplit("/", 1)[-1]
        for index in wanted:
            if (index if index < VANILLA_COLORS else 0) != color:
                continue
            target = f"fighter/kirby/motion/{clone}body/c{index:02d}/{name}"
            share.setdefault(path, [])
            if target not in share[path]:
                share[path].append(target)
            groups.setdefault(f"fighter/{clone}/kirbycopy/c{index:02d}/bodymotion", []).append(target)

    for index in wanted:
        key = f"fighter/{clone}/kirbycopy/c{index:02d}/bodymotion"
        if groups.get(key):
            groups[key] = sorted(set(groups[key]))
            if key not in config["new-dir-infos"]:
                config["new-dir-infos"].append(key)
            config["new-dir-infos-base"].pop(key, None)


ITEM_OWN_TREES = ("model", "param")


def shipped_under(pack_dir: str | None) -> set:
    """Arc paths the pack provides bytes for, as `item/<clone>/...` strings."""
    if not pack_dir:
        return set()
    root = Path(pack_dir)
    return {
        str(path.relative_to(root)).replace("\\", "/")
        for path in root.rglob("*")
        if path.is_file()
    }


def item_group_key(clone: str, directory: str) -> str:
    """Own directories carry their own group; base-linked ones use the root group."""
    relative = directory[len(f"item/{clone}"):].lstrip("/")
    head = relative.split("/", 1)[0] if relative else ""
    if not relative or head in ITEM_OWN_TREES:
        return directory
    return f"item/{clone}"


def build_item(base: str, clone: str, shipped: set) -> dict:
    root = f"item/{base}"
    directories = [d for d in arc_dirs() if d == root or d.startswith(root + "/")]
    if not directories:
        raise SystemExit(f"no item/{base}/ in the arc index; check the name")

    infos = []
    infos_base = {}
    for directory in directories:
        relative = directory[len(root):].lstrip("/")
        target = f"item/{clone}/{relative}".rstrip("/")
        infos.append(target)
        head = relative.split("/", 1)[0] if relative else ""
        if relative and head not in ITEM_OWN_TREES:
            infos_base[target] = directory

    share = {}
    groups = collections.defaultdict(list)
    for path in arc_paths():
        if not path.startswith(root + "/"):
            continue
        target = f"item/{clone}/" + path[len(root) + 1:]
        if target not in shipped:
            share.setdefault(path, [])
            if target not in share[path]:
                share[path].append(target)
        groups[item_group_key(clone, target.rsplit("/", 1)[0])].append(target)

    return {
        "new-dir-infos": infos,
        "new-dir-infos-base": infos_base,
        "share-to-vanilla": share,
        "share-to-added": {},
        "new-dir-files": {key: sorted(value) for key, value in sorted(groups.items())},
    }


SECTION_LISTS = ("new-dir-infos",)
SECTION_OWN_KEYS = ("new-dir-infos-base", "new-dir-files")
SECTION_SHARES = ("share-to-vanilla", "share-to-added")


def owns(path: str, clone: str) -> bool:
    """Whether a config entry belongs to this clone rather than to other content."""
    return re.search(r"(^|[/_])%s([/_.]|$)" % re.escape(clone), path) is not None


def merge(existing: dict, generated: dict, clone: str) -> dict:
    """This clone's entries come from `generated`; everything else is kept.

    A section the generator left empty is not touched at all, so a hand written
    `share-to-added` survives. The result is sorted, so writing the fighter and
    the item of one pack in either order gives the same file.
    """
    result: dict = {key: value for key, value in existing.items()}
    for key in SECTION_LISTS:
        if not generated.get(key):
            continue
        kept = [path for path in (result.get(key) or []) if not owns(path, clone)]
        result[key] = sorted(set(kept) | set(generated[key]))
    for key in SECTION_OWN_KEYS:
        if not generated.get(key):
            continue
        section = {name: value for name, value in (result.get(key) or {}).items()
                   if not owns(name, clone)}
        section.update(generated[key])
        result[key] = {name: section[name] for name in sorted(section)}
    for key in SECTION_SHARES:
        if not generated.get(key):
            continue
        section = {}
        for source, targets in (result.get(key) or {}).items():
            if isinstance(targets, list):
                rest = [target for target in targets if not owns(target, clone)]
                if rest:
                    section[source] = rest
            elif not owns(str(targets), clone):
                section[source] = targets
        for source, targets in generated[key].items():
            if isinstance(targets, list) and isinstance(section.get(source), list):
                section[source] = sorted(set(section[source]) | set(targets))
            else:
                section[source] = targets
        result[key] = {source: section[source] for source in sorted(section)}
    for key, value in generated.items():
        result.setdefault(key, value)
    return result


def foreign_entries(config: dict, clone: str) -> int:
    """How many entries in a config belong to content other than this clone."""
    total = 0
    for key in SECTION_LISTS:
        total += sum(1 for path in (config.get(key) or []) if not owns(path, clone))
    for key in SECTION_OWN_KEYS:
        total += sum(1 for name in (config.get(key) or {}) if not owns(name, clone))
    for key in SECTION_SHARES:
        for targets in (config.get(key) or {}).values():
            if isinstance(targets, list):
                total += sum(1 for target in targets if not owns(target, clone))
            elif not owns(str(targets), clone):
                total += 1
    return total


def color_range(start, count, shipped_colors) -> list[int]:
    """The costumes to declare: the range asked for, else the ones the pack
    ships, else the vanilla eight."""
    if count is not None:
        first = start or 0
        if count < 1 or first < 0 or first + count > 256:
            raise SystemExit("costumes must lie within c00 to c255")
        return list(range(first, first + count))
    if shipped_colors:
        return list(shipped_colors)
    return list(DEFAULT_COLORS)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write the config.json a fighter or item clone needs.")
    parser.add_argument("--base", required=True, metavar="NAME",
                        help="the vanilla fighter or item to clone from")
    parser.add_argument("--clone", required=True, metavar="NAME",
                        help="your clone's resource name")
    parser.add_argument("--kind", choices=("fighter", "item"), default="fighter",
                        help="default fighter")
    parser.add_argument("--pack-dir", metavar="DIR",
                        help="your mod folder; files it ships are declared as its own "
                             "instead of shared from the base")
    parser.add_argument("--color-start", type=int, metavar="N",
                        help="first costume (default 0)")
    parser.add_argument("--color-count", type=int, metavar="N",
                        help="how many costumes (default: the ones --pack-dir ships, "
                             "else 8)")
    parser.add_argument("--out", metavar="FILE", help="write here instead of printing")
    parser.add_argument("--kirby-copy-donor", metavar="FIGHTER",
                        help="use that fighter's Kirby copy model for your clone")
    parser.add_argument("--kirby-copy-suffix", default="fitkirby", metavar="NAME",
                        help="copy name suffix, comma separated for several (default "
                             "fitkirby)")
    parser.add_argument("--kirby-copy-donor-suffix", default="cap", metavar="NAME",
                        help="suffix the donor's own copy files use (default cap)")
    parser.add_argument("--kirby-copy-motion-donor", metavar="FIGHTER",
                        help="also use that fighter's copy body animations")
    parser.add_argument("--verify-against", metavar="FILE",
                        help="compare with an existing config.json instead of writing")
    parser.add_argument("--merge", action="store_true",
                        help="keep the entries in --out that belong to the pack's other "
                             "parts (a fighter and an item, or a stage)")
    parser.add_argument("--arc-index", metavar="DIR",
                        help="folder holding arc_files.tsv (default: beside this script)")
    args = parser.parse_args()
    if args.arc_index:
        global ARC_INDEX, ARC_FILES, ARC_DIRS
        ARC_INDEX = Path(args.arc_index)
        ARC_FILES = ARC_INDEX / "arc_files.tsv"
        ARC_DIRS = ARC_INDEX / "arc_dirs.tsv"

    if args.kind == "item":
        config = build_item(args.base, args.clone, shipped_under(args.pack_dir))
        return emit(config, args)

    shipped = shipped_under(args.pack_dir)
    own = own_paths(shipped, args.clone)
    colors = color_range(args.color_start, args.color_count, pack_colors(own))
    suffixes = [suffix.strip() for suffix in args.kirby_copy_suffix.split(",")]
    config = build(args.base, args.clone, shipped, colors, suffixes[0])
    if shipped:
        print(f"declared {len(own)} shipped file(s) of {args.clone}'s; "
              f"costumes c{colors[0]:02d} to c{colors[-1]:02d}")
    missed = uncovered_trees(args.base, set(config["share-to-vanilla"]))
    for tree, count in sorted(missed.items()):
        print(f"WARNING: {args.base} owns {count} file(s) under '{tree}/' that a clone "
              f"cannot load, which crashes at match load. Pick a base without that tree.")
    if args.kirby_copy_motion_donor:
        add_kirby_copy_motions(config, args.base, args.clone, args.kirby_copy_motion_donor,
                               colors)
    if args.kirby_copy_donor:
        for suffix in suffixes:
            add_kirby_copy(config, args.base, args.clone, args.kirby_copy_donor,
                           suffix, args.kirby_copy_donor_suffix, colors)

    return emit(config, args)


def emit(config: dict, args) -> int:
    if args.verify_against:
        known = json.loads(Path(args.verify_against).read_text(encoding="utf-8"))
        for key in ("new-dir-infos", "new-dir-infos-base", "share-to-vanilla", "new-dir-files"):
            mine, theirs = config[key], known.get(key, type(config[key])())
            only_mine = sorted(set(mine) - set(theirs))
            only_theirs = sorted(set(theirs) - set(mine))
            differing = []
            if isinstance(mine, dict):
                for name in sorted(set(mine) & set(theirs)):
                    left, right = mine[name], theirs[name]
                    if isinstance(left, list) and isinstance(right, list):
                        left, right = sorted(left), sorted(right)
                    if left != right:
                        differing.append(name)
            summary = (f"{key}: mine {len(mine)} theirs {len(theirs)} "
                       f"| only-mine {len(only_mine)} only-theirs {len(only_theirs)}")
            if isinstance(mine, dict):
                summary += f" | members differ {len(differing)}"
            print(summary)
            for sample in (only_mine[:3] + only_theirs[:3]):
                print("    ", sample)
            for name in differing[:3]:
                left, right = mine[name], theirs[name]
                if not isinstance(left, list) or not isinstance(right, list):
                    print(f"     {name}: mine {left!r} theirs {right!r}")
                    continue
                extra = sorted(set(left) - set(right))
                missing = sorted(set(right) - set(left))
                print(f"     {name}: mine has {len(extra)} extra, {len(missing)} absent")
                for sample in (extra[:2] + missing[:2]):
                    print("        ", sample)
        return 0

    kept = 0
    if args.merge and args.out and Path(args.out).is_file():
        existing = json.loads(Path(args.out).read_text(encoding="utf-8"))
        kept = foreign_entries(existing, args.clone)
        config = merge(existing, config, args.clone)
    text = json.dumps(config, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}: "
              f"{len(config['new-dir-infos'])} dirs, "
              f"{len(config['share-to-vanilla'])} shares, "
              f"{len(config['new-dir-files'])} groups"
              + (f"; kept {kept} entry(s) belonging to other content" if kept else ""))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
