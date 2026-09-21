#!/usr/bin/env python3
"""Offline checks for a clone-engine pack's ARCropolis config."""

import argparse
import collections
import json
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import fighter_manifest
except ImportError:
    fighter_manifest = None

WORK_ID_TERM_RE = re.compile(r"(FIGHTER_[A-Z0-9_]*INSTANCE_WORK_ID_(?:INT|FLOAT|FLAG)_TERM)\s*\+\s*(\d+)")

HERE = os.path.dirname(os.path.abspath(__file__))


def _beside(*relative):
    """Data file shipped beside this script, or one of the two levels above it."""
    parent = os.path.dirname(HERE)
    for root in (HERE, parent, os.path.dirname(parent)):
        candidate = os.path.join(root, *relative)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(parent, *relative)


DEFAULT_ARC_INDEX = os.environ.get("SSBU_ARC_INDEX") or _beside("arc_index")


def load_vanilla_dirs(arc_index):
    """Every directory data.arc loads files by, and the target of each link,
    from arc_dir_files.tsv; None without the file."""
    table = os.path.join(arc_index, "arc_dir_files.tsv")
    if not os.path.exists(table):
        return None
    dirs = {}
    with open(table, encoding="utf8", errors="replace") as handle:
        for line in handle:
            cells = line.rstrip("\n").split("\t")
            if len(cells) >= 4:
                dirs[cells[0]] = (int(cells[1]), cells[3])
    return dirs


def load_vanilla_paths(arc_index):
    """Every path that exists in data.arc, from the pre-built index."""
    files = os.path.join(arc_index, "arc_files.tsv")
    if not os.path.exists(files):
        return None
    paths = set()
    with open(files, encoding="utf8", errors="replace") as handle:
        for line in handle:
            paths.add(line.split("\t", 1)[0].strip())
    paths.discard("")
    return paths


def directory_of(path):
    return path.rsplit("/", 1)[0] if "/" in path else ""


def costume_of(path):
    """The cNN component of a path, or None."""
    for part in path.split("/"):
        if 3 <= len(part) <= 4 and part[0] == "c" and part[1:].isdigit():
            return part
    return None


