#!/usr/bin/env python3
import argparse
import json
import os
import re

import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import stage_bank_ids
except ImportError:
    stage_bank_ids = None
try:
    import stage_sqb_tones
except ImportError:
    stage_sqb_tones = None

MISSING_MODULES = [
    name
    for name, module in (("stage_bank_ids", stage_bank_ids),
                         ("stage_sqb_tones", stage_sqb_tones))
    if module is None
]

def _default_arc_index():
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(here, "arc_index"),
        os.path.join(os.path.dirname(here), "arc_index"),
        os.path.join(os.path.dirname(os.path.dirname(here)), "arc_index"),
    ):
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(here, "arc_index")


DEFAULT_ARC_INDEX = os.environ.get("SSBU_ARC_INDEX", _default_arc_index())

FORMS = ("normal", "omega", "battlefield")
PROBE_SUFFIX = "__arcropolis_probe__"

VANILLA_FILE_HOST_PREFIXES = (
    "ui/replace/stage/stage_",
    "ui/replace_patch/stage/stage_",
)

MINTED_ART_PREFIX = "ui/replace/stage/stage_"

VANILLA_FILE_HOST_DIRS = ("sound/bank/stage", "sound/sequence/stage")

KNOWN_TREES = ("stage/", "effect/", "ui/", "sound/")


def is_vanilla_file_host(directory):
    if directory in VANILLA_FILE_HOST_DIRS:
        return True
    for prefix in VANILLA_FILE_HOST_PREFIXES:
        if directory.startswith(prefix) and directory[len(prefix):].isdigit():
            return True
    return False

KNOWN_FORM_CHILDREN = (
    "param", "model", "motion", "effect", "render", "sound", "lut",
    "spirits_floor_model", "spirits_floor_motion",
)


def hash40(text):
    lower = text.lower().encode("utf8")
    return (len(lower) << 32) | zlib.crc32(lower)


def load_vanilla(arc_index):
    files_path = os.path.join(arc_index, "arc_files.tsv")
    dirs_path = os.path.join(arc_index, "arc_dirs.tsv")
    if not (os.path.exists(files_path) and os.path.exists(dirs_path)):
        return None, None
    files = set()
    with open(files_path, encoding="utf8", errors="replace") as handle:
        for line in handle:
            files.add(line.split("\t", 1)[0].strip())
    directories = set()
    with open(dirs_path, encoding="utf8", errors="replace") as handle:
        for line in handle:
            directories.add(line.split("\t", 1)[0].strip())
    files.discard("")
    directories.discard("")
    return files, directories


def read_stage_tomls(path):
    """Every stage the manifest declares: one dict for a flat file, one per
    [[stage]] block; an empty list when there is no file."""
    if not os.path.exists(path):
        return []
    blocks = [{}]
    headed = False
    with open(path, encoding="utf8") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            if line == "[[stage]]":
                if headed or blocks[0]:
                    blocks.append({})
                headed = True
                continue
            if not line or "=" not in line:
                continue
            settings = blocks[-1]
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if value.startswith("[") and value.endswith("]"):
                settings[key] = [
                    item.strip().strip('"').strip("'")
                    for item in value[1:-1].split(",")
                    if item.strip()
                ]
            elif value.lower() in ("true", "false"):
                settings[key] = value.lower() == "true"
            elif value.startswith(('"', "'")):
                settings[key] = value.strip('"').strip("'")
            else:
                try:
                    settings[key] = int(value)
                except ValueError:
                    settings[key] = value
    return [block for block in blocks if block] or [{}]


def read_stage_toml(path):
    """The first stage declared, for a caller that handles one."""
    found = read_stage_tomls(path)
    return found[0] if found else {}


def shipped_files(mod_dir):
    out = set()
    for root, _, names in os.walk(mod_dir):
        for name in names:
            relative = os.path.relpath(os.path.join(root, name), mod_dir)
            out.add(relative.replace(os.sep, "/"))
    return out


def directory_of(path):
    return path.rsplit("/", 1)[0] if "/" in path else ""


def stage_directories(paths, place):
    prefix = "stage/%s/" % place
    tree = {}
    for path in sorted(paths):
        if not path.startswith(prefix):
            continue
        tree.setdefault(directory_of(path), []).append(path)
    return tree


def all_parents(directory):
    parts = directory.split("/")
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def arc_trees(forms, ships_battle_tree):
    trees = ["normal"]
    if ships_battle_tree and any(form != "normal" for form in forms):
        trees.append("battle")
    return trees


def protected_directories(shipped_dirs, tree_roots, place):
    protected = {"stage/%s" % place}
    protected.update(tree_roots)
    for directory in shipped_dirs:
        protected.update(all_parents(directory))
    return protected


def donor_tree_sources(trees, donor, vanilla_dirs, normal_override=None):
    sources = {}
    for name in trees:
        donor_tree = normal_override if name == "normal" and normal_override else name
        if (
            not normal_override
            and vanilla_dirs
            and ("stage/%s/%s" % (donor, name)) not in vanilla_dirs
        ):
            donor_tree = "normal"
        sources[name] = donor_tree
    return sources


FOUND_BY_EXTENSION = ("lvd", "stprm")
FOUND_BY_NAME = ("stdat",)


def extension_of(path):
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[1].lower() if "." in name else ""


def donor_kind_files(donor, donor_dir, vanilla_files, extension):
    """The donor's files of one extension in one directory, split into the ones
    that carry the donor's name and the ones that do not (linegroup.stdat)."""
    named, plain = [], []
    for path in vanilla_files or ():
        directory, _, basename = path.rpartition("/")
        if directory != donor_dir or extension_of(basename) != extension:
            continue
        (named if donor in basename else plain).append(basename)
    return named, plain


def replaces_donor_kind(our_dir, donor_basename, donor, donor_dir, shipped_paths,
                        vanilla_files):
    """Whether a file the pack ships stands in for this donor file, whatever it
    is called: only when the donor has one of that kind, or one carrying its
    name beside unnamed ones (linegroup.stdat). A numbered set matches by name."""
    extension = extension_of(donor_basename)
    if extension not in FOUND_BY_EXTENSION:
        return False
    named, plain = donor_kind_files(donor, donor_dir, vanilla_files, extension)
    if len(named) + len(plain) == 1:
        replaced = {donor_basename}
    elif len(named) == 1 and donor_basename in named:
        replaced = {donor_basename}
    else:
        return False
    if donor_basename not in replaced:
        return False
    for path in shipped_paths:
        directory, _, basename = path.rpartition("/")
        if directory == our_dir and extension_of(basename) == extension \
                and basename not in plain:
            return True
    return False


