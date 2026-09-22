#!/usr/bin/env python3
"""Generate an ARCropolis config.json for a fighter clone from the arc index."""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import fighter_manifest
except ImportError:
    fighter_manifest = None

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
ARC_DIR_FILES = ARC_INDEX / "arc_dir_files.tsv"


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


_PATH_LIST: list[str] | None = None


def arc_path_list() -> list[str]:
    """Every file path, in the index's line order, which is what the member
    ranges of arc_dir_files.tsv count in."""
    global _PATH_LIST
    if _PATH_LIST is None:
        _PATH_LIST = list(arc_paths())
    return _PATH_LIST


class Tree:
    """The directories of one part of the arc: which files each loads, and
    which ones are links to another directory."""

    def __init__(self, members: dict[str, list[str]], links: dict[str, str]):
        self.members = members
        self.links = links
        self.holders: dict[str, list[str]] = collections.defaultdict(list)
        for directory, files in members.items():
            for path in files:
                self.holders[path].append(directory)

    @classmethod
    def load(cls, root: str) -> "Tree":
        if not ARC_DIR_FILES.is_file():
            raise SystemExit(
                f"no {ARC_DIR_FILES.name} beside {ARC_FILES.name}: this arc index is "
                "older than the generator; take the arc_index folder from the "
                "current Clone Pack Workbench."
            )
        paths = arc_path_list()
        members: dict[str, list[str]] = {}
        links: dict[str, str] = {}
        with ARC_DIR_FILES.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                cells = line.rstrip("\n").split("\t")
                if len(cells) < 4:
                    continue
                directory, count, ranges, link = cells[:4]
                if directory != root and not directory.startswith(root + "/"):
                    continue
                if link != "-":
                    links[directory] = link
                    continue
                found: list[str] = []
                for span in ranges.split(",") if ranges else ():
                    first, _, last = span.partition("-")
                    start = int(first)
                    stop = int(last) if last else start
                    found.extend(paths[start:stop + 1])
                if len(found) != int(count):
                    raise SystemExit(
                        f"{ARC_DIR_FILES.name} and {ARC_FILES.name} disagree on "
                        f"{directory}; take both from the same Workbench.")
                members[directory] = found
        return cls(members, links)

    def has(self, directory: str) -> bool:
        return directory in self.members or directory in self.links

    def directories(self) -> list[str]:
        return sorted(set(self.members) | set(self.links))

    def files(self, directory: str) -> list[str]:
        return self.members.get(directory, [])


def fighter_tree(name: str) -> Tree:
    return Tree.load(f"fighter/{name}")


VANILLA_COLORS = 8
DEFAULT_COLORS = list(range(VANILLA_COLORS))
FIGHTER_OWNED_TREES = ("finalsmash",)

NON_ASSET_SUFFIXES = {"yml", "yaml", "lua", "md", "txt", "json", "toml", "py", "gitkeep",
                      "prcxml", "xmsbt", "msbt", "stprmxml", "stdatxml", "prcx", "xml",
                      "png", "jpg", "jpeg", "psd", "zip", "7z", "rar", "bak", "ini", "nro"}
PATCH_FOLDER_SUFFIXES = (".nus3audio", ".nus3bank")

COLOR_RE = re.compile(r"/c(\d{2,3})(?=/|$)")
SOUND_COLOR_RE = re.compile(r"_c(\d{2,3})(\.[^/]+)$")
SOUND_NAME_RE = re.compile(r"^(sound/bank/[^/]+/)(se|vc)_([a-z0-9]+)((?:_[a-z0-9]+)*)_c(\d{2,3})(\.[^/]+)$")
EFFECT_COLOR_RE = re.compile(r"_c(\d{2,3})(\.eff)$")
COPY_RE = re.compile(r"^fighter/kirby/(model|motion)/(copy_[^/]+)/")
COPY_MODEL_RE = re.compile(r"^fighter/kirby/model/copy_(.+?)_([^/]+)/")
HAT_SUFFIXES = ("fitkirby", "cap", "helmet", "crown", "mask", "ear", "goggle", "hair",
                "parts", "bag")


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


def owned_trees(base: str) -> dict[str, int]:
    """Top-level trees outside fighter/ the base owns, by file count."""
    found: dict[str, int] = collections.Counter()
    for path in arc_paths():
        head = path.split("/", 1)[0]
        if head in FIGHTER_OWNED_TREES and path.startswith(f"{head}/{base}/"):
            found[head] += 1
    return dict(found)