def check_fighter_manifest(mod_dir, shipped, vanilla):
    """fighter.toml against the folders: every article it names has files, the
    costume count matches what the body model ships, and the base is a fighter."""
    findings = []
    path = os.path.join(mod_dir, "fighter.toml")
    if not os.path.isfile(path):
        return findings
    if fighter_manifest is None:
        return [("WARN", "fighter.toml is present but fighter_manifest.py is not beside "
                         "this script, so it was not checked")]
    try:
        fighters = fighter_manifest.read(path)
    except fighter_manifest.ManifestError as error:
        return [("ERROR", f"fighter.toml {error}; the engine registers nothing from it")]
    except OSError as error:
        return [("ERROR", f"fighter.toml: {error}")]
    for fighter in fighters:
        name = fighter.get("resource_name") or fighter.get("name")
        base = fighter.get("base_resource_name") or fighter.get("base")
        if vanilla is not None and not any(
                p.startswith(f"fighter/{base}/") for p in vanilla):
            findings.append(("ERROR", f"fighter.toml: base {base!r} is not a fighter in "
                                      "data.arc"))
        if not any(p.startswith(f"fighter/{name}/") for p in shipped):
            findings.append(("WARN", f"fighter.toml: nothing is shipped under fighter/{name}/; "
                                     "the clone will be all borrowed files"))
        body = set()
        for p in shipped:
            m = re.match(rf"fighter/{re.escape(name)}/model/body/c(\d{{2,3}})/", p)
            if m:
                body.add(int(m.group(1)))
        costumes = fighter.get("costumes", 8)
        start = fighter.get("color_start", 0)
        if body:
            past = sorted(c for c in body if c < start or c >= start + costumes)
            if past:
                findings.append(("WARN", f"fighter.toml: costumes {start}..{start + costumes - 1} "
                                         f"but the body model ships c{past[0]:02}"
                                         + (f" and {len(past) - 1} more" if len(past) > 1 else "")
                                         + "; those costumes are unreachable"))
        for article in fighter["articles"]:
            owner = "kirby" if article.get("kirby") else name
            folder = f"fighter/{owner}/model/{article.get('name')}/"
            if not any(p.startswith(folder) for p in shipped):
                findings.append(("WARN", f"fighter.toml: article {article.get('name')!r} has no "
                                         f"files under {folder}; its model is the source's"))
        kirby = fighter.get("kirby")
        if kirby and kirby.get("statuses", 0) > 0 and not any(
                p.startswith(f"fighter/{name}/model/kirbycopy/") or
                p.startswith(f"fighter/kirby/model/copy_{name}_") for p in shipped):
            findings.append(("WARN", "fighter.toml: [kirby] declares statuses but no copy model is "
                                     "shipped under fighter/%s/model/kirbycopy/ or "
                                     "fighter/kirby/model/copy_%s_*" % (name, name)))
        if fighter.get("staffroll") and not any(
                p == f"standard/staffroll/texture/standard_staffroll_{name}.nutexb"
                for p in shipped):
            findings.append(("ERROR", "fighter.toml: staffroll = true but "
                                      f"standard/staffroll/texture/standard_staffroll_{name}.nutexb "
                                      "is not shipped"))
        if fighter.get("jingle"):
            findings.append(("WARN", "fighter.toml: jingle is accepted by the engine but not "
                                     "served yet; the base's victory theme plays"))
        if fighter.get("css") is False and not os.path.isfile(os.path.join(mod_dir, "plugin.nro")):
            findings.append(("ERROR", "fighter.toml: css = false says the plugin publishes the CSS "
                                      "row through CSK, but there is no plugin.nro; the fighter "
                                      "would have no row"))
    return findings


