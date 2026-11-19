"""Write SSBU layouts (BFLYT 9.0) from a pane tree, packed as layout.arc.

A layout is null panes, pictures (a flat colour or a texture) and text boxes
that the menu's Lua fills at run time (`get_pane(name):set_text_string`).
Text uses a font the game already loads, by name. A layout carries its own
textures (`timg/__Combined.bntx`) and animations (`anim/<layout>_<tag>.bflan`,
listed in `info/layout.info`).
"""
import struct

import bntx
import sarc

VERSION = 0x09000000
FONT = "FOT-RodinNTLGPro-B64"
CENTER, LEFT, RIGHT = 0, 1, 2
MIDDLE, TOP, BOTTOM = 0, 1, 2
WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)
CLEAR = (0, 0, 0, 0)
COLOR_OFFSETS = bytes([0x00, 0x02, 0x04, 0x08])
TEXT_PLAIN, TEXT_SHADOW = 4, 5
CLAMP, REPEAT, MIRROR = 0, 1, 2
LINEAR_FILTER = 4
FULL_TEXTURE = ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0))
ADDITIVE = (1, 4, 1, 0)
MATERIAL_TEXTURE = 0x15
MATERIAL_BLEND = 0x400


def rgba(color):
    return bytes(color)


def padded(raw, align=4):
    return raw + b"\0" * (-len(raw) % align)


def fixed(text, size):
    raw = text.encode("ascii")
    assert len(raw) <= size, "name too long: %s" % text
    return raw + b"\0" * (size - len(raw))


def section(magic, body):
    body = padded(body)
    return magic + struct.pack("<I", 8 + len(body)) + body


def origin(h=CENTER, v=MIDDLE, parent_h=CENTER, parent_v=MIDDLE):
    return h | v << 2 | parent_h << 4 | parent_v << 6


class Pane:
    kind = b"pan1"

    def __init__(self, name, x=0.0, y=0.0, width=30.0, height=40.0, visible=True, alpha=255,
                 scale=(1.0, 1.0), rotate=0.0, anchor=(CENTER, MIDDLE), parent_anchor=(CENTER, MIDDLE),
                 children=()):
        self.name = name
        self.translate = (float(x), float(y), 0.0)
        self.rotate = (0.0, 0.0, float(rotate))
        self.scale = tuple(float(value) for value in scale)
        self.size = (float(width), float(height))
        self.visible = visible
        self.alpha = alpha
        self.anchor = anchor
        self.parent_anchor = parent_anchor
        self.children = list(children)

    def add(self, *children):
        self.children.extend(children)
        return self

    def header(self):
        flags = 1 if self.visible else 0
        base = origin(self.anchor[0], self.anchor[1], self.parent_anchor[0], self.parent_anchor[1])
        return (struct.pack("<BBBB", flags, base, self.alpha, 0) + fixed(self.name, 24) + b"\0" * 8
                + struct.pack("<3f3f2f2f", *self.translate, *self.rotate, *self.scale, *self.size))

    def body(self, layout):
        return b""

    def material(self, layout):
        return None


class Picture(Pane):
    kind = b"pic1"

    def __init__(self, name, width, height, color=WHITE, texture=None, corners=None, texcoords=None,
                 wrap=(CLAMP, CLAMP), blend=None, black=CLEAR, **rest):
        super().__init__(name, width=width, height=height, **rest)
        self.color = color
        self.texture = texture
        self.corners = corners or (WHITE, WHITE, WHITE, WHITE)
        self.texcoords = texcoords or FULL_TEXTURE
        self.wrap = wrap
        self.blend = blend
        self.black = black

    def material(self, layout):
        return picture_material(self.name, self.color, layout.texture_index(self.texture), self.wrap, self.blend,
                                self.black)

    def body(self, layout):
        index = layout.material_index(self)
        coords = struct.pack("<8f", *(value for corner in self.texcoords for value in corner))
        return (b"".join(rgba(color) for color in self.corners)
                + struct.pack("<HBB", index, 1, 0) + coords)


class Text(Pane):
    kind = b"txt1"

    def __init__(self, name, width, height, text="", font_size=48.0, color=WHITE, bottom_color=None,
                 position=(CENTER, MIDDLE), shadow=False, shadow_color=BLACK, font=FONT, capacity=0, **rest):
        super().__init__(name, width=width, height=height, **rest)
        self.text = text
        self.font_size = float(font_size)
        self.color = color
        self.bottom_color = bottom_color or color
        self.position = position
        self.shadow = shadow
        self.shadow_color = shadow_color
        self.capacity = capacity
        self.font = font

    def material(self, layout):
        return text_material(self.name, CLEAR, WHITE)

    def body(self, layout):
        index = layout.material_index(self)
        font = layout.font_index(self.font)
        encoded = self.text.encode("utf-16-le") + b"\0\0"
        text_offset = 8 + 76 + 84
        position = self.position[0] | self.position[1] << 2
        flags = TEXT_SHADOW if self.shadow else TEXT_PLAIN
        fields = struct.pack(
            "<HHHHBBBBfI4s4s2f2fI2f2f4s4sfII",
            max(len(encoded), (self.capacity + 1) * 2), len(encoded), index, font, position, 0, flags, 0, 0.0,
            text_offset,
            rgba(self.color), rgba(self.bottom_color), self.font_size, self.font_size, 0.0, 0.0,
            0, 1.0, -1.0, 1.0, 1.0, rgba(self.shadow_color), rgba(self.shadow_color), 0.0, 0, 0)
        return fields + padded(encoded)