def split_color(path: str) -> tuple[str, int | None, str, str]:
    """(head, colour, tail, separator): the path with its costume lifted out, so
    `head + separator + cNN + tail` puts any costume back. Sound banks and
    one-slot effect files carry the costume in the file name, everything else
    as a directory; a vanilla effect model's c00 is a name, not a costume."""
    if path.startswith("sound/bank/"):
        found = SOUND_COLOR_RE.search(path)
        if found:
            return path[:found.start()], int(found.group(1)), found.group(2), "_"
        return path, None, "", ""
    if path.startswith("effect/"):
        found = EFFECT_COLOR_RE.search(path)
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


def retarget(path: str, base: str, clone: str, color: int | None = None,
             copy_map: dict[str, str] | None = None) -> str | None:
    """The clone's name for a base path, moved to `color` when it has a costume;
    None for a path that is not the base's to give (another fighter's model in
    a Trainer group, an unnamed hash)."""
    out = None
    if path.startswith(f"fighter/{base}/"):
        out = f"fighter/{clone}/" + path[len(f"fighter/{base}/"):]
    elif path.startswith(f"camera/fighter/{base}/"):
        out = f"camera/fighter/{clone}/" + path[len(f"camera/fighter/{base}/"):]
    elif path.startswith(f"effect/fighter/{base}/"):
        rest = path[len(f"effect/fighter/{base}/"):]
        if rest == f"ef_{base}.eff":
            rest = f"ef_{clone}.eff"
        out = f"effect/fighter/{clone}/{rest}"
    elif path.startswith("sound/bank/"):
        found = SOUND_NAME_RE.match(path)
        if found:
            head, kind, _owner, extra, costume, suffix = found.groups()
            out = f"{head}{kind}_{clone}{extra}_c{costume}{suffix}"
    elif path.startswith(f"fighter/kirby/motion/{base}body/"):
        out = f"fighter/kirby/motion/{clone}body/" + path[len(f"fighter/kirby/motion/{base}body/"):]
    else:
        found = COPY_RE.match(path)
        if found and copy_map and found.group(2) in copy_map:
            out = (f"fighter/kirby/{found.group(1)}/{copy_map[found.group(2)]}/"
                   + path[found.end():])
    if out is None:
        return None
    return out if color is None else recolor(out, color)


def is_asset(path: str) -> bool:
    """A file ARCropolis will serve as itself: not a patch (prcxml, xmsbt, a
    tone inside a `<bank>.nus3audio/` folder), not a dot-prefixed path it
    skips, not a source or picture left in the tree."""
    parts = path.split("/")
    if any(part.startswith(".") for part in parts):
        return False
    if any(".bak" in part or part.lower().endswith(PATCH_FOLDER_SUFFIXES)
           for part in parts[:-1]):
        return False
    return path.rsplit(".", 1)[-1].lower() not in NON_ASSET_SUFFIXES


def own_paths(shipped, clone: str) -> set[str]:
    """The shipped files that are this clone's: its trees, its camera, effect and
    sound banks, and any Kirby copy model or body animation carrying its name."""
    prefixes = (f"fighter/{clone}/", f"camera/fighter/{clone}/", f"effect/fighter/{clone}/",
                f"sound/bank/fighter/se_{clone}_", f"sound/bank/fighter_voice/vc_{clone}_",
                f"fighter/kirby/model/copy_{clone}_", f"fighter/kirby/motion/copy_{clone}_",
                f"fighter/kirby/motion/{clone}body/")
    return {path for path in shipped if path.startswith(prefixes) and is_asset(path)}


def pack_colors(own: set[str]) -> list[int]:
    """The costumes the pack ships, from its body model first."""
    body = {color_of(path) for path in own if "/model/body/" in path}
    found = {color for color in body if color is not None}
    if not found:
        found = {color for color in map(color_of, own) if color is not None}
    return sorted(found)


def copy_suffix_of(name: str) -> str:
    """`copy_mario_cap` gives `cap`; `copy_mii_parts` gives `parts`."""
    rest = name[len("copy_"):]
    return rest.split("_", 1)[1] if "_" in rest else rest


def copy_names(tree: Tree, owner: str, color: int) -> tuple[set[str], set[str]]:
    """The copy model names and copy motion names a fighter's kirbycopy group
    loads for one costume."""
    models, motions = set(), set()
    for path in tree.files(f"fighter/{owner}/kirbycopy/c{color:02d}"):
        found = COPY_RE.match(path)
        if found:
            (models if found.group(1) == "model" else motions).add(found.group(2))
    return models, motions