def donor_stdat_names(donor, vanilla_files):
    """The `.stdat` basenames the donor's stage code asks for, by tree."""
    names = {}
    pattern = re.compile(r"stage/%s/([^/]+)/param/([^/]+\.stdat)$" % re.escape(donor))
    for path in vanilla_files or ():
        match = pattern.match(path)
        if match:
            names.setdefault(match.group(1), set()).add(match.group(2))
    return names


def stdat_aliases(place, donor, trees, vanilla_files, shipped_paths):
    """The behaviour donor's `.stdat` files under their own names, for every
    tree the pack has, unless the pack ships that name there. The stage code
    asks for each by basename; a renamed one is never read."""
    aliases = {}
    for tree, basenames in sorted(donor_stdat_names(donor, vanilla_files).items()):
        if tree not in trees:
            continue
        our_dir = "stage/%s/%s/param" % (place, tree)
        for basename in sorted(basenames):
            ours = "%s/%s" % (our_dir, basename)
            if ours in shipped_paths:
                continue
            source = "stage/%s/%s/param/%s" % (donor, tree, basename)
            aliases.setdefault(source, []).append(ours)
    return aliases


def alias_name_derived(place, donor, tree_sources, vanilla_files, shipped_paths):
    aliases = {}
    for our_tree, donor_tree in tree_sources.items():
        prefix = "stage/%s/%s/" % (donor, donor_tree)
        for path in sorted(vanilla_files or ()):
            if not path.startswith(prefix):
                continue
            directory, _, basename = path.rpartition("/")
            if donor not in basename or not directory.endswith("/param"):
                continue
            if extension_of(basename) in FOUND_BY_NAME:
                continue
            relative = directory[len(prefix):]
            our_dir = "stage/%s/%s/%s" % (place, our_tree, relative)
            ours = "%s/%s" % (our_dir, basename.replace(donor, place))
            if ours in shipped_paths:
                continue
            if replaces_donor_kind(our_dir, basename, donor, directory, shipped_paths,
                                   vanilla_files):
                continue
            aliases.setdefault(path, []).append(ours)
    return aliases


def share_missing_from_donor(place, donor, tree_sources, vanilla_files, tree):
    shares = {}
    for our_dir, ours in tree.items():
        shipped = {path.rsplit("/", 1)[1] for path in ours}
        for name, donor_tree in tree_sources.items():
            our_root = "stage/%s/%s/" % (place, name)
            if not our_dir.startswith(our_root):
                continue
            donor_dir = "stage/%s/%s/%s" % (
                donor,
                donor_tree,
                our_dir[len(our_root):],
            )
            for path in vanilla_files or ():
                if path.rsplit("/", 1)[0] != donor_dir:
                    continue
                basename = path.rsplit("/", 1)[1]
                if basename in shipped:
                    continue
                if donor in basename and donor_dir.endswith("/param"):
                    continue
                if extension_of(basename) in FOUND_BY_NAME:
                    continue
                if replaces_donor_kind(our_dir, basename, donor, donor_dir, set(ours),
                                       vanilla_files):
                    continue
                shares.setdefault(path, []).append("%s/%s" % (our_dir, basename))
    return shares


def check_stdat_names(config, place, donor, vanilla_files):
    """A `.stdat` the donor's stage code never asks for, or one it asks for
    that the folder lacks."""
    findings = []
    if not vanilla_files:
        return findings
    theirs = donor_stdat_names(donor, vanilla_files)
    known = set().union(*theirs.values()) if theirs else set()
    dir_files = config.get("new-dir-files", {})
    for directory in sorted(dir_files):
        parts = directory.split("/")
        if len(parts) != 4 or parts[:2] != ["stage", place] or parts[3] != "param":
            continue
        ours = {path.rsplit("/", 1)[1] for path in dir_files[directory]
                if extension_of(path) in FOUND_BY_NAME}
        for name in sorted(ours - known):
            if known:
                findings.append((
                    "ERROR",
                    "%s/%s is never read: %s's stage code asks for its .stdat by "
                    "name (%s). Rename yours to that, in your own folder, and re-run "
                    "with --write-config."
                    % (directory, name, donor, ", ".join(sorted(known))),
                ))
            else:
                findings.append((
                    "WARN",
                    "%s/%s is never read: %s's stage code reads no .stdat at all."
                    % (directory, name, donor),
                ))
        for name in sorted(theirs.get(parts[2], set()) - ours):
            findings.append((
                "WARN",
                "%s has no %s; %s's stage code asks for it by name and runs on its "
                "built-in values without it. --write-config borrows the donor's."
                % (directory, name, donor),
            ))
    return findings


def check_found_by_extension(config, place, donor, vanilla_files, tree_sources=None):
    """More lvd or stprm files in a folder than the donor keeps there."""
    findings = []
    dir_files = config.get("new-dir-files", {})
    for directory in sorted(dir_files):
        if not directory.startswith("stage/%s/" % place):
            continue
        theirs = donor_counterpart(directory, place, donor, tree_sources)
        by_kind = {}
        for path in dir_files[directory]:
            basename = path.rsplit("/", 1)[1]
            extension = extension_of(basename)
            if extension in FOUND_BY_EXTENSION:
                by_kind.setdefault(extension, []).append(basename)
        for extension, names in sorted(by_kind.items()):
            named, plain = donor_kind_files(donor, theirs, vanilla_files, extension)
            allowed = max(1, len(named) + len(plain)) if vanilla_files else 1
            if len(names) <= allowed:
                continue
            findings.append((
                "ERROR",
                "%s lists %d .%s files (%s); the donor has %d. The game picks any "
                ".%s it finds, so keep only yours and re-run with --write-config. A "
                "stage with a numbered set (wufu_00.lvd, ...) needs the donor's names."
                % (directory, len(names), extension, ", ".join(names), allowed,
                   extension),
            ))
    return findings


