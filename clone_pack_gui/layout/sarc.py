"""SARC archives (`layout.arc`): read and write, little endian."""
import struct

HASH_KEY = 0x65
ALIGN = 0x80
TEXTURE_ALIGN = 0x1000
"""A BNTX declares 4096-byte alignment: its texture pool must start on it."""


def name_hash(name):
    value = 0
    for byte in name.encode():
        value = (value * HASH_KEY + byte) & 0xFFFFFFFF
    return value


def read(data):
    assert data[:4] == b"SARC", "not a SARC archive"
    header_size, bom = struct.unpack_from("<HH", data, 4)
    assert bom == 0xFEFF, "big endian SARC"
    data_offset = struct.unpack_from("<I", data, 12)[0]
    sfat = header_size
    assert data[sfat:sfat + 4] == b"SFAT"
    node_count = struct.unpack_from("<H", data, sfat + 6)[0]
    nodes = sfat + 12
    sfnt = nodes + node_count * 16
    assert data[sfnt:sfnt + 4] == b"SFNT"
    names = sfnt + 8
    files = {}
    for index in range(node_count):
        _, attributes, start, end = struct.unpack_from("<IIII", data, nodes + index * 16)
        name_at = names + (attributes & 0xFFFF) * 4
        name = data[name_at:data.index(b"\0", name_at)].decode()
        files[name] = data[data_offset + start:data_offset + end]
    return files


def alignment(name, align=ALIGN):
    return TEXTURE_ALIGN if name.endswith(".bntx") else align


def write(files, align=ALIGN):
    entries = sorted(files.items(), key=lambda item: name_hash(item[0]))
    largest = max([alignment(name, align) for name, _ in entries] + [align])
    names = b""
    name_offsets = []
    for name, _ in entries:
        name_offsets.append(len(names) // 4)
        raw = name.encode() + b"\0"
        names += raw + b"\0" * (-len(raw) % 4)
    header_size = 0x14
    sfat_size = 12 + 16 * len(entries)
    sfnt_size = 8 + len(names)
    data_offset = header_size + sfat_size + sfnt_size
    data_offset += -data_offset % largest
    blob = b""
    ranges = []
    for name, payload in entries:
        blob += b"\0" * (-len(blob) % alignment(name, align))
        ranges.append((len(blob), len(blob) + len(payload)))
        blob += payload
    out = bytearray()
    out += struct.pack("<4sHHIIHH", b"SARC", header_size, 0xFEFF, data_offset + len(blob), data_offset, 0x100, 0)
    out += struct.pack("<4sHHI", b"SFAT", 12, len(entries), HASH_KEY)
    for (name, _), offset, (start, end) in zip(entries, name_offsets, ranges):
        out += struct.pack("<IIII", name_hash(name), 0x01000000 | offset, start, end)
    out += struct.pack("<4sHH", b"SFNT", 8, 0) + names
    out += b"\0" * (data_offset - len(out))
    out += blob
    return bytes(out)