def hat_name(models: set[str], owner: str, donor_suffix: str | None) -> str | None:
    """Which of a fighter's copy models is the one Kirby wears: the suffix asked
    for, else the first hat-like suffix, else the only model there is."""
    if donor_suffix:
        wanted = f"copy_{owner}_{donor_suffix}"
        return wanted if wanted in models else None
    by_suffix = {copy_suffix_of(name): name for name in models}
    for suffix in HAT_SUFFIXES:
        if suffix in by_suffix:
            return by_suffix[suffix]
    return next(iter(models)) if len(models) == 1 else None


def copy_name_map(tree: Tree, owner: str, clone: str, suffix: str,
                  donor_suffix: str | None = None, color: int = 0) -> dict[str, str]:
    """Every copy name in the owner's kirbycopy group mapped to the clone's:
    the hat becomes copy_<clone>_<suffix>, the primary name the engine builds,
    its motion directory too, and any other model keeps its own suffix."""
    models, motions = copy_names(tree, owner, color)
    hat = hat_name(models, owner, donor_suffix)
    mapping: dict[str, str] = {}
    if hat:
        mapping[hat] = f"copy_{clone}_{suffix}"
    for name in sorted(models):
        if name != hat:
            mapping[name] = f"copy_{clone}_{copy_suffix_of(name)}"
    for name in sorted(motions):
        if name in mapping:
            continue
        if hat and (name == hat or copy_suffix_of(name) == "fitkirby"):
            mapping[name] = f"copy_{clone}_{suffix}"
        elif hat and copy_suffix_of(name) == copy_suffix_of(hat):
            mapping[name] = f"copy_{clone}_{suffix}"
        else:
            mapping[name] = f"copy_{clone}_{copy_suffix_of(name)}"
    return mapping


COSTUME_DIR_RE = re.compile(r"(^|/)c(\d{2,3})(?=/|$)")


def dir_color(directory: str) -> int | None:
    found = COSTUME_DIR_RE.search(directory)
    return int(found.group(2)) if found else None


def recolor_dir(directory: str, color: int) -> str:
    return COSTUME_DIR_RE.sub(lambda m: f"{m.group(1)}c{color:02d}", directory, count=1)