def donor_counterpart(directory, place, donor, tree_sources=None):
    parts = directory.split("/")
    if (
        len(parts) >= 3
        and parts[0] == "stage"
        and parts[1] == place
        and tree_sources
        and parts[2] in tree_sources
    ):
        parts[1] = donor
        parts[2] = tree_sources[parts[2]]
        return "/".join(parts)
    return "/".join(donor if part == place else part for part in parts)


def share_effect_group(place, donor, vanilla_files, shipped):
    ours = "effect/stage/%s" % place
    theirs = "effect/stage/%s" % donor
    if any(path.startswith(ours + "/") for path in shipped):
        return {}
    shares = {}
    for path in sorted(vanilla_files or ()):
        if directory_of(path) != theirs:
            continue
        basename = path.rsplit("/", 1)[1]
        shares.setdefault(path, []).append(
            "%s/%s" % (ours, basename.replace(donor, place))
        )
    return shares

SCENERY_TREES = ("model", "motion")


def is_donor_scenery(directory):
    parts = directory.split("/")
    return len(parts) >= 5 and parts[0] == "stage" and parts[3] in SCENERY_TREES


SOUND_EXTENSIONS = ("nus3bank", "nus3audio", "tonelabel")


def sound_path(place, extension):
    if extension == "sqb":
        return "sound/sequence/stage/%s.sqb" % place
    return "sound/bank/stage/se_stage_%s.%s" % (place, extension)


def sound_shares(place, donor, shipped, vanilla_files):
    """Donor sound files a pack needs shared under its own place name.

    A minted stage asks for its own four sound paths and gets silence if they do
    not exist, so anything the pack does not ship itself is borrowed from the
    donor. A path the pack ships is never a share target.
    """
    shares = {}
    if not vanilla_files:
        return shares
    for extension in SOUND_EXTENSIONS + ("sqb",):
        ours = sound_path(place, extension)
        theirs = sound_path(donor, extension)
        if ours in shipped or theirs not in vanilla_files:
            continue
        shares[theirs] = ours
    return shares


def build_config(mod_dir, place, donor, forms_present, ships_battle_tree,
                 vanilla_dirs, vanilla_files=None, carry_donor_scenery=True,
                 content_donor_tree=None, stdat_donor=None):
    stdat_donor = stdat_donor or donor
    shipped = shipped_files(mod_dir)
    tree = stage_directories(shipped, place)
    shipped_dirs = set(tree)
    trees = arc_trees(forms_present, ships_battle_tree)
    tree_sources = donor_tree_sources(
        trees, donor, vanilla_dirs, content_donor_tree
    )
    tree_roots = {"stage/%s/%s" % (place, name) for name in trees}

    structural = set()
    for directory in shipped_dirs:
        structural.update(all_parents(directory))
    structural.add("stage/%s" % place)
    structural |= tree_roots

    protected = protected_directories(shipped_dirs, tree_roots, place)

    based = {}
    for name in trees:
        donor_tree = tree_sources[name]
        donor_root = "stage/%s/%s" % (donor, donor_tree)
        our_root = "stage/%s/%s" % (place, name)
        for donor_dir in sorted(vanilla_dirs or ()):
            if not donor_dir.startswith(donor_root + "/"):
                continue
            ours = our_root + donor_dir[len(donor_root):]
            if ours in protected:
                continue
            if not carry_donor_scenery and is_donor_scenery(ours):
                continue
            based[ours] = donor_dir

    existing = vanilla_dirs or set()
    new_dir_infos = sorted(
        directory
        for directory in structural
        if directory not in based and directory not in existing
    )

    new_dir_files = {
        directory: sorted(files) for directory, files in sorted(tree.items())
    }

    shipped_paths = {path for files in tree.values() for path in files}
    aliases = alias_name_derived(
        place, donor, tree_sources, vanilla_files, shipped_paths
    )
    for source, targets in stdat_aliases(
        place, stdat_donor, trees, vanilla_files, shipped_paths
    ).items():
        aliases.setdefault(source, []).extend(targets)
    for source, targets in share_missing_from_donor(
        place, donor, tree_sources, vanilla_files, tree
    ).items():
        aliases.setdefault(source, []).extend(targets)
    for source, targets in share_effect_group(
        place, donor, vanilla_files, shipped
    ).items():
        aliases.setdefault(source, []).extend(targets)
    for targets in aliases.values():
        for target in targets:
            directory = directory_of(target)
            if directory not in new_dir_files:
                new_dir_files[directory] = []
            if target not in new_dir_files[directory]:
                new_dir_files[directory].append(target)
            based.pop(directory, None)
            for parent in all_parents(directory):
                based.pop(parent, None)
                if parent not in new_dir_infos and parent not in (vanilla_dirs or set()):
                    new_dir_infos.append(parent)

    effect = "effect/stage/%s" % place
    if vanilla_dirs and ("effect/stage/%s" % donor) in vanilla_dirs:
        if effect not in new_dir_infos:
            new_dir_infos.append(effect)
    for path in sorted(shipped):
        if directory_of(path) == effect:
            new_dir_files.setdefault(effect, []).append(path)
            if effect not in new_dir_infos:
                new_dir_infos.append(effect)

    for created in sorted(set(new_dir_infos)):
        if created in based:
            continue
        theirs = donor_counterpart(created, place, donor, tree_sources)
        if theirs == created:
            continue
        rename = created.endswith("/param") or created.startswith("effect/")
        have = set(new_dir_files.get(created) or ())
        for path in sorted(vanilla_files or ()):
            if directory_of(path) != theirs:
                continue
            basename = path.rsplit("/", 1)[1]
            if extension_of(basename) in FOUND_BY_NAME:
                continue
            ours = "%s/%s" % (created, basename.replace(donor, place) if rename
                              else basename)
            if ours in have or ours in shipped_paths:
                continue
            if replaces_donor_kind(created, basename, donor, theirs, shipped_paths,
                                   vanilla_files):
                continue
            have.add(ours)
            aliases.setdefault(path, []).append(ours)
            new_dir_files.setdefault(created, []).append(ours)
    for tree in ("ui",):
        for base, _, files in os.walk(os.path.join(mod_dir, tree)):
            relative = os.path.relpath(base, mod_dir).replace(os.sep, "/")
            if relative.startswith("ui/message") or relative == tree:
                continue
            for name in files:
                new_dir_files.setdefault(relative, set()).add("%s/%s" % (relative, name))

    for theirs, ours in sound_shares(place, donor, shipped, vanilla_files).items():
        aliases.setdefault(theirs, []).append(ours)

    config = {
        "new-dir-infos": sorted(set(new_dir_infos)),
        "new-dir-infos-base": dict(sorted(based.items())),
        "new-dir-files": {k: sorted(v) for k, v in sorted(new_dir_files.items())},
    }
    if aliases:
        config["share-to-vanilla"] = {k: sorted(v) for k, v in sorted(aliases.items())}
    return config


