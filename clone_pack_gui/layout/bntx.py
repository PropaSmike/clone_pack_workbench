"""BNTX texture archives (Switch, little endian) with any number of textures.

A layout's textures live in one `timg/__Combined.bntx`; its txl1 names them.
Surfaces are Tegra block linear (64-byte by 8-row GOBs stacked `block
height` high); `read` and `write` take and give linear mip 0 data.

    python bntx.py <file.bntx>                    list the textures
    python bntx.py <file.bntx> <name> <out.png>   export one (rgba8 only)
"""
import struct
import sys

FORMATS = {
    "rgba8": (0x0B01, 4, 1),
    "rgba8_srgb": (0x0B06, 4, 1),
    "bc1": (0x1A01, 8, 4),
    "bc1_srgb": (0x1A06, 8, 4),
    "bc3": (0x1C01, 16, 4),
    "bc3_srgb": (0x1C06, 16, 4),
    "bc4": (0x1D01, 8, 4),
    "bc5": (0x1E01, 16, 4),
    "bc7": (0x2001, 16, 4),
    "bc7_srgb": (0x2006, 16, 4),
}
FORMAT_NAMES = {code: name for name, (code, _, _) in FORMATS.items()}
RGBA = 0x05040302
ALPHA_FROM_RED = 0x02010101
LUMINANCE_ALPHA = 0x03020202
CHANNELS = {"bc4": ALPHA_FROM_RED, "bc5": LUMINANCE_ALPHA}

FILE_ALIGN = 0x1000
SURFACE_ALIGN = 0x200
POOL = 0x58
POOL_SIZE = 0x140
BRTI_SIZE = 0xA0
BRTI_BLANK = 0x200
GPU_ACCESS_TEXTURE = 32
LAYOUT = 0x10007


