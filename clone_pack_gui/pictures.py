#!/usr/bin/env python3
"""Pictures as RGBA bytes: read with Pillow when it is installed, else 8-bit PNGs by hand."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class PictureError(Exception):
    pass


def read(path) -> tuple[int, int, bytes]:
    """(width, height, RGBA bytes) of a picture file."""
    try:
        from PIL import Image
    except ImportError:
        return read_png(Path(path).read_bytes())
    try:
        with Image.open(path) as image:
            image = image.convert("RGBA")
            return image.width, image.height, image.tobytes()
    except OSError as error:
        raise PictureError("%s is not a picture Pillow can read (%s)" % (Path(path).name, error))


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_png(data: bytes) -> tuple[int, int, bytes]:
    """An 8-bit, non-interlaced PNG as (width, height, RGBA bytes)."""
    if data[:8] != SIGNATURE:
        raise PictureError("not a PNG; install Pillow (pip install pillow) to read other pictures")
    at, idat, palette, alpha = 8, b"", b"", b""
    width = height = depth = color = interlace = None
    while at + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[at:at + 8])
        body = data[at + 8:at + 8 + length]
        at += 12 + length
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            alpha = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if width is None or color not in CHANNELS:
        raise PictureError("a PNG this reader does not know")
    if depth != 8 or interlace:
        raise PictureError("only 8-bit, non-interlaced PNGs without Pillow (pip install pillow)")
    channels = CHANNELS[color]
    stride = width * channels
    raw = zlib.decompress(idat)
    rows, previous, at = [], bytearray(stride), 0
    for _ in range(height):
        kind, line = raw[at], bytearray(raw[at + 1:at + 1 + stride])
        at += 1 + stride
        if kind == 1:
            for x in range(channels, stride):
                line[x] = (line[x] + line[x - channels]) & 0xFF
        elif kind == 2:
            line = bytearray((a + b) & 0xFF for a, b in zip(line, previous))
        elif kind == 3:
            for x in range(stride):
                left = line[x - channels] if x >= channels else 0
                line[x] = (line[x] + ((left + previous[x]) >> 1)) & 0xFF
        elif kind == 4:
            for x in range(stride):
                left = line[x - channels] if x >= channels else 0
                corner = previous[x - channels] if x >= channels else 0
                line[x] = (line[x] + paeth(left, previous[x], corner)) & 0xFF
        rows.append(bytes(line))
        previous = line
    pixels = b"".join(rows)
    if color == 6:
        return width, height, pixels
    out = bytearray(width * height * 4)
    for index in range(width * height):
        if color == 2:
            r, g, b = pixels[index * 3:index * 3 + 3]
            a = 255
        elif color == 0:
            r = g = b = pixels[index]
            a = 255
        elif color == 4:
            r = g = b = pixels[index * 2]
            a = pixels[index * 2 + 1]
        else:
            entry = pixels[index]
            r, g, b = palette[entry * 3:entry * 3 + 3]
            a = alpha[entry] if entry < len(alpha) else 255
        out[index * 4:index * 4 + 4] = bytes((r, g, b, a))
    return width, height, bytes(out)


def cover(picture: tuple[int, int, bytes], width: int, height: int) -> bytes:
    """The picture cropped to the size's shape around its centre, then scaled to it."""
    source_width, source_height, pixels = picture
    scale = max(width / source_width, height / source_height)
    crop_width, crop_height = width / scale, height / scale
    left, top = (source_width - crop_width) / 2, (source_height - crop_height) / 2
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image is not None:
        image = Image.frombytes("RGBA", (source_width, source_height), pixels)
        box = (round(left), round(top), round(left + crop_width), round(top + crop_height))
        return image.resize((width, height), Image.LANCZOS, box=box).tobytes()
    out = bytearray(width * height * 4)
    for y in range(height):
        row = min(source_height - 1, int(top + (y + 0.5) * crop_height / height))
        for x in range(width):
            column = min(source_width - 1, int(left + (x + 0.5) * crop_width / width))
            start = (row * source_width + column) * 4
            out[(y * width + x) * 4:(y * width + x) * 4 + 4] = pixels[start:start + 4]
    return bytes(out)
