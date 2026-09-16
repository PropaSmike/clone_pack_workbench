#!/usr/bin/env python3
"""The Help window: the README beside the tools, laid out for reading."""

from __future__ import annotations

import re
from pathlib import Path

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

README_NAMES = ("README.md", "clone_pack_tools_README.md")
CODE_BACKGROUND = "#eef0f3"
RULE = "#c8ccd2"
INLINE = re.compile(r"(`[^`]+`|\*\*[^*]+?\*\*)")
BULLET = re.compile(r"^[*-] ")
HEADING = re.compile(r"^(#{1,3}) +(.*?)\s*#*$")
TABLE_RULE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")


def body_family(size: int = 10) -> str:
    """The window's own font family, or the first one whose bold face is a real
    bold: on some installs the default family resolves to one face for both."""
    default = tkfont.nametofont("TkDefaultFont").actual()["family"]
    for family in (default, "Segoe UI Variable Text", "Calibri", "Tahoma", "Arial"):
        normal = tkfont.Font(family=family, size=size, weight="normal")
        bold = tkfont.Font(family=family, size=size, weight="bold")
        if normal.measure("Clone Pack Workbench") != bold.measure("Clone Pack Workbench"):
            return family
    return default


def find_readme(root: Path) -> Path | None:
    for name in README_NAMES:
        path = root / name
        if path.is_file():
            return path
    return None


def pieces(text: str) -> list[tuple[str, str | None]]:
    """Inline markdown as (text, style) runs; style is "code", "bold" or None."""
    out = []
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("`"):
            out.append((part[1:-1], "code"))
        elif part.startswith("**"):
            out.append((part[2:-2], "bold"))
        else:
            out.append((part, None))
    return [(text.replace("\\|", "|"), style) for text, style in out]


def cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", body)]


def parse(text: str) -> list[tuple]:
    """Markdown as blocks: ("heading", level, text), ("paragraph", text),
    ("bullet", text), ("code", text) and ("table", rows)."""
    blocks: list[tuple] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("```"):
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            blocks.append(("code", "\n".join(body)))
            i += 1
            continue
        if line.startswith("    "):
            body = []
            while i < len(lines) and (lines[i].startswith("    ") or not lines[i].strip()):
                body.append(lines[i][4:])
                i += 1
            while body and not body[-1].strip():
                body.pop()
            blocks.append(("code", "\n".join(body)))
            continue
        heading = HEADING.match(stripped)
        if heading:
            blocks.append(("heading", len(heading.group(1)), heading.group(2)))
            i += 1
            continue
        if stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not TABLE_RULE.match(lines[i].strip()):
                    rows.append(cells(lines[i]))
                i += 1
            blocks.append(("table", rows))
            continue
        if BULLET.match(stripped):
            body = [stripped[2:].strip()]
            i += 1
            while i < len(lines) and lines[i].strip() and lines[i].startswith(" ") \
                    and not BULLET.match(lines[i].strip()):
                body.append(lines[i].strip())
                i += 1
            blocks.append(("bullet", " ".join(body)))
            continue
        body = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith("    ") \
                and not BULLET.match(lines[i].strip()) \
                and not lines[i].strip().startswith(("#", "|", "```")):
            body.append(lines[i].strip())
            i += 1
        blocks.append(("paragraph", " ".join(body)))
    return blocks