def picture_material(name, color, texture, wrap=(CLAMP, CLAMP), blend=None, black=CLEAR):
    flags = (0 if texture is None else MATERIAL_TEXTURE) | (MATERIAL_BLEND if blend else 0)
    out = fixed(name, 28) + struct.pack("<I", flags) + COLOR_OFFSETS + rgba(black) + rgba(color)
    if texture is not None:
        out += struct.pack("<HBB", texture, wrap[0] | LINEAR_FILTER, wrap[1] | LINEAR_FILTER)
        out += struct.pack("<5f", 0, 0, 0, 1, 1) + bytes(16)
    if blend:
        out += bytes(blend)
    return out


def text_material(name, black, white):
    return fixed(name, 28) + struct.pack("<I", 0) + COLOR_OFFSETS + rgba(black) + rgba(white)


class Layout:
    def __init__(self, name, width=1920.0, height=1080.0):
        self.name = name
        self.width = float(width)
        self.height = float(height)
        self.root = Pane("RootPane", width=width, height=height)
        self.textures = []
        self.fonts = []
        self.materials = []
        self.material_of = {}
        self.groups = []
        self.images = {}
        self.animations = []

    def texture_index(self, texture):
        if texture is None:
            return None
        if texture not in self.textures:
            self.textures.append(texture)
        return self.textures.index(texture)

    def font_index(self, font):
        if font not in self.fonts:
            self.fonts.append(font)
        return self.fonts.index(font)

    def material_index(self, pane):
        return self.material_of[id(pane)]

    def group(self, name, panes):
        self.groups.append((name, list(panes)))

    def image(self, texture):
        self.images[texture.name] = texture
        self.texture_index(texture.name)
        return texture.name

    def animation(self, animation):
        animation.order = len(self.animations)
        self.animations.append(animation)
        return animation

    def walk(self, pane=None):
        pane = pane or self.root
        yield pane
        for child in pane.children:
            yield from self.walk(child)

    def collect(self):
        self.materials = []
        self.material_of = {}
        for pane in self.walk():
            if isinstance(pane, Text):
                self.font_index(pane.font)
            material = pane.material(self)
            if material is not None:
                self.material_of[id(pane)] = len(self.materials)
                self.materials.append(material)

    def pane_sections(self, pane):
        out = [section(pane.kind, pane.header() + pane.body(self))]
        if pane.children:
            out.append(section(b"pas1", b""))
            for child in pane.children:
                out.extend(self.pane_sections(child))
            out.append(section(b"pae1", b""))
        return out

    def bflyt(self):
        self.collect()
        sections = [section(b"lyt1", struct.pack("<B3x4f", 1, self.width, self.height, 0, 0) + padded(self.name.encode() + b"\0"))]
        sections.append(section(b"txl1", name_list(self.textures)))
        sections.append(section(b"fnl1", name_list(self.fonts)))
        sections.append(section(b"mat1", offset_list(self.materials)))
        sections.extend(self.pane_sections(self.root))
        sections.append(section(b"grp1", fixed("RootGroup", 34) + struct.pack("<H", 0)))
        if self.groups:
            sections.append(section(b"grs1", b""))
            for name, panes in self.groups:
                sections.append(section(b"grp1", fixed(name, 34) + struct.pack("<H", len(panes))
                                        + b"".join(fixed(pane, 24) for pane in panes)))
            sections.append(section(b"gre1", b""))
        body = b"".join(sections)
        header = struct.pack("<4sHHIIHH", b"FLYT", 0xFEFF, 0x14, VERSION, 0x14 + len(body), len(sections), 0)
        return header + body

    def info(self):
        names = ["%s.bflyt" % self.name] + [animation.tag for animation in self.animations] + ["", ""]
        return b"".join(name.encode() + b"\0" for name in names)

    def archive(self, textures=None):
        files = {"blyt/%s.bflyt" % self.name: self.bflyt(), "info/layout.info": self.info()}
        if textures is not None:
            files["timg/__Combined.bntx"] = textures
        elif self.images:
            files["timg/__Combined.bntx"] = bntx.write(list(self.images.values()))
        for animation in self.animations:
            files["anim/%s_%s.bflan" % (self.name, animation.tag)] = animation.bflan()
        return sarc.write(files)


def name_list(names):
    count = len(names)
    table = b""
    blob = b""
    for name in names:
        table += struct.pack("<I", 4 * count + len(blob))
        blob += name.encode() + b"\0"
    return struct.pack("<HH", count, 0) + table + blob


def offset_list(entries):
    count = len(entries)
    start = 8 + 4 + 4 * count
    table = b""
    blob = b""
    for entry in entries:
        table += struct.pack("<I", start + len(blob))
        blob += entry
    return struct.pack("<HH", count, 0) + table + blob