class Census:
    """The config of one clone, assembled directory by directory from the base
    fighter's own directory tree."""

    def __init__(self, base: str, clone: str, colors, shipped=frozenset(),
                 copy_suffix: str = "fitkirby", tree: Tree | None = None,
                 copy_donor: str | None = None, copy_donor_suffix: str | None = None,
                 copy_tree: Tree | None = None):
        self.base = base
        self.clone = clone
        self.colors = list(colors)
        self.copy_suffix = copy_suffix
        self.tree = tree if tree is not None else fighter_tree(base)
        self.copy_owner = copy_donor or base
        self.copy_tree = copy_tree if copy_tree is not None else (
            self.tree if self.copy_owner == base else fighter_tree(self.copy_owner))
        self.copy_map = copy_name_map(self.copy_tree, self.copy_owner, clone, copy_suffix,
                                      copy_donor_suffix)
        self.groups: dict[str, set[str]] = collections.defaultdict(set)
        self.infos: list[str] = []
        self.infos_base: dict[str, str] = {}
        self.share_vanilla: dict[str, list[str]] = {}
        self.share_added: dict[str, list[str]] = {}
        self.declared: set[str] = set()
        self.borrowed: set[str] = set()
        self.origin: dict[str, str] = {}
        self.kinds_of: dict[str, list[str]] = {}
        self.own = own_paths(shipped, clone)
        self.out_of_range = sorted(path for path in self.own
                                   if color_of(path) is not None
                                   and color_of(path) not in self.colors)
        self.own -= set(self.out_of_range)
        self.sets: dict[str, dict[int, list[tuple[str, str]]]] = collections.defaultdict(
            lambda: collections.defaultdict(list))
        self.left_out: dict[str, int] = collections.Counter()

    def base_color(self, color: int) -> int:
        """The base costume a clone costume borrows from: its own number while
        the base has it, c00 otherwise."""
        return color if self.tree.has(f"fighter/{self.base}/c{color:02d}") else 0

    def copy_color(self, color: int) -> int:
        if self.copy_owner == self.base:
            return self.base_color(color)
        return color if self.copy_tree.has(f"fighter/{self.copy_owner}/kirbycopy/c{color:02d}") else 0

    def costume_group(self, color: int) -> str:
        return f"fighter/{self.clone}/c{color:02d}"

    def clone_dir(self, kind: str, color: int) -> str:
        """`kind` is a base-relative directory with its costume as cNN."""
        return f"fighter/{self.clone}/" + kind.replace("cNN", f"c{color:02d}")

    def kind_of_dir(self, directory: str, owner: str) -> str | None:
        """`fighter/mario/result/c03` gives `result/cNN`; None for a directory
        with no costume in it."""
        relative = directory[len(f"fighter/{owner}/"):]
        if dir_color(relative) is None:
            return None
        return COSTUME_DIR_RE.sub(lambda m: f"{m.group(1)}cNN", relative, count=1)

    def add_info(self, directory: str) -> None:
        if directory not in self.infos:
            self.infos.append(directory)
        self.groups.setdefault(directory, set())

    def share(self, table: dict, source: str, target: str) -> None:
        targets = table.setdefault(source, [])
        if target not in targets:
            targets.append(target)

    def put(self, kind: str | None, target: str, color: int | None) -> None:
        """Declare a file in the group of its kind and costume; a kind of None
        is the costume group itself, a colour of None is every costume. A copy
        file is in the costume group as well."""
        if color is None:
            for index in self.colors:
                self.groups[self.costume_group(index)].add(target)
            return
        if kind is None or kind == "cNN":
            self.groups[self.costume_group(color)].add(target)
            return
        self.groups[self.clone_dir(kind, color)].add(target)
        if kind == "kirbycopy/cNN":
            self.groups[self.costume_group(color)].add(target)

    def kinds_for_own(self, path: str, color: int | None) -> list[str | None]:
        """Where a shipped file of the clone's belongs: every kind of directory
        the base keeps its counterpart in, else by what the file is."""
        if color is not None:
            counterpart = self.counterpart(path, color)
            if counterpart:
                kinds = [self.kind_of_dir(holder, self.base)
                         for holder in self.tree.holders.get(counterpart, ())]
                kinds = [kind for kind in kinds if kind]
                if kinds:
                    return kinds
        if path.startswith(f"camera/fighter/{self.clone}/"):
            return ["camera/cNN"]
        if path.startswith(f"fighter/kirby/motion/{self.clone}body/"):
            return ["kirbycopy/cNN/bodymotion"]
        if path.startswith(f"fighter/kirby/model/copy_{self.clone}_") \
                or path.startswith(f"fighter/kirby/motion/copy_{self.clone}_"):
            return ["kirbycopy/cNN"]
        return [None]

    def counterpart(self, path: str, color: int) -> str | None:
        """The base's own file a shipped file of the clone's stands in for."""
        base, clone = self.base, self.clone
        reverse = {value: key for key, value in self.copy_map.items()}
        out = None
        if path.startswith(f"fighter/{clone}/"):
            out = f"fighter/{base}/" + path[len(f"fighter/{clone}/"):]
        elif path.startswith(f"camera/fighter/{clone}/"):
            out = f"camera/fighter/{base}/" + path[len(f"camera/fighter/{clone}/"):]
        elif path.startswith("sound/bank/"):
            found = SOUND_NAME_RE.match(path)
            if found:
                head, kind, _owner, extra, costume, suffix = found.groups()
                out = f"{head}{kind}_{base}{extra}_c{costume}{suffix}"
        elif path.startswith(f"fighter/kirby/motion/{clone}body/"):
            out = f"fighter/kirby/motion/{base}body/" + path[len(f"fighter/kirby/motion/{clone}body/"):]
        else:
            found = COPY_RE.match(path)
            if found and found.group(2) in reverse:
                out = f"fighter/kirby/{found.group(1)}/{reverse[found.group(2)]}/" + path[found.end():]
        if out is None:
            return None
        return recolor(out, self.base_color(color))

    def add_own(self) -> None:
        """Declare the pack's files where the base keeps their counterparts,
        aliasing a stored copy model into Kirby's name for it, and note which
        costumes each per-costume directory covers."""
        stored = f"fighter/{self.clone}/model/kirbycopy/"
        copies = f"fighter/kirby/model/copy_{self.clone}_{self.copy_suffix}/"
        has_copies = any(path.startswith(copies) for path in self.own)
        for path in sorted(self.own):
            color = color_of(path)
            if path.startswith(stored):
                self.put(None, path, color)
                self.declared.add(path)
                if not has_copies and color is not None:
                    alias = copies + path[len(stored):]
                    self.share(self.share_added, path, alias)
                    self.put("kirbycopy/cNN", alias, color)
                    self.declared.add(alias)
                    self.origin[alias] = path
                    self.kinds_of[alias] = ["kirbycopy/cNN"]
                continue
            kinds = self.kinds_for_own(path, color)
            for kind in kinds:
                self.put(kind, path, color)
            self.declared.add(path)
            self.kinds_of[path] = kinds
        for target in sorted(self.declared):
            head, color, tail, separator = split_color(target)
            if color is not None and not target.startswith(stored):
                self.sets[head][color].append((tail, separator))

    def add_aliases(self) -> None:
        """Whatever some costume ships in a directory, a costume that lacks it
        gets from the nearest costume below it that has it, else the nearest
        above, so shipping c00 alone still fills every slot and a pack whose
        odd costumes carry their own textures keeps them together."""
        for head, by_color in sorted(self.sets.items()):
            everything = {entry for entries in by_color.values() for entry in entries}
            for color in self.colors:
                missing = everything - set(by_color.get(color, []))
                for tail, separator in sorted(missing):
                    holders = [index for index, entries in by_color.items()
                               if (tail, separator) in entries]
                    below = [index for index in holders if index < color]
                    origin = max(below) if below else min(holders)
                    source = with_color(head, origin, tail, separator)
                    target = with_color(head, color, tail, separator)
                    self.share(self.share_added, self.origin.get(source, source), target)
                    for kind in self.kinds_of.get(source, [None]):
                        self.put(kind, target, color)
                    self.declared.add(target)

    def owns(self, target: str, color: int) -> bool:
        """Whether the pack's own files replace the base's for this path: an
        effect tree with its own ef_<clone>.eff, a model directory (Kirby's
        copy of it included) with its own model. Motion, camera and sound
        borrow file by file."""
        if target.startswith(f"effect/fighter/{self.clone}/"):
            return f"effect/fighter/{self.clone}/ef_{self.clone}.eff" in self.own
        head, _, _, separator = split_color(target)
        if head not in self.sets:
            return False
        if head.startswith(f"fighter/{self.clone}/model/")                 or head.startswith(f"fighter/kirby/model/copy_{self.clone}_"):
            shipped = self.sets[head]
            pack_color = color if color in shipped else min(shipped)
            return with_color(head, pack_color, "/model.numdlb", "/") in self.declared
        return False

    def mirror(self) -> None:
        """Every directory of the base's for a costume becomes the clone's for
        each of its costumes: a link stays a link to the base's, a directory
        with files gets the base's files under the clone's names unless the
        pack replaces them. The Kirby copy comes from the copy owner, the base
        unless a donor was named. The base's effect directory has no costume,
        so its files go into every costume group."""
        base_root = f"fighter/{self.base}/"
        for color in self.colors:
            borrowed = self.base_color(color)
            for directory in self.tree.directories():
                if not directory.startswith(base_root):
                    continue
                relative = directory[len(base_root):]
                if dir_color(relative) != borrowed:
                    continue
                kind = self.kind_of_dir(directory, self.base)
                target_dir = self.clone_dir(kind, color)
                if directory in self.tree.links:
                    if self.owns_link(kind, color):
                        self.add_info(target_dir)
                    else:
                        self.infos_base[target_dir] = directory
                        self.groups.pop(target_dir, None)
                    continue
                if kind == "kirbycopy/cNN":
                    continue
                self.add_info(target_dir)
                for member in self.tree.files(directory):
                    self.borrow(member, kind, color)
            copy_dir = f"fighter/{self.copy_owner}/kirbycopy/c{self.copy_color(color):02d}"
            if self.copy_tree.files(copy_dir):
                self.add_info(self.clone_dir("kirbycopy/cNN", color))
                for member in self.copy_tree.files(copy_dir):
                    self.borrow(member, "kirbycopy/cNN", color, owner=self.copy_owner)
        for member in self.tree.files(f"fighter/{self.base}/cmn/effect"):
            self.borrow(member, None, None)
        for color in self.colors:
            own_camera = self.clone_dir("cNN/camera", color)
            if own_camera in self.infos:
                self.groups[own_camera] = set(self.groups[self.clone_dir("camera/cNN", color)])
        for directory, members in list(self.groups.items()):
            if members and directory not in self.infos and directory not in self.infos_base:
                self.add_info(directory)

    def owns_link(self, kind: str, color: int) -> bool:
        """A linked directory becomes the clone's own when the pack ships
        something for it: its camera animations, or Kirby's body animations
        for its copy."""
        source = {"cNN/camera": "camera/cNN"}.get(kind, kind)
        return any(target in self.declared
                   for target in self.groups.get(self.clone_dir(source, color), ()))

    def borrow(self, member: str, kind: str | None, color: int | None,
               owner: str | None = None) -> None:
        """Share one of the owner's files under the clone's name into the group
        of its kind, unless the pack already has that file or replaces it."""
        owner = owner or self.base
        target = retarget(member, owner, self.clone, color, self.copy_map)
        if target is None:
            head = "/".join(member.split("/")[:2]) if member.startswith("fighter/") \
                else member.split("/")[0]
            self.left_out[head] += 1
            return
        if target in self.declared:
            return
        if target in self.borrowed:
            self.put(kind, target, color)
            return
        if self.owns(target, self.colors[0] if color is None else color):
            return
        self.share(self.share_vanilla, member, target)
        self.put(kind, target, color)
        self.borrowed.add(target)

    def config(self) -> dict:
        ordered: list[str] = []
        for color in self.colors:
            for directory in self.infos:
                if dir_color(directory[len(f"fighter/{self.clone}/"):]) == color \
                        and directory not in ordered:
                    ordered.append(directory)
        for directory in self.infos:
            if directory not in ordered:
                ordered.append(directory)
        return {
            "new-dir-infos": ordered,
            "new-dir-infos-base": {key: self.infos_base[key] for key in sorted(self.infos_base)},
            "share-to-vanilla": self.share_vanilla,
            "share-to-added": self.share_added,
            "new-dir-files": {key: sorted(value) for key, value in sorted(self.groups.items())
                              if value or key in ordered},
        }