STAGE_TREES = ("stage", "ui")
STAGE_PREFIXES = ("effect/stage/",)


def stage_owner(path):
    """The place a stage-tree path belongs to, or None for any other tree."""
    parts = path.split("/")
    if parts[0] == "stage" and len(parts) > 1:
        return parts[1]
    if path.startswith(STAGE_PREFIXES) and len(parts) > 2:
        return parts[2]
    return None


def stage_owns(path, place):
    """Whether a config entry is this stage's, rather than a fighter's, an item's
    or another stage's. The stage-select art under ui/ is every stage's."""
    owner = stage_owner(path)
    if owner is not None:
        return owner == place
    if path.split("/", 1)[0] in STAGE_TREES:
        return True
    return re.search(r"(^|[/_])%s([/_.]|$)" % re.escape(place), path) is not None


def carry_foreign(previous, generated, place, others=()):
    """Put back the entries of a pack that also ships a fighter, an item or
    another stage.

    `--write-config` derives the whole file from one stage's tree, so on a
    combined pack everything the other content declared would be dropped. A
    stage entry is carried only for a place the manifest still declares, so a
    renamed place leaves nothing stale behind. Returns how many entries were
    carried over.
    """

    def foreign(entry):
        if stage_owns(entry, place):
            return False
        owner = stage_owner(entry)
        return owner is None or owner in others

    carried = 0
    for key, section in previous.items():
        if isinstance(section, list):
            kept_entries = [entry for entry in section if foreign(entry)]
            if not kept_entries:
                continue
            kept = generated.setdefault(key, [])
            for entry in kept_entries:
                if entry not in kept:
                    kept.append(entry)
                    carried += 1
            continue
        if not isinstance(section, dict):
            continue
        for name, value in section.items():
            if isinstance(value, list):
                targets = [target for target in value if foreign(target)]
                if not targets:
                    continue
                mine = generated.setdefault(key, {}).setdefault(name, [])
                for target in targets:
                    if target not in mine:
                        mine.append(target)
                        carried += 1
            elif foreign(name) or (stage_owner(name) is None and foreign(str(value))):
                if name not in generated.setdefault(key, {}):
                    generated[key][name] = value
                    carried += 1
    return carried


def lint(mod_dir, arc_index, write_config=False):
    """Every stage the pack declares, checked in turn. With several, each
    finding is prefixed by its place, and a `--write-config` for one stage
    carries the entries of the others, so the file ends up holding them all."""
    declared = read_stage_tomls(os.path.join(mod_dir, "stage.toml"))
    if not declared or declared == [{}]:
        return [("ERROR", "no stage.toml in %s" % mod_dir)]
    places = [settings.get("place") for settings in declared if settings.get("place")]
    findings = []
    if len(declared) > 1:
        findings.append((
            "INFO",
            "stage.toml declares %d stages; two or more in one file need an engine "
            "newer than 0.2.1-beta.1, which skips the whole file" % len(declared),
        ))
        if len(set(places)) != len(places):
            findings.append(("ERROR", "stage.toml declares the same place twice"))
    for settings in declared:
        found = lint_stage(mod_dir, arc_index, settings, places, write_config)
        if len(declared) > 1:
            found = [(level, "%s: %s" % (settings.get("place") or "?", message))
                     for level, message in found]
        findings.extend(found)
    return findings


