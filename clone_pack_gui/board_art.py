#!/usr/bin/env python3
"""A DLC spirit board's art layout (banner and card) and its own background layout, from pictures."""

from __future__ import annotations

import sys
from pathlib import Path

from . import backups, pictures

HERE = Path(__file__).resolve().parent
LAYOUT_DIRS = (HERE / "layout", HERE.parent / "modes" / "layout")
ART_FOLDER = "ui/layout/menu/dionysus_boards"
BACKGROUND = "ui/layout/patch/spirits_board_special_bg_%02d/spirits_board_special_bg_%02d/layout.arc"
GAME_BACKGROUNDS = 11
BANNER = (462, 92)
CARD = (460, 796)
BACKGROUND_TEXTURE = (1280, 720)
BACKGROUND_PANE = (2000, 1100)


def builder():
    """The layout writer: build and bntx, beside this package or in tools/modes/layout."""
    for folder in LAYOUT_DIRS:
        if (folder / "build.py").is_file():
            if str(folder) not in sys.path:
                sys.path.insert(0, str(folder))
            import bntx
            import build
            return build, bntx
    raise pictures.PictureError("the layout writer (layout/build.py) is not beside this window")


def art_path(board: str) -> str:
    return "%s/spb_%s/layout.arc" % (ART_FOLDER, board)


def art_layout(board: str, banner: bytes, card: bytes) -> bytes:
    """A layout named spb_<board> with a banner and a card picture, both hidden until the popup shows them."""
    build, bntx = builder()
    layout = build.Layout("spb_%s" % board)
    banner_texture = layout.image(bntx.Texture("spb_banner", "rgba8", BANNER[0], BANNER[1], banner))
    card_texture = layout.image(bntx.Texture("spb_card", "rgba8", CARD[0], CARD[1], card))
    layout.root.add(build.Picture("banner", BANNER[0], BANNER[1], texture=banner_texture, visible=False),
                    build.Picture("card", CARD[0], CARD[1], texture=card_texture, visible=False))
    return layout.archive()


def background_path(number: int) -> str:
    return BACKGROUND % (number, number)


def background_layout(number: int, picture: bytes) -> bytes:
    """A board background: one picture over the whole screen."""
    build, bntx = builder()
    layout = build.Layout("spirits_board_special_bg_%02d" % number)
    texture = layout.image(bntx.Texture("spb_background", "rgba8", BACKGROUND_TEXTURE[0], BACKGROUND_TEXTURE[1],
                                        picture))
    layout.root.add(build.Picture("background", BACKGROUND_PANE[0], BACKGROUND_PANE[1], texture=texture))
    return layout.archive()


def taken_backgrounds(folder: Path) -> dict:
    """{number: pack} for every own background this pack and the packs beside it ship."""
    folder = Path(folder)
    taken = {}
    packs = [folder] + sorted(entry for entry in folder.parent.iterdir() if entry.is_dir() and entry != folder) \
        if folder.parent.is_dir() else [folder]
    for pack in packs:
        root = pack / "ui" / "layout" / "patch"
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            name = entry.name
            if name.startswith("spirits_board_special_bg_") and name[25:].isdigit():
                number = int(name[25:])
                if number >= GAME_BACKGROUNDS and (pack / background_path(number)).is_file():
                    taken.setdefault(number, pack.name)
    return taken


def free_background(folder: Path) -> int:
    taken = taken_backgrounds(folder)
    number = GAME_BACKGROUNDS
    while number in taken:
        number += 1
    return number


def write(folder: Path, relative: str, data: bytes) -> Path:
    path = Path(folder).joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    backups.keep(path)
    path.write_bytes(data)
    return path


def make_art(folder: Path, board: str, banner_file, card_file) -> str:
    """Write the board's art layout from two pictures; returns its path in the pack."""
    banner = pictures.cover(pictures.read(banner_file), *BANNER)
    card = pictures.cover(pictures.read(card_file), *CARD)
    relative = art_path(board)
    write(folder, relative, art_layout(board, banner, card))
    return relative


def make_background(folder: Path, picture_file, number: int | None = None) -> int:
    """Write a board background from a picture: at the board's own number when no other installed pack
    ships it, else at a free one. Returns the number."""
    taken = taken_backgrounds(folder)
    if number is None or number < GAME_BACKGROUNDS or taken.get(number, Path(folder).name) != Path(folder).name:
        number = free_background(folder)
    picture = pictures.cover(pictures.read(picture_file), *BACKGROUND_TEXTURE)
    write(folder, background_path(number), background_layout(number, picture))
    return number