LAST_NOTES: list[str] = []


def build(base: str, clone: str, shipped=frozenset(), colors=None,
          copy_suffix: str = "fitkirby", copy_donor: str | None = None,
          copy_donor_suffix: str | None = None, tree: Tree | None = None,
          copy_tree: Tree | None = None) -> dict:
    """The clone's config: its own files declared, costumes it lacks aliased from
    the ones it ships, and the base fighter's files shared for the rest. What
    could not be carried is left in LAST_NOTES."""
    census = Census(base, clone, colors or DEFAULT_COLORS, shipped, copy_suffix, tree,
                    copy_donor, copy_donor_suffix, copy_tree)
    census.add_own()
    census.add_aliases()
    census.mirror()
    LAST_NOTES[:] = [
        f"{count} file(s) under {head}/ that {base}'s groups load cannot carry the "
        f"clone's name and are left out; the engine loads them from {base}'s own "
        f"groups at match load"
        for head, count in sorted(census.left_out.items())]
    if census.out_of_range:
        first, last = census.colors[0], census.colors[-1]
        LAST_NOTES.append(
            f"{len(census.out_of_range)} shipped file(s) sit at costumes outside "
            f"c{first:02d} to c{last:02d} and are not declared, e.g. "
            f"{census.out_of_range[0]}; renumber the pack so every part uses the "
            "same costumes")
    return census.config()