def check_work_ids(mod_dir):
    """Custom work ids past a base's _TERM in the pack's Rust source: a clone's
    instance arrays are the base's size, and Mecha overran them."""
    findings = []
    source = os.path.join(mod_dir, "src")
    if not os.path.isdir(source):
        return findings
    seen = set()
    for root, _, names in os.walk(source):
        for name in names:
            if not name.endswith(".rs"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf8", errors="replace") as handle:
                    text = handle.read()
            except OSError:
                continue
            for term, offset in WORK_ID_TERM_RE.findall(text):
                if (term, offset) in seen:
                    continue
                seen.add((term, offset))
                findings.append(("WARN", f"{os.path.relpath(path, mod_dir)} uses {term} + {offset}: "
                                         "a clone's work arrays are its base's size, so a custom "
                                         "id past _TERM writes into whatever follows the array"))
    return findings


def lint(mod_dir, arc_index, cross_color_resources=()):
    config_path = os.path.join(mod_dir, "config.json")
    if not os.path.exists(config_path):
        return [("ERROR", f"no config.json in {mod_dir}")]

    with open(config_path, encoding="utf8") as handle:
        config = json.load(handle)

    findings = []
    dir_files = config.get("new-dir-files", {})
    added_dirs = set(config.get("new-dir-infos", []))
    bases = config.get("new-dir-infos-base", {})
    vanilla = load_vanilla_paths(arc_index)

    shipped = set()
    for root, _, names in os.walk(mod_dir):
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), mod_dir)
            shipped.add(rel.replace(os.sep, "/"))
    shared_targets = {
        target
        for section in ("share-to-vanilla", "share-to-added")
        for targets in config.get(section, {}).values()
        for target in targets
    }
    resolved_share_targets = {
        target
        for section in ("share-to-vanilla", "share-to-added")
        for source, targets in config.get(section, {}).items()
        if source in shipped or (vanilla is not None and source in vanilla)
        for target in targets
    }

    if vanilla is not None:
        for group, files in dir_files.items():
            for path in files:
                if path in shipped:
                    continue
                if path in vanilla:
                    findings.append((
                        "ERROR",
                        f"{group} declares VANILLA file {path} which this pack does not ship - "
                        "it will be taken from the fighter that owns it",
                    ))

    if vanilla is not None:
        for group, files in dir_files.items():
            for path in files:
                if path not in shipped and path not in vanilla and path not in shared_targets:
                    if not any(path.startswith(d.rsplit("/", 1)[0]) for d in added_dirs):
                        findings.append((
                            "WARN",
                            f"{group} declares {path}, which is neither shipped nor in data.arc "
                            "(ARCropolis logs it at discovery and skips it)",
                        ))

    cross_color_resources = set(cross_color_resources)
    per_dir = collections.defaultdict(lambda: collections.defaultdict(set))
    for group, files in dir_files.items():
        group_costume = costume_of(group)
        if group_costume is None:
            continue
        for path in files:
            directory = directory_of(path)
            if not any(
                f"/{resource}/" in f"/{directory}/"
                for resource in cross_color_resources
            ):
                continue
            file_costume = costume_of(path)
            if file_costume is None:
                continue
            per_dir[directory.rsplit("/", 1)[0]][group_costume].add(file_costume)

    for directory, groups in per_dir.items():
        colours = {c for costumes in groups.values() for c in costumes}
        if len(colours) <= 1:
            continue
        incomplete = {g: sorted(c) for g, c in groups.items() if c != colours}
        if incomplete:
            findings.append((
                "WARN",
                f"{directory} is declared per-costume ({len(colours)} colours exist) - a group "
                f"loading one colour cannot serve a request for another: {sorted(incomplete)[:3]}",
            ))

    costume_groups = {g for g in dir_files if costume_of(g) is not None and g.count("/") == 2}
    param_groups = collections.defaultdict(set)
    for group in costume_groups:
        for path in dir_files[group]:
            parts = path.split("/")
            if len(parts) == 4 and parts[0] == "fighter" and parts[2] == "param":
                param_groups[path].add(group)
    for path, groups in sorted(param_groups.items()):
        owner = path.split("/")[1]
        owned = {g for g in costume_groups if g.split("/")[1] == owner}
        missing = sorted(owned - groups)
        if missing:
            findings.append((
                "ERROR",
                f"{path} is declared under {len(groups)} of {len(owned)} costume groups for {owner}; "
                f"costumes {missing[:4]} have no param directory and will silently run on the "
                "BASE fighter's vl.prc - declare it under every cNN group",
            ))

    for group in sorted(g for g in dir_files if "kirbycopy" in g):
        files = dir_files[group]
        if not files:
            findings.append(("ERROR", f"{group} is declared but has no members - the resource "
                                      "cache faults walking an empty added directory"))
            continue
        foreign = [
            f for f in files if f not in shipped and f not in resolved_share_targets
        ]
        if foreign:
            findings.append((
                "ERROR",
                f"{group} borrows {len(foreign)} file(s) the pack does not ship, e.g. {foreign[0]}",
            ))

        backed = collections.defaultdict(int)
        unbacked = collections.defaultdict(int)
        for f in files:
            parts = f.split("/")
            if len(parts) < 4 or not parts[3].startswith("copy_"):
                continue
            ok = f in shipped or f in resolved_share_targets
            (backed if ok else unbacked)[parts[3]] += 1
        if backed and unbacked:
            findings.append((
                "ERROR",
                f"{group} declares Kirby copy models under {sorted(unbacked)} with no files "
                f"behind them, while {sorted(backed)} has them. Registering an empty one "
                "crashes Kirby. Use one name in both the plugin and config.json",
            ))

    for group in sorted(added_dirs):
        if "kirbycopy" in group and group not in dir_files:
            findings.append(("ERROR", f"{group} is declared in new-dir-infos with no files"))

    for directory in sorted(added_dirs):
        if any(key.startswith(directory) for key in bases):
            continue
        members = dir_files.get(directory, [])
        if members and all(
            m not in shipped and m not in resolved_share_targets for m in members
        ):
            findings.append((
                "WARN",
                f"{directory} has no new-dir-infos-base entry and ships none of its own files",
            ))

    findings.extend(lint_shares(config, shipped, vanilla))
    findings.extend(lint_added_dirs(added_dirs, bases, dir_files, load_vanilla_dirs(arc_index)))
    findings.extend(lint_effects(added_dirs, dir_files, shipped, shared_targets))
    findings.extend(lint_camera_slots(dir_files, added_dirs, bases, shipped))
    findings.extend(lint_camera_coverage(dir_files, bases, shipped))
    findings.extend(lint_article_lvd_names(shipped))
    findings.extend(lint_item_pack(mod_dir, added_dirs, bases, dir_files, shipped,
                                   resolved_share_targets))
    findings.extend(lint_undeclared_shipped(added_dirs, dir_files, shipped))
    findings.extend(check_fighter_manifest(mod_dir, shipped, vanilla))
    findings.extend(check_work_ids(mod_dir))
    return findings


