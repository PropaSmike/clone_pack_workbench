#!/usr/bin/env python3
"""item_hand: which hand a fighter holds items in, and what the engine changes for a clone.

The rules are the engine's (dionysus_core/src/item_hand.rs): a base that holds items in a hand
has every hand bone mirrored when the clone picks the other hand; a base that holds them in its
mouth takes the picked hand for its hold bones and its swung-item bone."""

from __future__ import annotations

HANDS = ("left", "right")
HAND_BONES = {"left": "havel", "right": "haver"}
HAND_WORDS = ("haver", "havel")
NO_HAND_BONES = ("pfushigisou",)
BONE_NAMES = {"haver": "HaveR", "havel": "HaveL", "have": "have (mouth)", "": "none"}
ROWS = (("hold", "Held and thrown items"), ("hold2", "Held items, second grip"),
        ("other", "Other hand"), ("battering", "Swung item hitboxes (commonhave)"))


def remap(bone: str, main: str, hand: str) -> str:
    """One hold bone as the clone gets it."""
    side = HAND_BONES[hand]
    if main in HAND_WORDS:
        if main == side:
            return bone
        return {"haver": "havel", "havel": "haver"}.get(bone, bone)
    if bone == main or bone == "have" or bone in HAND_WORDS:
        return side
    return bone


def base_hand(row: dict | None) -> str:
    """left, right, mouth or "" when the base is unknown."""
    if not row:
        return ""
    return {"haver": "right", "havel": "left", "have": "mouth"}.get(row.get("hold", ""), "")


def describe_base(name: str, row: dict | None) -> str:
    if not row:
        return "%s is not a roster fighter, so its hold bones are unknown" % (name or "The base")
    where = {"right": "its right hand (HaveR)", "left": "its left hand (HaveL)",
             "mouth": "its mouth (have)"}.get(base_hand(row), BONE_NAMES.get(row.get("hold", ""), "?"))
    text = "%s holds items in %s" % (name, where)
    if row.get("battering") and row["battering"] != row.get("hold"):
        text += "; swung items hit from %s" % BONE_NAMES.get(row["battering"], row["battering"])
    if row.get("other") and row["other"] != row.get("hold"):
        text += "; its hold data names the other hand too (%s)" % BONE_NAMES.get(row["other"], row["other"])
    return text + "."


def changes(row: dict | None, hand: str) -> list[tuple[str, str, str]]:
    """(what, the base's bone, this fighter's bone) for each bone item_hand touches."""
    if not row:
        return []
    main = row.get("hold", "")
    out = []
    for key, label in ROWS:
        bone = row.get(key, "")
        mine = remap(bone, main, hand) if hand in HANDS and bone else bone
        out.append((label, BONE_NAMES.get(bone, bone), BONE_NAMES.get(mine, mine)))
    return out


def problem(base: str, hand: str) -> str:
    """Why the engine would refuse item_hand on this base, or ""."""
    if hand in HANDS and base in NO_HAND_BONES:
        return "%s has no HaveL or HaveR bone; the engine refuses item_hand on it" % base
    return ""
