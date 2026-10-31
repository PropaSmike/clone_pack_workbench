#!/usr/bin/env python3
"""Check an enemy pack: enemy.toml by the engine's rules, the enemy's folders and its motion list."""
import argparse
import json
import os
import re
import struct
import sys
import zlib

BASES = {"yellow_devil": "yellowdevil", "yellowdevil": "yellowdevil",
         "dark_emperor": "subetenoyaminoou", "subetenoyaminoou": "subetenoyaminoou",
         "flying_man": "flyingman", "flyingman": "flyingman",
         "metal_face": "metalface", "metalface": "metalface", "nabbit": "nabbit"}
FOLDERS = set(BASES.values())
MAX_NAME = 48
KEYS = {"name": "text", "base": "text"}
MOTION_LIST_FOLDER = 8


class EnemyError(ValueError):
    pass


def hash40(text):
    data = text.lower().encode()
    return (len(data) << 32) | zlib.crc32(data)


def strip_comment(line):
    quoted = False
    for index, character in enumerate(line):
        if character == '"':
            quoted = not quoted
        elif character == "#" and not quoted:
            return line[:index]
    return line


def valid_name(name):
    return (0 < len(name) <= MAX_NAME and name not in BASES
            and re.fullmatch(r"[a-z0-9_]+", name) is not None)


def parse(text):
    """(enemies, problems) as the engine reads enemy.toml: one flat enemy, or one per [[enemy]]."""
    blocks, current, problems = [], None, []
    for number, raw in enumerate(text.splitlines(), 1):
        line = strip_comment(raw).strip()
        if not line:
            continue
        if line == "[[enemy]]":
            current = {"line": number}
            blocks.append(current)
            continue
        if current is None:
            if blocks:
                problems.append(("ERROR", "line %d: a key outside any [[enemy]] block" % number))
                continue
            current = {"line": number}
            blocks.append(current)
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip()
        if not _:
            problems.append(("ERROR", "line %d: expected key = value" % number))
        elif key not in KEYS:
            problems.append(("ERROR", "line %d: unknown enemy key %s" % (number, key)))
        elif key == "name" and not valid_name(value):
            problems.append(("ERROR", 'line %d: name "%s" must be lower case letters, digits and _, up to %d, '
                                      "and not a game enemy's" % (number, value, MAX_NAME)))
        elif key == "base" and value.lower() not in BASES:
            problems.append(("ERROR", 'line %d: base "%s" is not yellow_devil, dark_emperor, flying_man, '
                                      "metal_face or nabbit" % (number, value)))
        else:
            current[key] = value.lower() if key == "base" else value
    enemies = []
    for block in blocks:
        for key in ("name", "base"):
            if key not in block:
                problems.append(("ERROR", "line %d: an enemy needs %s" % (block["line"], key)))
        if "name" in block and "base" in block:
            enemies.append({"name": block["name"], "base": BASES[block["base"]], "line": block["line"]})
    return enemies, problems


def shipped(mod_dir, name):
    """Every file the pack ships for this enemy, as game paths."""
    out = []
    for root in ("enemy/%s" % name, "effect/enemy/%s" % name):
        top = os.path.join(mod_dir, *root.split("/"))
        for folder, _, files in os.walk(top):
            for file in files:
                out.append(os.path.relpath(os.path.join(folder, file), mod_dir).replace(os.sep, "/"))
    return sorted(out)


def folder_of(path, name):
    """The folder the game loads a file of this enemy through."""
    effect = "effect/enemy/%s/" % name
    if path.startswith(effect):
        rest = path[len(effect):]
        folder = "enemy/%s/effect" % name
        if "/" in rest:
            folder += "/" + rest.rsplit("/", 1)[0].replace("model/", "", 1)
        return folder
    return path.rsplit("/", 1)[0]


def config_entries(mod_dir, name):
    """new-dir-infos and new-dir-files for one enemy, from the files on disk."""
    held = {}
    for path in shipped(mod_dir, name):
        held.setdefault(folder_of(path, name), []).append(path)
    effects = sorted(path for paths in held.values() for path in paths if path.startswith("effect/enemy/"))
    if effects:
        held["effect/enemy/%s" % name] = effects
    infos = ["enemy/%s" % name]
    for folder in sorted(held):
        parts = folder.split("/")
        for depth in range(3, len(parts) + 1):
            prefix = "/".join(parts[:depth])
            if prefix not in infos:
                infos.append(prefix)
    return infos, {folder: sorted(paths) for folder, paths in held.items()}


def read_config(mod_dir):
    path = os.path.join(mod_dir, "config.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf8") as handle:
        return json.load(handle)