def lint_shares(config, shipped, vanilla):
    """A share is a new name for an existing file's data. ARCropolis points a
    target the pack ships back at the source, so the shipped bytes never load;
    a source that exists nowhere makes it skip the entry, so the target never
    exists and every group naming it drops it."""
    findings = []
    for section in ("share-to-vanilla", "share-to-added"):
        for source, targets in config.get(section, {}).items():
            targets = targets if isinstance(targets, list) else [targets]
            if source not in shipped and (vanilla is None or source not in vanilla):
                findings.append((
                    "ERROR",
                    f"{section}: source {source} is neither in data.arc nor in this pack; "
                    f"ARCropolis skips it and {len(targets)} target(s) never exist",
                ))
            for target in targets:
                if target in shipped:
                    findings.append((
                        "ERROR",
                        f"{section}: {target} is shipped by this pack AND listed as a target "
                        f"of {source}; ARCropolis points it at the source and the shipped "
                        "file never loads. Drop the share or the file",
                    ))
                if target == source:
                    findings.append(("ERROR", f"{section}: {source} is shared to itself"))
    return findings


def lint_added_dirs(added_dirs, bases, dir_files, vanilla_dirs):
    """Every new directory needs a parent that exists, a base link needs a
    directory that exists, and a linked directory cannot also hold files."""
    findings = []
    known = set(added_dirs) | set(bases)
    for directory, target in sorted(bases.items()):
        if directory in added_dirs:
            findings.append((
                "ERROR",
                f"{directory} is both in new-dir-infos and linked to {target} in "
                "new-dir-infos-base; keep one",
            ))
        if dir_files.get(directory):
            findings.append((
                "ERROR",
                f"{directory} is linked to {target} but new-dir-files gives it "
                f"{len(dir_files[directory])} member(s); a linked directory loads the "
                "target's files, so put them in the directory that owns them",
            ))
        if vanilla_dirs is not None and target not in vanilla_dirs and target not in known:
            findings.append((
                "ERROR",
                f"{directory} is linked to {target}, which is not a directory data.arc "
                "loads and this pack does not add; ARCropolis skips the link",
            ))
    if vanilla_dirs is None:
        return findings
    for directory in sorted(known):
        parent = directory_of(directory)
        if not parent or parent in known or parent in vanilla_dirs:
            continue
        if costume_of(parent.rsplit("/", 1)[-1]) is None:
            continue
        findings.append((
            "ERROR",
            f"{directory} is added under {parent}, which is neither in data.arc nor "
            "declared; ARCropolis creates it with no files and the game walks an "
            "empty costume directory into a fault. Declare the parent or drop the child",
        ))
    return findings