def lint_stage(mod_dir, arc_index, settings, declared_places, write_config=False):
    findings = []

    def error(message):
        findings.append(("ERROR", message))

    def warn(message):
        findings.append(("WARN", message))

    def note(message):
        findings.append(("INFO", message))

    place = settings.get("place")
    if not place:
        return [("ERROR", "stage.toml has no `place`")]
    if place != place.lower() or " " in place:
        error("place %r must be a lowercase arc directory name" % place)

    for name in MISSING_MODULES:
        warn(
            "%s.py is not beside lint_stage_pack.py, so the checks that need it "
            "are skipped. Copy the whole linter folder, not just the script."
            % name
        )

    vanilla_files, vanilla_dirs = load_vanilla(arc_index)
    if vanilla_files is None:
        if write_config:
            error(
                "no arc index at %s, so --write-config cannot fill in the donor's "
                "files and would write a broken config.json. Pass --arc-index, or "
                "set SSBU_ARC_INDEX to a folder holding arc_files.tsv and "
                "arc_dirs.tsv." % arc_index
            )
            return findings
        warn(
            "no arc index at %s, so nothing can be checked against the game's "
            "files. Pass --arc-index, or set SSBU_ARC_INDEX to a folder holding "
            "arc_files.tsv and arc_dirs.tsv." % arc_index
        )

    if vanilla_dirs and ("stage/%s" % place) in vanilla_dirs:
        error(
            "place %r is a vanilla stage. A clone stage needs a place name of its "
            "own." % place
        )

    paths = shipped_files(mod_dir)
    tree = stage_directories(paths, place)
    other_places = sorted(
        {
            path.split("/")[1]
            for path in paths
            if path.startswith("stage/") and len(path.split("/")) > 2
        }
        - set(declared_places)
    )
    if other_places:
        error(
            "ships files under stage/%s/ but stage.toml declares %s"
            % ("/, stage/".join(other_places),
               "place %r" % place if len(declared_places) == 1
               else "only %s" % ", ".join(repr(known) for known in declared_places))
        )
    if not tree:
        warn(
            "skeleton: nothing shipped under stage/%s/ yet. Drop the stage tree in "
            "and re-run with --write-config." % place
        )

    forms = [form for form in settings.get("forms", ["normal"]) if form in FORMS]
    if not forms:
        error("stage.toml `forms` selects nothing; Normal is the minimum")
    if "normal" not in forms:
        error("a stage without its Normal form cannot be loaded")

    ships_battle = any(path.startswith("stage/%s/battle/" % place) for path in paths)
    declared = bool(settings.get("ships_battle_tree", False))
    if declared and not ships_battle:
        error(
            "ships_battle_tree = true but there is nothing under stage/%s/battle/. "
            "Omega and Battlefield would point at a missing tree and fail to load."
            % place
        )
    if ships_battle and not declared:
        error(
            "stage/%s/battle/ exists but ships_battle_tree = false, so Omega and "
            "Battlefield would use normal/ and the battle tree never loads." % place
        )

    id_name = settings.get("id_name")
    if not id_name:
        error("stage.toml has no `id_name`; the label is nam_stg1_<id_name>")
    else:
        if id_name.lower() != place:
            error(
                "id_name %r does not match place %r. The stage-select art is named "
                "stage_<N>_<id_name>.bntx, so the icons would be looked up as "
                "stage_<N>_%s.bntx and stay blank. Use %r."
                % (id_name, place, id_name.lower(),
                   "_".join(part.capitalize() for part in place.split("_")))
            )
        label = "nam_stg1_%s" % id_name
        xmsbt = [path for path in paths if path.endswith("msg_name.xmsbt")]
        if not xmsbt:
            warn("no ui/message/msg_name.xmsbt; the stage will have no name")
        else:
            found = False
            for relative in xmsbt:
                with open(os.path.join(mod_dir, relative), "rb") as handle:
                    blob = handle.read()
                if label.encode("utf-16-le") in blob or label.encode("utf8") in blob:
                    found = True
            if not found:
                error("%s is in no msg_name.xmsbt; the stage will show a blank label"
                      % label)
    sound_donor = settings.get("content_donor") or settings.get("donor") or place
    shared_sound = set()
    config_on_disk = os.path.join(mod_dir, "config.json")
    if os.path.exists(config_on_disk):
        with open(config_on_disk, encoding="utf8") as handle:
            shared_now = json.load(handle).get("share-to-vanilla") or {}
        for targets in shared_now.values():
            for target in targets:
                stem = target.rsplit("/", 1)[-1]
                for extension in ("nus3bank", "nus3audio", "tonelabel"):
                    if stem == "se_stage_%s.%s" % (place, extension):
                        shared_sound.add(extension)
                if stem == "%s.sqb" % place:
                    shared_sound.add("sqb")

    def sound_resolves(extension):
        if extension == "sqb":
            ours = "sound/sequence/stage/%s.sqb" % place
            theirs = "sound/sequence/stage/%s.sqb" % sound_donor
        else:
            ours = "sound/bank/stage/se_stage_%s.%s" % (place, extension)
            theirs = "sound/bank/stage/se_stage_%s.%s" % (sound_donor, extension)
        return (
            ours in paths
            or extension in shared_sound
            or (vanilla_files is not None and theirs in vanilla_files)
        )

    if vanilla_files is not None and not sound_resolves("nus3bank"):
        warn(
            "no stage sound bank: this pack ships none and %s has none to borrow, "
            "so the stage is silent. Ship sound/bank/stage/se_stage_%s.nus3bank, "
            ".nus3audio and .tonelabel, or borrow them from a stage that has them."
            % (sound_donor, place)
        )

    if vanilla_files is not None:
        cam_donor = settings.get("content_donor") or settings.get("donor") or place
        cam_tree = settings.get("content_donor_tree") or "normal"
        donor_camera = "stage/%s/%s/motion/camera" % (cam_donor, cam_tree)
        ours_camera = "stage/%s/normal/motion/camera" % place
        if any(f.startswith(donor_camera + "/") for f in vanilla_files):
            if any(p.startswith(ours_camera + "/") for p in paths):
                pass
            elif any(p.startswith("stage/%s/normal/motion/" % place) for p in paths):
                warn(
                    "%s has camera animations (%s) and this pack ships motion files "
                    "but no camera. stage/%s/normal/motion is then yours with only "
                    "the camera borrowed, a mix nothing has tested. Ship %s/ "
                    "yourself, or drop the motion files so the whole motion tree "
                    "is borrowed." % (cam_donor, donor_camera, place, ours_camera)
                )
            else:
                note(
                    "camera animations are inherited whole from %s (%s)"
                    % (cam_donor, donor_camera)
                )

    stage_sounds = {}
    for path in paths:
        if not path.startswith("sound/bank/stage/"):
            continue
        stem, _, extension = path.rsplit("/", 1)[1].rpartition(".")
        if stem.startswith("se_stage_"):
            stage_sounds.setdefault(stem[len("se_stage_"):], set()).add(extension)
    for owner, extensions in sorted(stage_sounds.items()):
        if owner in declared_places and owner != place:
            continue
        if owner != place:
            error(
                "sound/bank/stage/se_stage_%s.* is named for %r, but the stage id "
                "row asks for se_stage_%s.*, so nothing ever requests these files"
                % (owner, owner, place)
            )
            continue
        if not sound_resolves("nus3audio"):
            warn(
                "sound/bank/stage/se_stage_%s.nus3audio is missing, so the bank "
                "indexes samples that are not there" % place
            )
        if "nus3bank" in extensions and stage_bank_ids is not None:
            bank = os.path.join(mod_dir, "sound", "bank", "stage",
                                "se_stage_%s.nus3bank" % place)
            current = stage_bank_ids.read_bank_id(bank)
            wanted = stage_bank_ids.free_bank_id(place)
            if current is None:
                warn("%s has no GRP chunk, so it carries no bank id" % bank)
            elif current in stage_bank_ids.VANILLA_BANK_IDS:
                owner = stage_bank_ids.VANILLA_BANK_IDS[current]
                note(
                    "sound/bank/stage/se_stage_%s.nus3bank has bank id %d, which is "
                    "%s's (this bank started as a copy). Harmless while only one "
                    "stage loads at a time; %s free ids (%d..%d) exist, and "
                    "--write-bank-id gives the bank one."
                    % (place, current, owner, len(stage_bank_ids.FREE),
                       stage_bank_ids.FREE[0], stage_bank_ids.FREE[-1])
                )
            elif not (stage_bank_ids.BAND[0] <= current <= stage_bank_ids.BAND[1]):
                note(
                    "sound/bank/stage/se_stage_%s.nus3bank has bank id %d, outside "
                    "the %d..%d every stage bank in the game uses."
                    % (place, current, stage_bank_ids.BAND[0], stage_bank_ids.BAND[1])
                )
            else:
                note("sound/bank/stage/se_stage_%s.nus3bank holds free bank id %d"
                     % (place, current))
        if "nus3bank" in extensions and not sound_resolves("tonelabel"):
            warn(
                "sound/bank/stage/se_stage_%s.nus3bank ships without its tonelabel, "
                "so its sounds cannot be found by name. The two always go together."
                % place
            )
    for path in paths:
        if not path.startswith("sound/sequence/stage/") or not path.endswith(".sqb"):
            continue
        owner = path.rsplit("/", 1)[1][:-len(".sqb")]
        if owner in declared_places and owner != place:
            continue
        if owner != place:
            error(
                "sound/sequence/stage/%s.sqb is named for %r, but the stage id row "
                "asks for %s.sqb" % (owner, owner, place)
            )
            continue
        if stage_sqb_tones is None:
            continue
        owners = stage_sqb_tones.sqb_tone_owners(os.path.join(mod_dir, *path.split("/")))
        referenced = owners[0][0] if owners else None
        if referenced is None:
            warn(
                "sound/sequence/stage/%s.sqb references no tone that any vanilla stage "
                "bank names, so nothing it asks for can resolve" % place
            )
        elif referenced != sound_donor and referenced != place:
            error(
                "sound/sequence/stage/%s.sqb is %s's: it names %d of that stage's "
                "sounds and none of yours, so it can never play anything from your "
                "bank." % (place, referenced, owners[0][1])
            )
        if sound_donor not in stage_sqb_tones.VANILLA_SQB and referenced != place:
            warn(
                "%s ships no sqb in the game (only 25 stages do), so a pack rehoused "
                "from it usually should not ship one either" % sound_donor
            )

    stray = sorted(
        {path.split("/", 1)[0] + "/" for path in paths
         if "/" in path and not path.startswith(KNOWN_TREES)}
    )
    if stray:
        warn(
            "ships file(s) under %s. Music is not tied to a stage, so this replaces "
            "the track for every stage. Ship it as a separate mod if that is what "
            "you want." % ", ".join(stray)
        )

    patched_art = sorted(
        path for path in paths
        if path.startswith("ui/replace_patch/stage/") and path.endswith(".bntx")
    )
    if patched_art:
        warn(
            "%d stage-select icon(s) are under ui/replace_patch/. A clone stage "
            "finds its art under %s<N>/, so move them there (for example %s)."
            % (len(patched_art), MINTED_ART_PREFIX,
               patched_art[0].replace("ui/replace_patch/", "ui/replace/", 1))
        )

    disp_order = settings.get("disp_order", -1)
    if isinstance(disp_order, int) and disp_order > 255:
        error("disp_order %d cannot be expressed; the node is a u8" % disp_order)
    elif isinstance(disp_order, int) and disp_order > 127:
        warn(
            "disp_order %d is above what CSK's SignedByteType carries, so the row "
            "registers hidden and stage_db_rows promotes it afterwards" % disp_order
        )

    setting_no = settings.get("bgm_setting_no")
    if setting_no is not None and (
        not isinstance(setting_no, int) or not 0 <= setting_no <= 15
    ):
        error(
            "bgm_setting_no %r is outside 0..15; a playlist has sixteen columns"
            % (setting_no,)
        )
    if setting_no is not None and settings.get("bgm") is None:
        warn(
            "bgm_setting_no is set but bgm is not, so the column applies to "
            "whatever playlist the donor uses"
        )

    donor = settings.get("donor", "battlefield")
    content_donor = settings.get("content_donor", donor)
    if vanilla_dirs and ("stage/%s" % donor) not in vanilla_dirs:
        error("donor %r is not a stage in data.arc" % donor)
    if content_donor != donor and vanilla_dirs and (
        "stage/%s" % content_donor
    ) not in vanilla_dirs:
        error("content_donor %r is not a stage in data.arc" % content_donor)

    content_donor_tree = settings.get("content_donor_tree")
    if content_donor_tree is not None:
        if content_donor_tree not in ("normal", "battle"):
            error("content_donor_tree must be 'normal' or 'battle'")
        elif vanilla_dirs and (
            "stage/%s/%s" % (content_donor, content_donor_tree)
        ) not in vanilla_dirs:
            error(
                "content donor %r has no %r tree in data.arc"
                % (content_donor, content_donor_tree)
            )

    carry_donor_scenery = settings.get("carry_donor_scenery", True)

    generated = build_config(mod_dir, place, content_donor, forms, declared,
                             vanilla_dirs, vanilla_files, carry_donor_scenery,
                             content_donor_tree, stdat_donor=donor)

    inherited = sorted(
        directory for directory in generated.get("new-dir-infos-base", {})
        if is_donor_scenery(directory)
    )
    if inherited and "donor" not in settings:
        warn(
            "no behaviour donor, so every model set is shown at once, and %d of "
            "the donor's scenery folders are still borrowed and will draw over "
            "yours (%s%s). Set carry_donor_scenery = false if that is not wanted."
            % (len(inherited), ", ".join(inherited[:3]),
               ", ..." if len(inherited) > 3 else "")
        )
    config_path = os.path.join(mod_dir, "config.json")

    if os.path.exists(config_path):
        with open(config_path, encoding="utf8") as handle:
            previous = json.load(handle)
        for directory, files in previous.get("new-dir-files", {}).items():
            if directory.endswith(PROBE_SUFFIX):
                generated.setdefault("new-dir-files", {})[directory] = files
        carried = carry_foreign(previous, generated, place,
                                [other for other in declared_places if other != place])
        if carried:
            note("carried over %d config entry(s) that belong to other content in "
                 "this pack, such as a fighter, an item or another stage" % carried)

    if write_config:
        with open(config_path, "w", encoding="utf8") as handle:
            json.dump(generated, handle, indent=2)
            handle.write("\n")
        findings.append(("INFO", "wrote %s" % config_path))
        config = generated
    elif os.path.exists(config_path):
        with open(config_path, encoding="utf8") as handle:
            config = json.load(handle)
    else:
        error("no config.json; run with --write-config to generate it")
        config = {}

    shared_targets = {
        target
        for targets in (config.get("share-to-vanilla") or {}).values()
        for target in targets
    }
    for path in sorted(shared_targets & set(paths)):
        error(
            "%s is both shipped as a file and listed as a share-to-vanilla "
            "target; a path can only be one or the other, and the shipped copy "
            "wins" % path
        )

    if config:
        findings.extend(check_config(config, place, tree, forms, declared))
        findings.extend(check_effect_group(config, place, content_donor, vanilla_files))
        sources = donor_tree_sources(
            arc_trees(forms, declared),
            content_donor,
            vanilla_dirs,
            content_donor_tree,
        )
        findings.extend(
            check_donor_coverage(config, place, content_donor, vanilla_files, sources)
        )
        findings.extend(
            check_found_by_extension(config, place, content_donor, vanilla_files, sources)
        )
        findings.extend(check_stdat_names(config, place, donor, vanilla_files))
        findings.extend(check_borrowed_sources_replaced(config, mod_dir, place))
    findings.extend(
        check_stage_config(mod_dir, place, donor if "donor" in settings else None)
    )

    return findings