def add_kirby_copy(config: dict, base: str, clone: str, donor: str, suffix: str,
                   donor_suffix: str | None = None, colors=None,
                   donor_tree: Tree | None = None) -> None:
    """Alias a donor fighter's Kirby copy files into the clone's own copy names,
    for every costume that has no copy model of its own, replacing the base's."""
    colors = list(colors or DEFAULT_COLORS)
    tree = donor_tree if donor_tree is not None else fighter_tree(donor)
    share = config["share-to-vanilla"]
    groups = config["new-dir-files"]
    added_targets = {target for targets in config["share-to-added"].values() for target in targets}
    own_prefix = f"fighter/kirby/model/copy_{clone}_"

    def has_own_copy(index: int) -> bool:
        group = f"fighter/{clone}/kirbycopy/c{index:02d}"
        return any(member.startswith(own_prefix) and
                   (member in added_targets or not any(member in t for t in share.values()))
                   for member in groups.get(group, []))

    wanted = [index for index in colors if not has_own_copy(index)]
    for index in wanted:
        group = f"fighter/{clone}/kirbycopy/c{index:02d}"
        stale = [member for member in groups.get(group, [])
                 if COPY_RE.match(member)]
        for member in stale:
            groups[group].remove(member)
            costume = f"fighter/{clone}/c{index:02d}"
            if member in groups.get(costume, []):
                groups[costume].remove(member)
            for source in list(share):
                if member in share[source]:
                    share[source].remove(member)
                    if not share[source]:
                        del share[source]
    for index in wanted:
        donor_color = index if tree.has(f"fighter/{donor}/kirbycopy/c{index:02d}") else 0
        mapping = copy_name_map(tree, donor, clone, suffix, donor_suffix, donor_color)
        group = f"fighter/{clone}/kirbycopy/c{index:02d}"
        for member in tree.files(f"fighter/{donor}/kirbycopy/c{donor_color:02d}"):
            target = retarget(member, donor, clone, index, mapping)
            if target is None:
                continue
            share.setdefault(member, [])
            if target not in share[member]:
                share[member].append(target)
            groups.setdefault(group, []).append(target)
            groups.setdefault(f"fighter/{clone}/c{index:02d}", []).append(target)
        if not groups.get(group):
            continue
        if group not in config["new-dir-infos"]:
            config["new-dir-infos"].append(group)
        for leaf in ("bodymotion", "cmn", "sound"):
            link = f"{group}/{leaf}"
            if link not in config["new-dir-infos"]:
                config["new-dir-infos-base"][link] = f"fighter/{donor}/kirbycopy/c{donor_color:02d}/{leaf}"
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