def lint_effects(added_dirs, dir_files, shipped, shared_targets):
    """A clone's effects are effect/fighter/<clone>/ef_<clone>.eff and the
    models beside it, loaded whatever the costume; one-slot names are for
    vanilla slots and an effect model in one costume group only is missing
    for the others."""
    findings = []
    clones = {d.split("/")[1] for d in added_dirs if d.startswith("fighter/") and d.count("/") >= 2}
    costume_groups = collections.defaultdict(list)
    for group in dir_files:
        parts = group.split("/")
        if len(parts) == 3 and parts[0] == "fighter" and costume_of(parts[2]):
            costume_groups[parts[1]].append(group)
    for clone in sorted(clones):
        prefix = f"effect/fighter/{clone}/"
        main = f"{prefix}ef_{clone}.eff"
        one_slot = sorted(p for p in shipped if p.startswith(prefix)
                          and re.fullmatch(rf"ef_{re.escape(clone)}_c\d+\.eff", p[len(prefix):]))
        if one_slot and main not in shipped and main not in shared_targets:
            findings.append((
                "ERROR",
                f"{one_slot[0]} is a one-slot effect name; the engine loads {main}, which "
                "this pack neither ships nor shares. Rename the c00 file (one-slot "
                "effects are a vanilla-slot plugin, a clone has one effect file)",
            ))
        groups = costume_groups.get(clone, [])
        if len(groups) < 2:
            continue
        where = collections.defaultdict(set)
        for group in groups:
            for member in dir_files[group]:
                if member.startswith(prefix + "model/") or member == main:
                    where[member].add(group)
        for member, holders in sorted(where.items()):
            if len(holders) != len(groups):
                findings.append((
                    "WARN",
                    f"{member} is in {len(holders)} of {len(groups)} costume groups of "
                    f"{clone}; the game loads effect files with whichever costume is "
                    "picked, so declare it in every cNN group",
                ))
    return findings


def lint_undeclared_shipped(added_dirs, dir_files, shipped):
    """Files the pack ships under its own namespace that no group declares."""
    namespaces = {
        "/".join(directory.split("/")[:2])
        for directory in added_dirs
        if directory.startswith(("fighter/", "item/")) and directory.count("/") >= 1
    }
    if not namespaces:
        return []
    declared = {member for members in dir_files.values() for member in members}
    missing = sorted(
        path for path in shipped
        if any(path.startswith(namespace + "/") for namespace in namespaces)
        and path not in declared
    )
    if not missing:
        return []
    return [(
        "WARN",
        f"{len(missing)} shipped file(s) are in no new-dir-files group; unless a plugin "
        f"serves them through an arc callback they will not load, "
        f"e.g. {', '.join(missing[:3])}",
    )]


ITEM_OWN_TREES = ("model", "param")


def read_item_tomls(mod_dir):
    """Every item item.toml declares, one dict per [[item]] block or one for a
    flat file; None when there is no item.toml. Regex, not tomllib, for 3.8."""
    path = os.path.join(mod_dir, "item.toml")
    if not os.path.isfile(path):
        return None
    blocks = [{}]
    headed = False
    table = "item"
    with io.open(path, encoding="utf8", errors="replace") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            if line == "[[item]]":
                if headed or blocks[0]:
                    blocks.append({})
                headed = True
                table = "item"
                continue
            if line.startswith("[") and line.endswith("]"):
                table = line.strip("[]").strip().split(".")[-1]
                continue
            if table != "item":
                continue
            found = re.match(r'^(\w+)\s*=\s*"?([^"\s]+)"?', line)
            if found:
                blocks[-1][found.group(1)] = found.group(2)
    return blocks