def read_stage_config(path):
    """`{section: {key: raw}}` from a `config_stage.toml`, flat-parsed."""
    sections = {}
    current = None
    try:
        handle = open(path, encoding="utf8")
    except OSError:
        return sections
    with handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1].strip()
                sections.setdefault(current, {})
            elif "=" in line and current is not None:
                key, _, value = line.partition("=")
                sections[current][key.strip()] = value.strip()
    return sections


def normalised_stage_name(name):
    return name.replace("_", "").lower()


ENUM_NAMES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "stage_id_enum_names.txt"
)


def stage_id_enum_name(place):
    try:
        with open(ENUM_NAMES_PATH, encoding="utf8") as handle:
            blob = "".join(
                line.strip() for line in handle if not line.startswith("#")
            )
    except OSError:
        return None
    flat = blob.replace("_", "").lower()
    target = place.replace("_", "").lower()
    at = flat.find(target)
    if at < 0:
        return None
    out, seen, started = [], 0, False
    for character in blob:
        if seen == at:
            started = True
        if started:
            out.append(character)
        if character != "_":
            seen += 1
        if started and sum(1 for c in out if c != "_") == len(target):
            break
    return "".join(out)


def check_stage_config(mod_dir, place, donor):
    findings = []
    ours = read_stage_config(os.path.join(mod_dir, "config_stage.toml"))
    if not ours:
        return findings
    for section, entries in ours.items():
        for key in entries:
            if donor is None:
                findings.append((
                    "WARN",
                    "config_stage.toml [%s] keys %r, but this pack has no behaviour "
                    "donor, so the setting applies to the vanilla stage %r and never "
                    "to this one. Delete it, or set a donor it belongs to."
                    % (section, key, key),
                ))
                continue
            if normalised_stage_name(key) != normalised_stage_name(donor):
                wanted = stage_id_enum_name(donor)
                findings.append((
                    "ERROR",
                    "config_stage.toml [%s] keys %r, which is not this pack's "
                    "behaviour donor %r. The setting applies to that vanilla stage "
                    "instead of this one, and %r's own setting is lost too. %s"
                    % (section, key, donor, key,
                       "Use %r." % wanted if wanted else
                       "No enum name is known for %r." % donor),
                ))

    root = os.path.dirname(os.path.abspath(mod_dir.rstrip("/\\")))
    us = os.path.basename(os.path.abspath(mod_dir.rstrip("/\\")))
    try:
        siblings = sorted(os.listdir(root))
    except OSError:
        return findings
    for name in siblings:
        if name == us:
            continue
        theirs = read_stage_config(os.path.join(root, name, "config_stage.toml"))
        for section, entries in theirs.items():
            for key, value in entries.items():
                if key not in ours.get(section, {}):
                    continue
                if section == "discard_stage_code":
                    continue
                same = ours[section][key] == value
                findings.append((
                    "WARN" if same else "ERROR",
                    "config_stage.toml [%s] %r is also set by %r%s. Only one of "
                    "the two applies, and which one is not under your control. %s"
                    % (section, key, name,
                       " to the same value" if same else " to a DIFFERENT value",
                       "Harmless only while the values agree."
                       if same else "One of these two packs loses its setting."),
                ))
    return findings