def merge(existing: dict, generated: dict, clone: str, stale=()) -> dict:
    """This clone's entries come from `generated`; everything else is kept,
    except entries named after a name in `stale` (the base the clone was
    converted from: a reslotter config's `fighter/<base>/c120` groups name
    files that were renamed away and would never finish loading).

    A section the generator left empty is not touched at all, so a hand written
    `share-to-added` survives. The result is sorted, so writing the fighter and
    the item of one pack in either order gives the same file.
    """
    def mine(path: str) -> bool:
        return owns(path, clone) or any(owns(path, name) for name in stale)

    result: dict = {key: value for key, value in existing.items()}
    for key in SECTION_LISTS:
        if not generated.get(key):
            continue
        kept = [path for path in (result.get(key) or []) if not mine(path)]
        result[key] = sorted(set(kept) | set(generated[key]))
    for key in SECTION_OWN_KEYS:
        if not generated.get(key):
            continue
        section = {name: value for name, value in (result.get(key) or {}).items()
                   if not mine(name)}
        section.update(generated[key])
        result[key] = {name: section[name] for name in sorted(section)}
    for key in SECTION_SHARES:
        if not generated.get(key):
            continue
        section = {}
        for source, targets in (result.get(key) or {}).items():
            if isinstance(targets, list):
                rest = [target for target in targets if not mine(target)]
                if rest:
                    section[source] = rest
            elif not mine(str(targets)):
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


def foreign_entries(config: dict, clone: str, stale=()) -> int:
    """How many entries in a config belong to content other than this clone,
    entries named after a name in `stale` not counted (see `merge`)."""
    return len(entries_owned_by(config, lambda path: not owns(path, clone)
                                and not any(owns(path, name) for name in stale)))


def entries_owned_by(config: dict, wanted) -> list[str]:
    """The config entries (directories, keys, share targets) `wanted` accepts."""
    found = []
    for key in SECTION_LISTS:
        found += [path for path in (config.get(key) or []) if wanted(path)]
    for key in SECTION_OWN_KEYS:
        found += [name for name in (config.get(key) or {}) if wanted(name)]
    for key in SECTION_SHARES:
        for targets in (config.get(key) or {}).values():
            if isinstance(targets, list):
                found += [target for target in targets if wanted(target)]
            elif wanted(str(targets)):
                found.append(str(targets))
    return found


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