def lint_item_pack(mod_dir, added_dirs, bases, dir_files, shipped, resolved_share_targets):
    """Checks for a custom ItemKind pack. Every rule here fails silently in game."""
    findings = []
    namespaces = sorted({
        directory.split("/")[1]
        for directory in added_dirs
        if directory.startswith("item/") and directory.count("/") >= 1
    })
    if not namespaces:
        return findings

    tomls = read_item_tomls(mod_dir)
    plugin = os.path.isfile(os.path.join(mod_dir, "plugin.nro"))
    by_resource = {}
    if tomls is None:
        if not plugin:
            findings.append((
                "ERROR",
                f"item/{namespaces[0]} is added but there is no item.toml and no plugin.nro - "
                "nothing registers this pack",
            ))
    else:
        for toml in tomls:
            resource = toml.get("resource_name")
            label = "item.toml" if len(tomls) == 1 else f"item.toml [[item]] '{resource}'"
            if resource and resource not in namespaces:
                findings.append((
                    "ERROR",
                    f"item.toml resource_name '{resource}' does not match the added "
                    f"{', '.join('item/' + n for n in namespaces)}",
                ))
            if "base_kind" not in toml:
                findings.append(("ERROR", f"{label} has no base_kind"))
            if resource:
                if resource in by_resource:
                    findings.append(("ERROR", f"item.toml declares '{resource}' twice"))
                by_resource[resource] = toml
        if len(tomls) > 1:
            findings.append((
                "INFO",
                f"item.toml declares {len(tomls)} items; two or more in one file need an "
                "engine newer than 0.2.1-beta.1, which skips the whole file",
            ))
        for name in namespaces:
            if name not in by_resource and not plugin:
                findings.append((
                    "ERROR",
                    f"item/{name} is added but no item.toml entry declares it and there is "
                    "no plugin.nro - nothing registers it",
                ))

    for name in namespaces:
        prefix = f"item/{name}"
        toml = by_resource.get(name)

        for directory, target in sorted(bases.items()):
            if not directory.startswith(prefix + "/"):
                continue
            head = directory[len(prefix) + 1:].split("/", 1)[0]
            if head in ITEM_OWN_TREES:
                findings.append((
                    "ERROR",
                    f"{directory} is base-linked to {target} - a custom item must own "
                    f"its {head}/",
                ))

        for directory in sorted(d for d in added_dirs if d == prefix or d.startswith(prefix + "/")):
            if directory in bases:
                continue
            if dir_files.get(directory):
                continue
            parent_carries = any(
                member.startswith(directory + "/")
                for members in dir_files.values()
                for member in members
            )
            if not parent_carries:
                findings.append((
                    "ERROR",
                    f"{directory} is added with no base link and no members",
                ))

        param = f"{prefix}/param/param.prc"
        declared = any(param in members for members in dir_files.values())
        if not (param in shipped or param in resolved_share_targets) or not declared:
            findings.append((
                "ERROR",
                f"{param} is not shipped or shared into a declared group",
            ))

        linked_bases = {
            target.split("/")[1]
            for directory, target in bases.items()
            if directory.startswith(prefix + "/") and target.startswith("item/")
        }
        if len(linked_bases) > 1:
            findings.append((
                "WARN",
                f"{prefix} base-links to more than one item: "
                f"{', '.join(sorted(linked_bases))}",
            ))
        elif (toml and linked_bases and toml.get("base_item")
              and toml["base_item"] not in linked_bases):
            findings.append((
                "WARN",
                f"item.toml base_item '{toml['base_item']}' but config links to "
                f"{', '.join(sorted(linked_bases))}",
            ))
    return findings


ARTICLE_LVD_FILENAMES = {
    "firehydrant.lvd",
    "forge.lvd",
    "iceberg.lvd",
    "iceberghit.lvd",
}

ARTICLE_MODEL_DIR = re.compile(r"^fighter/[^/]+/model/[^/]+/c\d\d/([^/]+\.lvd)$")


def lint_article_lvd_names(shipped):
    """An article's LVD filename is hardcoded in the article's own C++ class."""
    findings = []
    for path in sorted(shipped):
        match = ARTICLE_MODEL_DIR.match(path)
        if not match:
            continue
        name = match.group(1)
        if name in ARTICLE_LVD_FILENAMES:
            continue
        findings.append((
            "ERROR",
            f"{path} will never be found: an article's LVD filename is hardcoded in "
            f"the base article's class, so it must keep the base name "
            f"({', '.join(sorted(ARTICLE_LVD_FILENAMES))}) even though the directory "
            f"around it is renamed for the clone",
        ))
    return findings