def check_effect_group(config, place, donor, vanilla_files):
    if vanilla_files is None:
        return []
    theirs = "effect/stage/%s" % donor
    if not any(directory_of(path) == theirs for path in vanilla_files):
        return []
    ours = "effect/stage/%s" % place
    if config.get("new-dir-files", {}).get(ours):
        return []
    if ours in config.get("new-dir-infos-base", {}):
        return []
    return [(
        "ERROR",
        "%s is empty but the donor's %s has a file. An empty effect folder "
        "crashes at match load. Re-run with --write-config to borrow the "
        "donor's .eff." % (ours, theirs),
    )]


def check_donor_coverage(config, place, donor, vanilla_files, tree_sources=None):
    if vanilla_files is None:
        return []
    findings = []
    dir_files = config.get("new-dir-files", {})
    based = config.get("new-dir-infos-base", {})
    by_donor_dir = {}
    for path in vanilla_files:
        by_donor_dir.setdefault(directory_of(path), []).append(path)
    for created in sorted(set(config.get("new-dir-infos", []))):
        if created in based:
            continue
        theirs = donor_counterpart(created, place, donor, tree_sources)
        if theirs == created:
            continue
        theirs_count = len(by_donor_dir.get(theirs, ()))
        ours_count = len(dir_files.get(created, ()))
        if ours_count >= theirs_count:
            continue
        missing = sorted(
            path.rsplit("/", 1)[1] for path in by_donor_dir.get(theirs, ())
        )
        findings.append((
            "ERROR",
            "%s lists %d file(s) but the donor's %s has %d. A folder this pack "
            "creates gets nothing from the donor, so anything not listed is "
            "missing. The donor has: %s. Re-run with --write-config."
            % (created, ours_count, theirs, theirs_count, ", ".join(missing)),
        ))
    return findings


def sibling_mods(mod_dir):
    """The other mod folders installed beside this pack, as (name, path)."""
    parent = os.path.dirname(os.path.abspath(mod_dir))
    own = os.path.basename(os.path.abspath(mod_dir))
    try:
        names = sorted(os.listdir(parent))
    except OSError:
        return []
    out = []
    for name in names:
        if name == own or name.startswith("."):
            continue
        path = os.path.join(parent, name)
        if os.path.isdir(path):
            out.append((name, path))
    return out