def defaults_from_manifest(args) -> str | None:
    """Fill --base, --clone and the costume range from the pack's fighter.toml.
    A flag that disagrees with the file is an error, never a silent override."""
    if not args.pack_dir or fighter_manifest is None:
        return None
    path = Path(args.pack_dir) / "fighter.toml"
    if not path.is_file():
        return None
    try:
        fighters = fighter_manifest.read(path)
    except fighter_manifest.ManifestError as error:
        return f"{path}: {error}"
    except OSError as error:
        return f"{path}: {error}"
    if len(fighters) != 1:
        wanted = args.clone
        matching = [fighter for fighter in fighters if fighter.get("name") == wanted]
        if not matching:
            return (f"{path} declares {len(fighters)} fighters; pass --clone to say "
                    "which one this config is for")
        fighter = matching[0]
    else:
        fighter = fighters[0]
    name = fighter.get("resource_name") or fighter.get("name")
    base = fighter.get("base_resource_name") or fighter.get("base")
    conflicts = []
    if args.clone and args.clone != name:
        conflicts.append(f"--clone {args.clone} but fighter.toml names {name}")
    if args.base and args.base != base:
        conflicts.append(f"--base {args.base} but fighter.toml is on {base}")
    costumes = fighter.get("costumes", 8)
    start = fighter.get("color_start", 0)
    if args.color_count is not None and args.color_count != costumes:
        conflicts.append(f"--color-count {args.color_count} but fighter.toml has {costumes}")
    if args.color_start is not None and args.color_start != start:
        conflicts.append(f"--color-start {args.color_start} but fighter.toml has {start}")
    if conflicts:
        return "; ".join(conflicts) + " (edit fighter.toml, it is what the engine reads)"
    args.clone = name
    args.base = base
    args.color_count = costumes
    args.color_start = start
    print(f"fighter.toml: {name} on {base}, costumes c{start:02} to c{start + costumes - 1:02}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write the config.json a fighter or item clone needs.")
    parser.add_argument("--base", metavar="NAME",
                        help="the vanilla fighter or item to clone from (default: the "
                             "base in --pack-dir's fighter.toml)")
    parser.add_argument("--clone", metavar="NAME",
                        help="your clone's resource name (default: the name in "
                             "--pack-dir's fighter.toml)")
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
                        help="use that fighter's Kirby copy model instead of the base's")
    parser.add_argument("--kirby-copy-suffix", default="fitkirby", metavar="NAME",
                        help="copy name suffix, comma separated for several (default "
                             "fitkirby)")
    parser.add_argument("--kirby-copy-donor-suffix", metavar="NAME",
                        help="which of the donor's copy models is the hat (default: "
                             "found from its files)")
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
        global ARC_INDEX, ARC_FILES, ARC_DIRS, ARC_DIR_FILES
        ARC_INDEX = Path(args.arc_index)
        ARC_FILES = ARC_INDEX / "arc_files.tsv"
        ARC_DIRS = ARC_INDEX / "arc_dirs.tsv"
        ARC_DIR_FILES = ARC_INDEX / "arc_dir_files.tsv"

    if args.kind == "fighter":
        problem = defaults_from_manifest(args)
        if problem:
            print(problem)
            return 2
    if not args.base or not args.clone:
        print("--base and --clone are required without a fighter.toml in --pack-dir")
        return 2

    if args.kind == "item":
        config = build_item(args.base, args.clone, shipped_under(args.pack_dir))
        return emit(config, args)

    tree = fighter_tree(args.base)
    if not tree.has(f"fighter/{args.base}/c00"):
        print(f"no fighter/{args.base}/c00 in the arc index; check the base's name")
        return 2
    shipped = shipped_under(args.pack_dir)
    own = own_paths(shipped, args.clone)
    colors = color_range(args.color_start, args.color_count, pack_colors(own))
    suffixes = [suffix.strip() for suffix in args.kirby_copy_suffix.split(",")]
    config = build(args.base, args.clone, shipped, colors, suffixes[0],
                   args.kirby_copy_donor, args.kirby_copy_donor_suffix, tree)
    for note in LAST_NOTES:
        print(note)
    if shipped:
        print(f"declared {len(own)} shipped file(s) of {args.clone}'s; "
              f"costumes c{colors[0]:02d} to c{colors[-1]:02d}")
    for tree_name, count in sorted(owned_trees(args.base).items()):
        print(f"{args.base} owns {count} file(s) under '{tree_name}/'; the engine loads "
              f"that tree for the clone, nothing to declare")
    if args.kirby_copy_motion_donor:
        add_kirby_copy_motions(config, args.base, args.clone, args.kirby_copy_motion_donor,
                               colors)
    if args.kirby_copy_donor and len(suffixes) > 1:
        for suffix in suffixes[1:]:
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
        stale = (args.base,) if args.kind == "fighter" and args.base else ()
        dropped = entries_owned_by(existing, lambda path: any(owns(path, n) for n in stale))
        if dropped:
            print(f"dropped {len(dropped)} stale entry(s) named after {args.base} "
                  f"(e.g. {dropped[0]}); a clone's config never adds the base's own "
                  "directories")
        kept = foreign_entries(existing, args.clone, stale)
        config = merge(existing, config, args.clone, stale)
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