class GuideWindow(tk.Toplevel):
    """The README in its own window, with a contents list that jumps to each section."""

    def __init__(self, master: tk.Misc, root: Path):
        super().__init__(master)
        self.title("Clone Pack Workbench: help")
        self.geometry("980x720+%d+%d" % (master.winfo_rootx() + 60, master.winfo_rooty() + 60))
        self.minsize(640, 420)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.fonts = self._fonts()
        self.headings: list[str] = []
        self.rules: list[tk.Frame] = []

        side = ttk.Frame(self, padding=(8, 8, 0, 8))
        side.grid(row=0, column=0, sticky="ns")
        side.rowconfigure(1, weight=1)
        ttk.Label(side, text="Contents").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.contents = tk.Listbox(side, width=34, activestyle="none", exportselection=False,
                                   borderwidth=0, highlightthickness=0,
                                   font=self.fonts["body"])
        self.contents.grid(row=1, column=0, sticky="ns")
        self.contents.bind("<<ListboxSelect>>", self.jump)

        frame = ttk.Frame(self, padding=8)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.text = tk.Text(frame, wrap="word", padx=18, pady=12, borderwidth=0,
                            highlightthickness=0, font=self.fonts["body"], cursor="arrow")
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.across = ttk.Scrollbar(frame, orient="horizontal", command=self.text.xview)
        self.across.grid(row=1, column=0, sticky="ew")
        self.text.configure(yscrollcommand=scroll.set, xscrollcommand=self._xscroll)
        self.text.bind("<Configure>", self._fit_rules)
        self._tags()

        path = find_readme(root)
        if path is None:
            self.render([("paragraph", "README.md is not beside the tools, so there is "
                                       "nothing to show. It is in the release folder.")])
        else:
            self.render(parse(path.read_text(encoding="utf-8")))
        self.text.configure(state="disabled")
        self.bind("<Escape>", lambda _: self.destroy())
        self.text.focus_set()

    def _xscroll(self, first: str, last: str) -> None:
        """The horizontal scrollbar shows only while a code line is cut off."""
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.across.grid_remove()
        else:
            self.across.grid()
        self.across.set(first, last)

    def _fonts(self) -> dict:
        family = body_family()
        body = tkfont.Font(family=family, size=10, weight="normal")
        bold = tkfont.Font(family=family, size=10, weight="bold")
        title = tkfont.Font(family=family, size=17, weight="bold")
        section = tkfont.Font(family=family, size=13, weight="bold")
        fixed = tkfont.nametofont("TkFixedFont").copy()
        fixed.configure(size=10)
        if "Consolas" in tkfont.families():
            fixed.configure(family="Consolas")
        hairline = tkfont.Font(family=family, size=1)
        return {"body": body, "bold": bold, "title": title, "section": section,
                "fixed": fixed, "hairline": hairline}

    def _tags(self) -> None:
        text, fonts = self.text, self.fonts
        text.tag_configure("title", font=fonts["title"], spacing3=10)
        text.tag_configure("section", font=fonts["section"], spacing1=18, spacing3=6)
        text.tag_configure("sub", font=fonts["bold"], spacing1=10, spacing3=4)
        text.tag_configure("paragraph", spacing3=9)
        indent = fonts["body"].measure("•  ")
        text.tag_configure("bullet", lmargin1=10, lmargin2=10 + indent, spacing3=5)
        text.tag_configure("code", font=fonts["fixed"], background=CODE_BACKGROUND,
                           lmargin1=14, lmargin2=14, rmargin=14, wrap="none")
        text.tag_configure("codetop", spacing1=6)
        text.tag_configure("codeend", spacing3=6)
        try:
            text.tag_configure("code", lmargincolor=CODE_BACKGROUND,
                               rmargincolor=CODE_BACKGROUND)
        except tk.TclError:
            pass
        text.tag_configure("inline", font=fonts["fixed"], background=CODE_BACKGROUND)
        text.tag_configure("mono", font=fonts["fixed"])
        text.tag_configure("bold", font=fonts["bold"])
        text.tag_configure("header", font=fonts["bold"])
        text.tag_configure("hairline", font=fonts["hairline"], spacing1=0, spacing3=0)
        text.tag_configure("gap", font=fonts["hairline"], spacing3=8)
        text.tag_configure("listend", spacing3=12)

    def render(self, blocks: list[tuple]) -> None:
        self.contents.delete(0, "end")
        self.headings = []
        tables = 0
        for number, block in enumerate(blocks):
            kind = block[0]
            if kind == "heading":
                self._heading(block[1], block[2])
            elif kind == "paragraph":
                self._inline(block[1], "paragraph")
                self.text.insert("end", "\n", "paragraph")
            elif kind == "bullet":
                last = number + 1 == len(blocks) or blocks[number + 1][0] != "bullet"
                self.text.insert("end", "•  ", "bullet")
                self._inline(block[1], "bullet")
                self.text.insert("end", "\n", ("bullet", "listend") if last else "bullet")
            elif kind == "code":
                lines = block[1].splitlines() or [""]
                width = max(len(line) for line in lines) + 2
                for index, line in enumerate(lines):
                    tags = ["code"]
                    if index == 0:
                        tags.append("codetop")
                    if index == len(lines) - 1:
                        tags.append("codeend")
                    self.text.insert("end", line.ljust(width) + "\n", tuple(tags))
                self.text.insert("end", "\n", "gap")
            elif kind == "table":
                tables += 1
                self._table(block[1], "table%d" % tables)
        self.contents.configure(height=min(len(self.headings), 40))

    def _heading(self, level: int, title: str) -> None:
        tag = {1: "title", 2: "section"}.get(level, "sub")
        mark = "heading%d" % len(self.headings)
        self.text.mark_set(mark, "end-1c")
        self.text.mark_gravity(mark, "left")
        self._inline(title, tag)
        self.text.insert("end", "\n", tag)
        self.headings.append(mark)
        self.contents.insert("end", ("   " if level > 1 else "") + plain(title))

    def _inline(self, text: str, base: str) -> None:
        for run, style in pieces(text):
            tags = (base,) if style is None else (base, "inline" if style == "code" else style)
            self.text.insert("end", run, tags)

    def _table(self, rows: list[list[str]], tag: str) -> None:
        if not rows:
            return
        columns = max(len(row) for row in rows)
        widths = [0] * columns
        for row in rows:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], self._width(cell))
        stops, position = [], 12
        for width in widths[:-1]:
            position += width + 28
            stops.append(position)
        last = stops[-1] if stops else 12
        self.text.tag_configure(tag, lmargin1=12, lmargin2=last, tabs=tuple(stops),
                                spacing3=3)
        for number, row in enumerate(rows):
            style = (tag, "header") if number == 0 else (tag,)
            for index, cell in enumerate(row):
                if index:
                    self.text.insert("end", "\t", style)
                for run, inline in pieces(cell):
                    tags = style if inline is None else style + (
                        "mono" if inline == "code" else inline,)
                    self.text.insert("end", run, tags)
            self.text.insert("end", "\n", style)
            if number == 0:
                self._rule(tag)
        self.text.insert("end", "\n", "gap")

    def _rule(self, tag: str) -> None:
        line = tk.Frame(self.text, height=1, background=RULE)
        self.text.window_create("end", window=line, pady=2)
        self.text.tag_add(tag, "end-2c")
        self.text.insert("end", "\n", (tag, "hairline"))
        self.rules.append(line)

    def _fit_rules(self, event) -> None:
        width = max(event.width - 2 * 18 - 12 - 8, 40)
        for line in self.rules:
            line.configure(width=width)

    def _width(self, cell: str) -> int:
        total = 0
        for run, style in pieces(cell):
            font = self.fonts["fixed"] if style == "code" else \
                self.fonts["bold"] if style == "bold" else self.fonts["body"]
            total += font.measure(run)
        return total

    def jump(self, _event=None) -> None:
        chosen = self.contents.curselection()
        if not chosen:
            return
        self.text.yview(self.headings[chosen[0]])


def plain(text: str) -> str:
    return "".join(run for run, _ in pieces(text))