def align(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def block_height_log2(rows):
    rows += rows // 2
    for log2, limit in ((4, 128), (3, 64), (2, 32), (1, 16)):
        if rows >= limit:
            return log2
    return 0


def surface_shape(fmt, width, height):
    _, block_bytes, block = FORMATS[fmt]
    columns = (width + block - 1) // block
    rows = (height + block - 1) // block
    return columns * block_bytes, rows


def surface_size(width_bytes, rows, bh_log2):
    gobs = (width_bytes + 63) // 64
    tall = 8 << bh_log2
    return gobs * 512 * (1 << bh_log2) * ((rows + tall - 1) // tall)


def gob_offset(x, y, gobs_wide, bh_log2):
    bh = 1 << bh_log2
    tall = 8 * bh
    base = (y // tall) * 512 * bh * gobs_wide + (x // 64) * 512 * bh + ((y % tall) // 8) * 512
    return (base + ((x % 64) // 32) * 256 + ((y % 8) // 2) * 64 + ((x % 32) // 16) * 32
            + (y % 2) * 16 + (x % 16))


def swizzle(linear, width_bytes, rows, bh_log2):
    out = bytearray(surface_size(width_bytes, rows, bh_log2))
    gobs = (width_bytes + 63) // 64
    for y in range(rows):
        line = y * width_bytes
        for x in range(0, width_bytes, 16):
            at = gob_offset(x, y, gobs, bh_log2)
            out[at:at + 16] = linear[line + x:line + x + 16]
    return bytes(out)


def deswizzle(surface, width_bytes, rows, bh_log2):
    out = bytearray(width_bytes * rows)
    gobs = (width_bytes + 63) // 64
    for y in range(rows):
        line = y * width_bytes
        for x in range(0, width_bytes, 16):
            at = gob_offset(x, y, gobs, bh_log2)
            out[line + x:line + x + 16] = surface[at:at + 16]
    return bytes(out)


class Texture:
    def __init__(self, name, fmt, width, height, data, channels=None):
        width_bytes, rows = surface_shape(fmt, width, height)
        assert len(data) == width_bytes * rows, "%s: %d bytes, %dx%d %s needs %d" % (
            name, len(data), width, height, fmt, width_bytes * rows)
        self.name = name
        self.fmt = fmt
        self.width = width
        self.height = height
        self.data = data
        self.channels = channels if channels is not None else CHANNELS.get(fmt, RGBA)

    def surface(self):
        width_bytes, rows = surface_shape(self.fmt, self.width, self.height)
        bh = block_height_log2(rows)
        padded_width = align(width_bytes, 16)
        linear = self.data
        if padded_width != width_bytes:
            linear = b"".join(self.data[y * width_bytes:(y + 1) * width_bytes].ljust(padded_width, b"\0")
                              for y in range(rows))
        return swizzle(linear, padded_width, rows, bh), bh


def bit(name, index):
    byte = index >> 3
    if byte >= len(name):
        return 0
    return (name[len(name) - 1 - byte] >> (index & 7)) & 1


def first_difference(a, b):
    for index in range(max(len(a), len(b)) * 8):
        if bit(a, index) != bit(b, index):
            return index
    raise ValueError("duplicate texture name %r" % a)


def dictionary(names):
    """ResDic radix tree: [(reference bit, left, right)], node 0 the root."""
    keys = [b""] + [name.encode() for name in names]
    nodes = [[-1, 0, 0]]

    def child(node, key):
        reference, left, right = nodes[node]
        return right if node and bit(key, reference) else left

    for index in range(1, len(keys)):
        key = keys[index]
        previous, current = 0, nodes[0][1]
        while nodes[previous][0] < nodes[current][0]:
            previous, current = current, child(current, key)
        reference = first_difference(key, keys[current])
        previous, current = 0, nodes[0][1]
        while nodes[previous][0] < nodes[current][0] < reference:
            previous, current = current, child(current, key)
        node = [reference, current, index] if bit(key, reference) else [reference, index, current]
        nodes.append(node)
        if previous == 0:
            nodes[0][1] = index
        elif bit(key, nodes[previous][0]):
            nodes[previous][2] = index
        else:
            nodes[previous][1] = index
    return nodes


def relocation_entries(positions):
    positions = sorted(positions)
    entries = []
    index = 0
    while index < len(positions):
        start = positions[index]
        run = 1
        while (index + run < len(positions) and positions[index + run] == start + 8 * run and run < 255):
            run += 1
        structs, padding = 1, 0
        following = index + run
        if following < len(positions):
            stride = positions[following] - start
            gap = stride // 8 - run
            if 0 <= gap <= 255:
                while structs < 0xFFFF and index + (structs + 1) * run <= len(positions) and all(
                        positions[index + structs * run + offset] == start + structs * stride + 8 * offset
                        for offset in range(run)):
                    structs += 1
                if structs > 1:
                    padding = gap
        entries.append((start, structs, run, padding))
        index += structs * run
    return entries


def string_block(strings):
    out = bytearray()
    where = {}
    for text in strings:
        where[text] = len(out)
        raw = text.encode()
        out += struct.pack("<H", len(raw)) + raw + b"\0"
        if len(out) % 2:
            out += b"\0"
    return bytes(out), where


def write(textures, file_name="__Combined", string_order=None):
    textures = sorted(textures, key=lambda texture: texture.name)
    count = len(textures)
    surfaces = [texture.surface() for texture in textures]
    names = [texture.name for texture in textures]
    infos = POOL + POOL_SIZE
    strings_at = infos + 8 * count
    blob, where = string_block([""] + [file_name] + (string_order or names))
    dic = align(strings_at + 0x14 + len(blob), 8)
    first_brti = dic + 8 + 16 * (count + 1)
    brtis = [first_brti + index * (BRTI_SIZE + BRTI_BLANK + 8) for index in range(count)]
    brti_end = first_brti + count * (BRTI_SIZE + BRTI_BLANK + 8)
    brtd = align(brti_end + 0x10, FILE_ALIGN) - 0x10
    data_at = []
    cursor = brtd + 0x10
    for surface, _ in surfaces:
        cursor = align(cursor, SURFACE_ALIGN)
        data_at.append(cursor)
        cursor += len(surface)
    rlt = align(cursor, FILE_ALIGN)

    out = bytearray(rlt)
    string = lambda text: strings_at + 0x14 + where[text]
    struct.pack_into("<4sIHHHBB", out, 0, b"BNTX", 0, 0, 4, 0xFEFF, 0x0C, 0x40)
    struct.pack_into("<IHHI", out, 0x10, string(file_name) + 2, 0, strings_at, rlt)
    struct.pack_into("<4sIQQQQ", out, 0x20, b"NX  ", count, infos, brtd, dic, POOL)
    for index, at in enumerate(brtis):
        struct.pack_into("<Q", out, infos + 8 * index, at)
    struct.pack_into("<4sIQI", out, strings_at, b"_STR", first_brti - strings_at, first_brti - strings_at,
                     1 + len(string_order or names))
    out[strings_at + 0x14:strings_at + 0x14 + len(blob)] = blob
    struct.pack_into("<4sI", out, dic, b"_DIC", count)
    for index, (reference, left, right) in enumerate(dictionary(names)):
        key = "" if index == 0 else names[index - 1]
        struct.pack_into("<iHHQ", out, dic + 8 + 16 * index, reference, left, right, string(key))
    for index, (texture, (surface, bh), at) in enumerate(zip(textures, surfaces, brtis)):
        size = (brtis[index + 1] if index + 1 < count else brtd) - at
        code = FORMATS[texture.fmt][0]
        struct.pack_into("<4sIQBBHHHIIIIIIII6IIIII", out, at, b"BRTI", size, size, 1, 2, 0, 0, 1, 1, code,
                         GPU_ACCESS_TEXTURE, texture.width, texture.height, 1, 1, bh, LAYOUT, 0, 0, 0, 0, 0,
                         len(surface), SURFACE_ALIGN, texture.channels, 1)
        mips = at + BRTI_SIZE + BRTI_BLANK
        struct.pack_into("<6Q", out, at + 0x60, string(texture.name), 0x20, mips, 0, at + BRTI_SIZE,
                         at + BRTI_SIZE + 0x100)
        struct.pack_into("<Q", out, mips, data_at[index])
        out[data_at[index]:data_at[index] + len(surface)] = surface
    struct.pack_into("<4sIQ", out, brtd, b"BRTD", 0, rlt - brtd)

    near = [0x28, 0x38, 0x40] + [infos + 8 * index for index in range(count)]
    near += [dic + 8 + 16 * index + 8 for index in range(count + 1)]
    far = [0x30]
    for at in brtis:
        near += [at + 0x60, at + 0x68, at + 0x70, at + 0x80, at + 0x88]
        far.append(at + BRTI_SIZE + BRTI_BLANK)
    sections = [(0, brti_end, relocation_entries(near)), (brtd, rlt - brtd, relocation_entries(far))]
    table = struct.pack("<4sIII", b"_RLT", rlt, len(sections), 0)
    first = 0
    for position, size, entries in sections:
        table += struct.pack("<QIIII", 0, position, size, first, len(entries))
        first += len(entries)
    for _, _, entries in sections:
        for entry in entries:
            table += struct.pack("<IHBB", *entry)
    out += table
    struct.pack_into("<I", out, 0x1C, len(out))
    return bytes(out)


def relocated_positions(data):
    """{position: section} of every pointer the relocation table names."""
    rlt = struct.unpack_from("<I", data, 0x18)[0]
    sections = struct.unpack_from("<I", data, rlt + 8)[0]
    out = {}
    entries_at = rlt + 0x10 + 24 * sections
    for section in range(sections):
        _, _, _, first, count = struct.unpack_from("<QIIII", data, rlt + 0x10 + 24 * section)
        for entry in range(first, first + count):
            position, structs, offsets, padding = struct.unpack_from("<IHBB", data, entries_at + 8 * entry)
            for index in range(structs):
                for offset in range(offsets):
                    out[position + 8 * (index * (offsets + padding) + offset)] = section
    return out


def read(data):
    assert data[:4] == b"BNTX", "not a BNTX"
    count, infos = struct.unpack_from("<IQ", data, 0x24)
    textures = []
    for index in range(count):
        at = struct.unpack_from("<Q", data, infos + 8 * index)[0]
        code = struct.unpack_from("<I", data, at + 0x1C)[0]
        width, height = struct.unpack_from("<II", data, at + 0x24)
        bh = struct.unpack_from("<I", data, at + 0x34)[0]
        size, _, channels = struct.unpack_from("<III", data, at + 0x50)
        name_at, _, mips = struct.unpack_from("<QQQ", data, at + 0x60)
        name_length = struct.unpack_from("<H", data, name_at)[0]
        name = data[name_at + 2:name_at + 2 + name_length].decode()
        start = struct.unpack_from("<Q", data, mips)[0]
        fmt = FORMAT_NAMES.get(code)
        if fmt is None:
            textures.append((name, code, width, height, None))
            continue
        width_bytes, rows = surface_shape(fmt, width, height)
        padded_width = align(width_bytes, 16)
        linear = deswizzle(data[start:start + size], padded_width, rows, bh)
        if padded_width != width_bytes:
            linear = b"".join(linear[y * padded_width:y * padded_width + width_bytes] for y in range(rows))
        textures.append(Texture(name, fmt, width, height, linear, channels))
    return textures


def main():
    data = open(sys.argv[1], "rb").read()
    textures = read(data)
    if len(sys.argv) == 2:
        for texture in textures:
            if isinstance(texture, tuple):
                print("%s format %#06x %dx%d (not readable)" % (texture[0], texture[1], texture[2], texture[3]))
            else:
                print("%s %s %dx%d" % (texture.name, texture.fmt, texture.width, texture.height))
        return
    from PIL import Image
    texture = next(texture for texture in textures if not isinstance(texture, tuple) and texture.name == sys.argv[2])
    assert texture.fmt.startswith("rgba8"), "only rgba8 exports"
    Image.frombytes("RGBA", (texture.width, texture.height), texture.data).save(sys.argv[3])


if __name__ == "__main__":
    main()