def lint_camera_slots(dir_files, added_dirs, bases, shipped):
    """A pack shipping its own camera must own BOTH directories vanilla uses."""
    findings = []
    real_re = re.compile(r"^fighter/([^/]+)/camera/c(\d\d)$")
    for directory in sorted(dir_files):
        match = real_re.match(directory)
        if not match:
            continue
        if not any(member in shipped for member in dir_files.get(directory, [])):
            continue
        resource, color = match.group(1), match.group(2)
        slot = f"fighter/{resource}/c{color}/camera"
        if slot in bases:
            findings.append((
                "ERROR",
                f"{slot} is mapped to '{bases[slot]}' but this pack ships its own "
                f"{directory}; the package load will use the other fighter's camera "
                f"and {directory} will never be loaded (docs/CAMERA_UNSHARE.md)",
            ))
        elif slot not in added_dirs or not dir_files.get(slot):
            findings.append((
                "ERROR",
                f"{directory} ships camera files but {slot} is not declared with the "
                f"same members; nothing will load them (docs/CAMERA_UNSHARE.md)",
            ))
        elif set(dir_files[slot]) != set(dir_files[directory]):
            findings.append((
                "WARN",
                f"{slot} and {directory} list different members; vanilla exposes one "
                f"set of files through both paths",
            ))
    return findings


CAMERA_MANIFEST = _beside("docs", "camera_animations.tsv")


def vanilla_camera_animations():
    """fighter -> set of camera animations it owns, from docs/camera_animations.tsv."""
    table = {}
    try:
        handle = io.open(CAMERA_MANIFEST, encoding="utf8")
    except OSError:
        return table
    with handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            name, _count, animations = line.rstrip("\n").split("\t")
            table[name] = set(animations.split(","))
    return table


def lint_camera_coverage(dir_files, bases, shipped):
    """Report camera animations the BASE fighter owns that this pack does not ship."""
    findings = []
    table = vanilla_camera_animations()
    if not table:
        return findings
    real_re = re.compile(r"^fighter/([^/]+)/camera/c(\d\d)$")
    base_names = set()
    for target in bases.values():
        parts = target.split("/")
        if len(parts) > 1 and parts[0] == "fighter" and parts[1] in table:
            base_names.add(parts[1])
    if len(base_names) != 1:
        return findings
    base = base_names.pop()
    expected = table[base]
    for directory in sorted(dir_files):
        match = real_re.match(directory)
        if not match:
            continue
        present = {
            member.rsplit("/", 1)[-1]
            for member in dir_files.get(directory, [])
            if member in shipped
        }
        if not present:
            continue
        missing = sorted(expected - present)
        if missing:
            findings.append((
                "INFO",
                f"{directory} ships {len(present)}/{len(expected)} of {base}'s camera "
                f"animations; {', '.join(missing)} will fall back to {base}",
            ))
        extra = sorted(present - expected)
        if extra:
            findings.append((
                "WARN",
                f"{directory} ships {', '.join(extra)}, which {base} does not have - "
                f"nothing will ever ask for it (docs/camera_animations.tsv)",
            ))
    return findings

def main():
    parser = argparse.ArgumentParser(
        description="Check a fighter or item pack against its config.json.")
    parser.add_argument("mod_dir", help="your mod folder")
    parser.add_argument("--arc-index", default=DEFAULT_ARC_INDEX, metavar="DIR",
                        help="folder holding arc_files.tsv (default: beside this script)")
    parser.add_argument(
        "--cross-color-resource",
        action="append",
        default=[],
        metavar="NAME",
        help="an article folder every costume group must contain; repeatable",
    )
    args = parser.parse_args()

    findings = lint(args.mod_dir, args.arc_index, args.cross_color_resource)
    errors = [f for f in findings if f[0] == "ERROR"]
    for level, message in findings:
        print(f"[{level}] {message}")
    if not findings:
        print("clean")
    print(f"\n{len(errors)} error(s), {len(findings) - len(errors)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