def write_config(mod_dir, names):
    """config.json with each enemy's folders and files, keeping every other entry."""
    config = read_config(mod_dir)
    infos = [info for info in config.get("new-dir-infos", [])
             if not any(info == "enemy/%s" % name or info.startswith(("enemy/%s/" % name, "effect/enemy/%s" % name))
                        for name in names)]
    files = {folder: paths for folder, paths in config.get("new-dir-files", {}).items()
             if not any(folder.startswith(("enemy/%s" % name, "effect/enemy/%s" % name)) for name in names)}
    for name in names:
        more_infos, more_files = config_entries(mod_dir, name)
        infos += more_infos
        files.update(more_files)
    config["new-dir-infos"] = infos
    config.setdefault("new-dir-infos-base", {})
    config["new-dir-files"] = files
    with open(os.path.join(mod_dir, "config.json"), "w", encoding="utf8", newline="\n") as handle:
        handle.write(json.dumps(config, indent=2) + "\n")


def motion_list(mod_dir, name):
    return os.path.join(mod_dir, "enemy", name, "motion", "body", "c00", "motion_list.bin")


def motion_list_problem(mod_dir, name):
    path = motion_list(mod_dir, name)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        head = handle.read(MOTION_LIST_FOLDER + 8)
    if len(head) < MOTION_LIST_FOLDER + 8:
        return "is too short to name a folder"
    word = struct.unpack_from("<Q", head, MOTION_LIST_FOLDER)[0]
    wanted = hash40("enemy/%s/motion/body/c00" % name)
    return None if word == wanted else "names another folder at offset 8, so the enemy plays the base's animations"


def fix_motion_list(mod_dir, name):
    path = motion_list(mod_dir, name)
    with open(path, "rb") as handle:
        data = bytearray(handle.read())
    struct.pack_into("<Q", data, MOTION_LIST_FOLDER, hash40("enemy/%s/motion/body/c00" % name))
    with open(path, "wb") as handle:
        handle.write(bytes(data))


def lint(mod_dir, arc_index=None):
    path = os.path.join(mod_dir, "enemy.toml")
    if not os.path.isfile(path):
        return [("ERROR", "no enemy.toml in %s" % mod_dir)]
    with open(path, encoding="utf8", errors="replace") as handle:
        enemies, findings = parse(handle.read())
    if any(level == "ERROR" for level, _ in findings):
        findings.append(("ERROR", "the engine skips this whole enemy.toml"))
        return findings
    config = read_config(mod_dir)
    infos = set(config.get("new-dir-infos", []))
    for enemy in enemies:
        name = enemy["name"]
        files = shipped(mod_dir, name)
        if not files:
            findings.append(("WARN", "%s ships no files under enemy/%s/; it uses %s's" % (name, name, enemy["base"])))
            continue
        model = "enemy/%s/model/body/c00/model.numdlb" % name
        if model not in files:
            findings.append(("WARN", "%s has no %s; copy %s's model and change it" % (name, model, enemy["base"])))
        wanted, _ = config_entries(mod_dir, name)
        missing = [info for info in wanted if info not in infos]
        if missing:
            findings.append(("ERROR", "%s: %s%s not in config.json's new-dir-infos, so the game never loads "
                                      "them; --fix-config writes them"
                             % (name, missing[0], " and %d more are" % (len(missing) - 1) if len(missing) > 1
                                else " is")))
        problem = motion_list_problem(mod_dir, name)
        if problem:
            findings.append(("ERROR", "%s: motion_list.bin %s; --fix-motion-list fixes it" % (name, problem)))
        findings.append(("INFO", "%s on %s: %d file(s); its plugin spawns and drives it (the Workbench's Rust tab "
                                 "writes one)" % (name, enemy["base"], len(files))))
    findings.append(("INFO", "enemy.toml needs an engine newer than 0.6.0-beta.1"))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mod_dir")
    parser.add_argument("--fix-config", action="store_true", help="write each enemy's folders into config.json")
    parser.add_argument("--fix-motion-list", action="store_true",
                        help="make each motion_list.bin name its own folder")
    args = parser.parse_args(argv)
    path = os.path.join(args.mod_dir, "enemy.toml")
    if (args.fix_config or args.fix_motion_list) and os.path.isfile(path):
        with open(path, encoding="utf8", errors="replace") as handle:
            enemies, problems = parse(handle.read())
        if not any(level == "ERROR" for level, _ in problems):
            if args.fix_config:
                write_config(args.mod_dir, [enemy["name"] for enemy in enemies])
            if args.fix_motion_list:
                for enemy in enemies:
                    if os.path.isfile(motion_list(args.mod_dir, enemy["name"])):
                        fix_motion_list(args.mod_dir, enemy["name"])
    findings = lint(args.mod_dir)
    for level, message in findings:
        print("%-5s %s" % (level, message))
    return 1 if any(level == "ERROR" for level, _ in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
