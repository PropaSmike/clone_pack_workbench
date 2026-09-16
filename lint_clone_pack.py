#!/usr/bin/env python3
"""Offline checks for a clone-engine pack's ARCropolis config."""

import argparse
import collections
import json
import io
import os
import re
import sys

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

    findings.extend(lint_camera_slots(dir_files, added_dirs, bases, shipped))
    findings.extend(lint_camera_coverage(dir_files, bases, shipped))
    findings.extend(lint_article_lvd_names(shipped))
    findings.extend(lint_item_pack(mod_dir, added_dirs, bases, dir_files, shipped,
                                   resolved_share_targets))
    findings.extend(lint_undeclared_shipped(added_dirs, dir_files, shipped))
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
    with io.open(path, encoding="utf8", errors="replace") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            if line == "[[item]]":
                if headed or blocks[0]:
                    blocks.append({})
                headed = True
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