def check_borrowed_sources_replaced(config, mod_dir, place):
    """A file this stage borrows is replaced by another installed mod."""
    findings = []
    siblings = sibling_mods(mod_dir)
    if not siblings:
        return findings
    borrowed = []
    for source, targets in sorted((config.get("share-to-vanilla") or {}).items()):
        ours = [t for t in targets if t.startswith("stage/%s/" % place)]
        if ours:
            borrowed.append((source, ours[0], False))
    for ours, base in sorted((config.get("new-dir-infos-base") or {}).items()):
        if ours.startswith("stage/%s/" % place):
            borrowed.append((base, ours, True))
    for source, ours, is_dir in borrowed:
        for name, path in siblings:
            candidate = os.path.join(path, source.replace("/", os.sep))
            if is_dir:
                hit = os.path.isdir(candidate) and any(
                    files for _, _, files in os.walk(candidate))
            else:
                hit = os.path.isfile(candidate)
            if not hit:
                continue
            what = "the directory" if is_dir else "the file"
            findings.append((
                "WARN",
                "%s is borrowed as %s, and the mod '%s' replaces %s at that path. "
                "Stages in this position have loaded to a black screen. Ship your "
                "own copy as %s, so this stage does not depend on other mods."
                % (source, ours, name, what, ours),
            ))
            break
    return findings


def check_config(config, place, tree, forms, ships_battle_tree):
    findings = []
    dir_infos = set(config.get("new-dir-infos", []))
    bases = config.get("new-dir-infos-base", {})
    dir_files = config.get("new-dir-files", {})

    for directory, files in sorted(tree.items()):
        if directory not in dir_infos:
            findings.append((
                "ERROR",
                "%s ships %d file(s) but is not in new-dir-infos"
                % (directory, len(files)),
            ))
        listed = set(dir_files.get(directory, []))
        missing = sorted(set(files) - listed)
        if missing:
            findings.append((
                "ERROR",
                "%s: %d shipped file(s) are not in new-dir-files, so they are "
                "added standalone and the directory load will never see them "
                "(first: %s)" % (directory, len(missing), missing[0]),
            ))
        if directory in bases:
            findings.append((
                "ERROR",
                "%s ships files and also has a new-dir-infos-base, so its file "
                "range is the donor's and its own files are unreachable"
                % directory,
            ))

    tree_roots = {
        "stage/%s/%s" % (place, name)
        for name in arc_trees(forms, ships_battle_tree)
    }
    ancestors = set(tree_roots)
    ancestors.add("stage/%s" % place)
    for directory in tree:
        ancestors.update(all_parents(directory))
    for directory in sorted(ancestors & set(bases)):
        findings.append((
            "ERROR",
            "%s must not be in new-dir-infos-base: it would take the donor's "
            "subfolders and lose every folder this pack adds under it" % directory,
        ))
    for root in sorted(tree_roots):
        if root not in dir_infos and root not in bases:
            findings.append(("ERROR", "%s is in neither new-dir-infos nor bases" % root))

    for name in ("omega", "battlefield"):
        stray = "stage/%s/%s" % (place, name)
        if stray in dir_infos or stray in bases:
            findings.append((
                "ERROR",
                "%s is not a stage directory: the arc trees are `normal` and "
                "`battle`, and the Omega/Battlefield forms resolve to one of "
                "those" % stray,
            ))

    for directory in sorted(dir_files):
        if directory.endswith(PROBE_SUFFIX):
            findings.append((
                "INFO",
                "%s is deliberate: it makes ARCropolis log 'Cannot get file info "
                "range', which proves the config was read" % directory,
            ))
            continue
        if is_vanilla_file_host(directory):
            continue
        if directory not in dir_infos and directory not in bases:
            findings.append((
                "ERROR",
                "new-dir-files names %s, which no new-dir-infos creates"
                % directory,
            ))

    overlap = sorted(dir_infos & set(bases))
    for directory in overlap:
        findings.append((
            "WARN",
            "%s is in both new-dir-infos and new-dir-infos-base; the base wins"
            % directory,
        ))

    return findings


def main(argv):
    parser = argparse.ArgumentParser(
        description="Check a stage pack, and write its config.json from the files it ships."
    )
    parser.add_argument("mod_dir", help="your mod folder")
    parser.add_argument("--arc-index", default=DEFAULT_ARC_INDEX, metavar="DIR",
                        help="folder holding arc_files.tsv (default: beside this script)")
    parser.add_argument(
        "--write-config",
        action="store_true",
        help="write config.json from the files on disk, then check it",
    )
    parser.add_argument(
        "--write-bank-id",
        action="store_true",
        help="give the pack's own sound bank a free id, then check it",
    )
    arguments = parser.parse_args(argv)

    if arguments.write_bank_id:
        places = [settings.get("place") for settings
                  in read_stage_tomls(os.path.join(arguments.mod_dir, "stage.toml"))
                  if settings.get("place")]
        if not places:
            print("ERROR no place in stage.toml")
            return 1
        for place in places:
            bank = os.path.join(arguments.mod_dir, "sound", "bank", "stage",
                                "se_stage_%s.nus3bank" % place)
            if not os.path.exists(bank):
                if len(places) == 1:
                    print("ERROR %s does not exist; there is no bank to stamp" % bank)
                    return 1
                continue
            was = stage_bank_ids.read_bank_id(bank)
            wanted = stage_bank_ids.free_bank_id(place)
            if was is not None and was not in stage_bank_ids.VANILLA_BANK_IDS \
                    and stage_bank_ids.BAND[0] <= was <= stage_bank_ids.BAND[1]:
                print("INFO  %s already holds free bank id %d" % (bank, was))
            elif stage_bank_ids.write_bank_id(bank, wanted):
                print("INFO  %s bank id %s -> %d" % (bank, was, wanted))
            else:
                print("ERROR %s has no GRP chunk to stamp" % bank)
                return 1

    findings = lint(arguments.mod_dir, arguments.arc_index, arguments.write_config)
    errors = 0
    for level, message in findings:
        print("%-5s %s" % (level, message))
        errors += level == "ERROR"
    print()
    print("%d error(s), %d note(s)" % (errors, len(findings) - errors))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
