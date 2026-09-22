#!/usr/bin/env python3
"""The Clone Pack Workbench window: one pack folder, one panel per pack kind."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import backups, emit, guide, optimize, packs, prc
from .catalog import (Catalog, OWNER_SURFACE, VL_SURFACE, is_float_field,
                      is_label_field, is_name_field)

TITLE = "Clone Pack Workbench"
KINDS = (packs.FIGHTER, packs.ITEM, packs.STAGE)
PARAM_TABLES = ("fighter_param", "param_motion", "common", "param_thrown", "vl.prc")
ITEM_PRC_SURFACE = "param.prc"
ITEM_PARAM_TABLES = ("item_common", "item_owner_param", ITEM_PRC_SURFACE)
PREFILL_TYPES = ("f32", "float", "i32", "u32", "int", "bool", "i8", "u8", "i16", "u16")
CHANGED = "#1a6e2e"
SURFACES = {packs.FIGHTER: PARAM_TABLES, packs.ITEM: ITEM_PARAM_TABLES, packs.STAGE: ()}
ANY_FILE = "any file"
NO_STAGE_PARAMS = (
    "The engine changes no stage value at runtime, so there is nothing to set "
    "here. A stage is tuned by the files it ships: camera, wind and colour in "
    "the .stprm (a prc file), post-processing in render/render_param.prc, blast "
    "zones and collision in the .lvd. Everything else is in stage.toml "
    "(Identity tab)."
)
SPAWN_CONTAINERS = ("box", "barrel", "capsule", "carrierbox", "kusudama")
LEVELS = ("ERROR", "WARN", "INFO")


def tools_root() -> Path:
    return Path(__file__).resolve().parent.parent


def import_tool(name: str):
    """One of the command line tools, imported from beside this package."""
    root = str(tools_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        return __import__(name)
    except ImportError:
        return None


NAMED_KEYS = ("resource_name", "place", "ui_chara", "fighter_kind_name", "display_name",
              "agent_name", "ui_id", "id_name")


class Workbench(ttk.Frame):
    """The whole window. Panels read and write self.state and call self.log."""

    def __init__(self, master: tk.Misc, folder: str | None = None):
        super().__init__(master, padding=8)
        self.master.title(TITLE)
        self.catalog = Catalog()
        self.folder: Path | None = None
        self.sections: dict = {kind: [{}] for kind in packs.KINDS}
        self.index: dict = {kind: 0 for kind in packs.KINDS}
        self.present: list[str] = []
        self.kind = tk.StringVar(value=packs.FIGHTER)
        self.path_var = tk.StringVar(value="")
        self.status = tk.StringVar(value="open a pack folder, or make a new one")
        self.guide: guide.GuideWindow | None = None

        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_top()
        self.split = ttk.PanedWindow(self, orient="vertical")
        self.split.grid(row=1, column=0, sticky="nsew")
        self._build_tabs()
        self._build_log()
        self.master.bind("<F1>", lambda _: self.show_guide())
        for note in self.catalog.notes:
            self.log(note)
        if folder:
            self.open_folder(Path(folder))

    def _build_top(self) -> None:
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text="Pack folder").grid(row=0, column=0, padx=(0, 6))
        entry = ttk.Entry(bar, textvariable=self.path_var)
        entry.grid(row=0, column=1, sticky="ew")
        entry.bind("<Return>", lambda _: self.open_folder(Path(self.path_var.get())))
        ttk.Button(bar, text="Open", command=self.pick_folder).grid(row=0, column=2, padx=4)
        ttk.Button(bar, text="New pack", command=self.new_pack).grid(row=0, column=3)
        ttk.Button(bar, text="Reload", command=self.reload).grid(row=0, column=4, padx=4)
        ttk.Button(bar, text="Backups", command=self.show_backups).grid(row=0, column=5)

        kinds = ttk.Frame(bar)
        kinds.grid(row=1, column=0, columnspan=6, sticky="w", pady=(6, 0))
        ttk.Label(kinds, text="Working on").pack(side="left", padx=(0, 6))
        self.kind_buttons = {}
        for value in KINDS:
            button = ttk.Radiobutton(kinds, text=value.capitalize(), value=value,
                                     variable=self.kind, command=self.show_kind)
            button.pack(side="left", padx=2)
            self.kind_buttons[value] = button
        ttk.Button(kinds, text="Add this part to the pack",
                   command=self.add_kind).pack(side="left", padx=(10, 0))
        status = ttk.Label(kinds, textvariable=self.status, justify="left")
        status.pack(side="left", padx=12)

        parts = ttk.Frame(bar)
        parts.grid(row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))
        ttk.Label(parts, text="Part").pack(side="left", padx=(0, 6))
        self.part_var = tk.StringVar()
        self.part_box = ttk.Combobox(parts, textvariable=self.part_var, width=30,
                                     state="readonly")
        self.part_box.pack(side="left")
        self.part_box.bind("<<ComboboxSelected>>", self.part_chosen)
        ttk.Button(parts, text="New part", command=self.new_part).pack(side="left", padx=4)
        ttk.Button(parts, text="Remove part",
                   command=self.remove_part).pack(side="left")
        about = ttk.Label(parts, text="a pack may hold several fighters, items or stages; "
                                      "each is a part with its own settings",
                          foreground="#555", justify="left")
        about.pack(side="left", padx=12)
        wrap_within(bar, [status, about])

    def _build_tabs(self) -> None:
        self.tabs = ttk.Notebook(self.split)
        self.split.add(self.tabs, weight=4)
        self.identity = IdentityPanel(self.tabs, self)
        self.files = FilesPanel(self.tabs, self)
        self.params = ParamsPanel(self.tabs, self)
        self.lint = LintPanel(self.tabs, self)
        self.optimize = OptimizePanel(self.tabs, self)
        self.rust = RustPanel(self.tabs, self)
        self.help_tab = ttk.Frame(self.tabs)
        for panel, label in ((self.identity, "Identity"), (self.files, "Files"),
                             (self.params, "Parameters"), (self.lint, "Lint"),
                             (self.optimize, "Optimize"), (self.rust, "Rust"),
                             (self.help_tab, "Help")):
            self.tabs.add(panel, text=label)
        self.last_tab = str(self.identity)
        self.tabs.bind("<<NotebookTabChanged>>", self.tab_changed)

    def tab_changed(self, _event=None) -> None:
        """The Help tab is a button: it opens the guide and leaves the tab you were on."""
        chosen = self.tabs.select()
        if chosen == str(self.help_tab):
            self.tabs.select(self.last_tab)
            self.show_guide()
        else:
            self.last_tab = chosen
            if self.identity.pending is not None:
                self.identity.sync()

    def show_guide(self) -> None:
        if self.guide is not None and self.guide.winfo_exists():
            self.guide.deiconify()
            self.guide.lift()
            self.guide.focus_set()
            return
        self.guide = guide.GuideWindow(self.master, tools_root())

    def _build_log(self) -> None:
        frame = ttk.LabelFrame(self.split, text="Output", padding=4)
        self.split.add(frame, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(frame, height=5, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set, state="disabled")
        ttk.Button(frame, text="Clear", command=self.clear_log).grid(row=1, column=0,
                                                                    sticky="e", pady=(4, 0))

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip("\n") + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def log_kept(self) -> None:
        """Say where each file written over since the last action was copied to."""
        for source, target in backups.drain():
            self.log("kept %s as %s" % (source.name, backups.describe(target)))

    def keep(self, *names: str) -> None:
        """Copy these pack files before a tool writes over them."""
        if self.folder is None:
            return
        for name in names:
            backups.keep(self.folder / name, self.folder)

    def show_backups(self) -> None:
        """Open the backups folder, the pack's own when it has one."""
        folder = backups.ROOT
        if self.folder is not None and (folder / self.folder.name).is_dir():
            folder = folder / self.folder.name
        if not folder.is_dir():
            messagebox.showinfo(TITLE, "Nothing has been backed up yet. Every file the "
                                       "window writes over is copied first to %s, dated."
                                % backups.ROOT)
            return
        try:
            os.startfile(str(folder))
        except (AttributeError, OSError):
            self.log("backups are in %s" % folder)

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def run_tool(self, module_name: str, argv: list[str], pass_argv: bool = False) -> int:
        """Run one of the command line tools in process and log what it printed."""
        module = import_tool(module_name)
        if module is None:
            self.log("%s is not beside this GUI, so that step cannot run" % module_name)
            return 1
        self.log("$ python %s.py %s" % (module_name, " ".join(argv)))
        captured = io.StringIO()
        saved = sys.argv
        sys.argv = [module_name + ".py"] + argv
        try:
            with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                code = module.main(argv) if pass_argv else module.main()
        except SystemExit as stop:
            if isinstance(stop.code, str):
                self.log("    " + stop.code)
                code = 1
            else:
                code = int(stop.code or 0)
        except Exception:
            self.log(traceback.format_exc())
            code = 1
        finally:
            sys.argv = saved
        for line in captured.getvalue().splitlines():
            self.log("    " + line)
        self.log_kept()
        return int(code or 0)

    def pick_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Pick the pack folder")
        if chosen:
            self.open_folder(Path(chosen))

    def open_folder(self, folder: Path) -> None:
        folder = Path(folder)
        if not folder.is_dir():
            messagebox.showerror(TITLE, "%s is not a folder" % folder)
            return
        self.folder = folder
        self.path_var.set(str(folder))
        self.present = packs.detect_kinds(folder)
        self.log("opened %s (ships %s)"
                 % (folder, ", ".join(self.present) if self.present else "nothing yet"))
        self.sections = self.scan(folder)
        saved = packs.read_state(folder)
        for kind in packs.KINDS:
            self.adopt_strays(kind, *self.merge_parts(kind, saved[kind]))
            manifest = packs.manifest_name(kind)
            if manifest and (folder / manifest).is_file():
                if kind == packs.FIGHTER:
                    declared = packs.read_fighter_manifests(folder / manifest)
                else:
                    declared = packs.read_manifests(folder / manifest)
                self.merge_parts(kind, declared)
                self.log("read %s%s" % (manifest, " (%d parts)" % len(declared)
                                        if len(declared) > 1 else ""))
            if not self.sections[kind]:
                self.sections[kind] = [{}]
            self.index[kind] = 0
        if self.present:
            self.kind.set(self.present[0])
        self.mark_present()
        self.show_kind()
        self.identity.load()
        self.params.load()
        self.files.refresh()
        self.rust.refresh()
        self.lint.clear()
        self.optimize.clear()

    def reload(self) -> None:
        if self.folder:
            self.open_folder(self.folder)

    def scan(self, folder: Path) -> dict:
        """Pre-fill every part from what the folder itself says."""
        catalog = self.catalog
        found = packs.scan(folder, catalog.fighter_dirs(), catalog.item_dirs(),
                           catalog.stage_places())
        self.item_candidates = found.get("item_candidates") or []
        sections = {kind: list(found.get(kind) or []) for kind in packs.KINDS}
        for fighter in sections[packs.FIGHTER]:
            if fighter.get("base_resource_name"):
                kind = catalog.kind_of_fighter(fighter["base_resource_name"])
                if kind is not None:
                    fighter["base_kind"] = kind
        for item in sections[packs.ITEM]:
            if item.get("base_item"):
                kind = catalog.kind_of_item(item["base_item"])
                if kind is not None:
                    item["base_kind"] = kind
        for note in found.get("notes") or []:
            self.log("    scan: " + note)
        self.identity.set_item_candidates(self.item_candidates)
        return sections

    def merge_parts(self, kind: str, parts: list) -> tuple[list, set]:
        """Fold these parts into the kind's list, by name; a nameless part joins
        the first part that has no name yet, so a saved file and a manifest that
        describe the same clone stay one part. Returns the parts that matched
        nothing and were appended, and the ids of the parts that were matched."""
        known = self.sections[kind]
        strays, matched = [], set()
        for part in parts:
            name = packs.identity(part, kind)
            for existing in known:
                if packs.identity(existing, kind) == name:
                    existing.update(part)
                    matched.add(id(existing))
                    break
            else:
                stray = dict(part)
                known.append(stray)
                strays.append(stray)
        return strays, matched

    def adopt_strays(self, kind: str, strays: list, matched: set) -> None:
        """A saved part whose name ships nothing joins the first part found on
        disk that has no saved state of its own: the disk names the clone, the
        file keeps the rules. A pack with one fighter and a stale name in
        clone_pack_gui.json is one fighter, not two."""
        parts = self.sections[kind]
        for stray in strays:
            for existing in parts:
                if existing is stray or existing in strays or id(existing) in matched:
                    continue
                if not packs.identity(existing, kind):
                    continue
                for key, value in stray.items():
                    if key not in NAMED_KEYS:
                        existing.setdefault(key, value)
                matched.add(id(existing))
                parts.remove(stray)
                self.log("    clone_pack_gui.json describes %s '%s', which ships "
                         "nothing here; its settings now belong to '%s'"
                         % (kind, packs.identity(stray, kind), packs.identity(existing, kind)))
                break

    def part(self, kind: str) -> dict:
        """The part of that kind being worked on; a kind always has at least one."""
        parts = self.sections[kind]
        if not parts:
            parts.append({})
        self.index[kind] = min(self.index.get(kind, 0), len(parts) - 1)
        return parts[self.index[kind]]

    @property
    def state(self) -> dict:
        """The part being worked on, of the kind being worked on."""
        return self.part(self.kind.get())

    def part_label(self, kind: str, part: dict) -> str:
        return packs.identity(part, kind) or "(new %s)" % kind

    def refresh_parts(self) -> None:
        kind = self.kind.get()
        self.part(kind)
        labels = [self.part_label(kind, part) for part in self.sections[kind]]
        self.part_box.configure(values=labels)
        self.part_var.set(labels[self.index[kind]])

    def part_chosen(self, _event=None) -> None:
        kind = self.kind.get()
        chosen = self.part_box.current()
        if chosen < 0 or chosen == self.index[kind]:
            return
        self.identity.collect()
        self.index[kind] = chosen
        self.show_kind()

    def new_part(self) -> None:
        kind = self.kind.get()
        self.identity.collect()
        self.sections[kind].append({})
        self.index[kind] = len(self.sections[kind]) - 1
        self.show_kind()
        self.log("new %s part; fill it in, then write its manifest or config" % kind)

    def remove_part(self) -> None:
        kind = self.kind.get()
        part = self.part(kind)
        name = self.part_label(kind, part)
        if part and not messagebox.askyesno(
                TITLE, "Forget %s in this window? Its files stay on disk; the next "
                       "manifest write leaves it out." % name):
            return
        self.sections[kind].pop(self.index[kind])
        if not self.sections[kind]:
            self.sections[kind].append({})
        self.index[kind] = max(0, self.index[kind] - 1)
        self.show_kind()
        self.log("forgot %s" % name)

    def mark_present(self) -> None:
        for kind, button in self.kind_buttons.items():
            shipped = kind in self.present
            button.configure(text=kind.capitalize() + (" *" if shipped else ""))
        if not self.present:
            self.status.set("ships nothing yet: fill a part in and add it")
        else:
            self.status.set("ships %s (* marks what is on disk)"
                            % ", ".join(self.present))

    def show_kind(self) -> None:
        self.refresh_parts()
        self.identity.show(self.kind.get())
        self.identity.load()
        self.params.show(self.kind.get())
        self.params.load()
        self.rust.refresh()

    def add_kind(self) -> None:
        """Give the open pack the trees and manifest of the part being worked on."""
        if not self.require_folder():
            return
        kind = self.kind.get()
        self.identity.collect()
        made = packs.scaffold(self.folder, kind, self.state)
        for entry in made:
            self.log("added " + entry)
        self.log_kept()
        self.present = packs.detect_kinds(self.folder)
        self.mark_present()
        self.files.refresh()

    def vanilla_names(self, kind: str) -> list[str]:
        return {packs.FIGHTER: self.catalog.fighter_dirs, packs.ITEM: self.catalog.item_dirs,
                packs.STAGE: self.catalog.stage_places}[kind]()

    def rename_part(self, kind: str, old: str, new: str, confirm=None) -> bool:
        """Rename what the pack ships for one part, then read the pack again.
        confirm(plan) may say no once the plan is known."""
        if not self.require_folder():
            return False
        refusal = packs.rename_refusal(self.folder, kind, old, new, self.vanilla_names(kind))
        if refusal:
            self.log("not renamed: " + refusal)
            return False
        plan = packs.rename_plan(self.folder, old, new)
        if confirm is not None and not confirm(plan):
            self.log("rename of %s to %s cancelled" % (old, new))
            return False
        self.log("renaming %s to %s: %d path(s), %d text file(s)"
                 % (old, new, len(plan["moves"]), len(plan["edits"])))
        for line in packs.apply_rename(self.folder, plan):
            self.log("    " + line)
        self.log_kept()
        converted = kind == packs.FIGHTER and old in self.vanilla_names(kind)
        self.open_folder(self.folder)
        for index, part in enumerate(self.sections[kind]):
            if packs.identity(part, kind) == new:
                self.kind.set(kind)
                self.index[kind] = index
                if converted and not part.get("base_resource_name"):
                    part["base_resource_name"] = old
                    number = self.catalog.kind_of_fighter(old)
                    if number is not None:
                        part["base_kind"] = number
                    self.log("%s was %s's own tree, so %s is its base now" % (new, old, old))
                self.show_kind()
                break
        if converted:
            self.log("next: Renumber costumes (an added-slot moveset sits at c%s and the "
                     "select screen starts at c00), then Write fighter.toml and Write "
                     "config.json; the old plugin.nro hooks %s by kind and needs a rebuild "
                     "from the Rust tab" % ("NN", old))
        return True

    def renumber_part(self, resource: str, confirm=None) -> bool:
        """Move a fighter's costumes to c00, c01, ... then read the pack again.
        confirm(plan) may say no once the plan is known."""
        if not self.require_folder():
            return False
        if not (self.folder / packs.FIGHTER / resource).is_dir():
            self.log("nothing to renumber: fighter/%s is not in this pack" % resource)
            return False
        plan = packs.renumber_plan(self.folder, resource)
        if not plan["moves"] and not plan["effect"] and not plan["leftovers"]:
            self.log("%s already runs from c00 with nothing left over" % resource)
            return False
        if confirm is not None and not confirm(plan):
            self.log("renumbering of %s cancelled" % resource)
            return False
        self.log("renumbering %s: %d path(s) moved" % (resource, len(plan["moves"])))
        for line in packs.apply_renumber(self.folder, plan):
            self.log("    " + line)
        self.log_kept()
        self.open_folder(self.folder)
        for index, part in enumerate(self.sections[packs.FIGHTER]):
            if packs.identity(part, packs.FIGHTER) == resource:
                self.kind.set(packs.FIGHTER)
                self.index[packs.FIGHTER] = index
                part["color_start"] = 0
                self.show_kind()
                break
        return True

    def merge_needed(self, clone: str) -> bool:
        """Whether config.json holds entries that belong to other parts of this pack."""
        module = import_tool("make_clone_pack")
        config = self.folder / "config.json" if self.folder else None
        if module is None or config is None or not config.is_file():
            return False
        try:
            existing = json.loads(config.read_text(encoding="utf-8"))
        except ValueError:
            return False
        foreign = module.foreign_entries(existing, clone)
        if foreign:
            self.log("config.json holds %d entry(s) belonging to other parts of this "
                     "pack, so this write merges instead of replacing" % foreign)
        return bool(foreign)

    def new_pack(self) -> None:
        parent = filedialog.askdirectory(title="Where should the pack folder go?")
        if not parent:
            return
        name = simpledialog.askstring(TITLE, "Folder name for the pack",
                                      initialvalue="Clone Engine - ")
        if not name:
            return
        folder = Path(parent) / name
        self.identity.collect()
        made = packs.scaffold(folder, self.kind.get(), dict(self.state))
        self.log("made %s" % folder)
        for entry in made:
            self.log("    " + entry)
        self.open_folder(folder)

    def require_folder(self) -> bool:
        if self.folder is None:
            messagebox.showinfo(TITLE, "Open a pack folder first.")
            return False
        return True

    def save_state(self) -> None:
        """Keep the fields no manifest can hold, and only those."""
        if self.folder is None:
            return
        keep = {}
        for kind, parts in self.sections.items():
            for section in parts:
                beyond = any(section.get(key) for key in
                             ("articles", "params", "item_params", "owner_params",
                              "owner_prc_files", "item_common_prc"))
                if section and (kind == packs.FIGHTER or beyond):
                    keep.setdefault(kind, []).append(section)
        if not keep:
            return
        path = packs.write_state(self.folder, keep)
        self.log("saved %s" % path.name)
        self.log_kept()


def wrap_within(container: tk.Misc, labels, margin: int = 12) -> None:
    """Wrap each label to the width left of it inside the container, again on
    every resize, so a hint or a note never runs past the window's edge."""
    def fit() -> None:
        width = container.winfo_width()
        if width <= 1:
            return
        for label in labels:
            left = label.winfo_rootx() - container.winfo_rootx()
            if 0 <= left < width:
                label.configure(wraplength=max(160, width - left - margin))
    container.bind("<Configure>", lambda _: container.after_idle(fit), add="+")
    for label in labels:
        label.bind("<Configure>", lambda _: container.after_idle(fit), add="+")


class RenameDialog(tk.Toplevel):
    """Old name to new name for one kind: the names on disk to pick from, the
    name typed on the form as the default new one."""

    def __init__(self, parent: tk.Misc, kind: str, on_disk, guess: str, new: str, done):
        super().__init__(parent)
        self.title("Rename the %s's files" % kind)
        self.resizable(False, False)
        self.done = done
        self.old = tk.StringVar(value=guess)
        self.new = tk.StringVar(value=new)
        body = ttk.Frame(self, padding=12)
        body.grid(sticky="nsew")
        ttk.Label(body, text="Name on disk").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Combobox(body, textvariable=self.old, values=list(on_disk), width=28,
                     state="readonly" if on_disk else "normal").grid(row=0, column=1, pady=2)
        ttk.Label(body, text="New name").grid(row=1, column=0, sticky="w", pady=2)
        entry = ttk.Entry(body, textvariable=self.new, width=30)
        entry.grid(row=1, column=1, pady=2)
        ttk.Label(body, text="every folder, file, label and manifest line that carries "
                            "the old name takes the new one; a plugin.nro is reported, "
                            "not changed", foreground="#555", wraplength=360,
                  justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 8))
        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Rename", command=self.confirm).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left")
        entry.focus_set()
        entry.bind("<Return>", lambda _: self.confirm())
        self.bind("<Escape>", lambda _: self.destroy())
        self.transient(parent.winfo_toplevel())
        self.grab_set()

    def confirm(self) -> None:
        old, new = self.old.get().strip(), self.new.get().strip()
        self.destroy()
        self.done(old, new)


class Scrolled(ttk.Frame):
    """A frame whose contents scroll when the window is shorter than they are:
    build into .body, and the bar appears only while it is needed."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        background = ttk.Style().lookup("TFrame", "background") or None
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0,
                                background=background)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.bar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.body = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _: self.fit())
        self.canvas.bind("<Configure>", self.resized)
        self.canvas.bind("<Enter>", lambda _: self.arm())
        self.canvas.bind("<Leave>", lambda _: self.disarm())

    def resized(self, event) -> None:
        self.canvas.itemconfigure(self.window, width=event.width)
        self.fit()

    def fit(self) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if self.overflows():
            self.bar.grid()
        else:
            self.bar.grid_remove()
            self.canvas.yview_moveto(0)
        self.after_idle(self.settle)

    def settle(self) -> None:
        """The canvas sizes the body lazily; a width set during its own resize
        event can be missed, so it is set again once the event is over."""
        width = self.canvas.winfo_width()
        if width > 1 and self.body.winfo_width() != width:
            self.canvas.itemconfigure(self.window, width=width)

    def overflows(self) -> bool:
        return self.body.winfo_reqheight() > self.canvas.winfo_height()

    def arm(self) -> None:
        self.canvas.bind_all("<MouseWheel>", self.wheel)
        self.canvas.bind_all("<Button-4>", self.wheel)
        self.canvas.bind_all("<Button-5>", self.wheel)

    def disarm(self) -> None:
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(sequence)

    def wheel(self, event) -> None:
        if isinstance(event.widget, (tk.Text, tk.Listbox, ttk.Treeview, ttk.Combobox)):
            return
        if not self.overflows():
            return
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            self.canvas.yview_scroll(-1, "units")
        else:
            self.canvas.yview_scroll(1, "units")


class Fields:
    """A row per key: label, entry or combobox, and the tk variable behind it."""

    def __init__(self, parent: tk.Misc):
        self.parent = parent
        self.vars: dict[str, tk.Variable] = {}
        self.widgets: dict[str, tk.Misc | None] = {}
        self.hints: list[ttk.Label] = []
        self.row = 0

    def hint(self, text: str) -> None:
        label = ttk.Label(self.parent, text=text, foreground="#555", justify="left")
        label.grid(row=self.row, column=2, sticky="w", padx=8)
        self.hints.append(label)

    def entry(self, key: str, label: str, width: int = 28, hint: str = "") -> None:
        variable = tk.StringVar()
        self.vars[key] = variable
        self.widgets[key] = None
        ttk.Label(self.parent, text=label).grid(row=self.row, column=0, sticky="w", pady=2)
        ttk.Entry(self.parent, textvariable=variable, width=width).grid(
            row=self.row, column=1, sticky="w", pady=2)
        if hint:
            self.hint(hint)
        self.row += 1

    def choice(self, key: str, label: str, values, width: int = 26, hint: str = "") -> None:
        variable = tk.StringVar()
        self.vars[key] = variable
        ttk.Label(self.parent, text=label).grid(row=self.row, column=0, sticky="w", pady=2)
        box = ttk.Combobox(self.parent, textvariable=variable, values=list(values),
                           width=width)
        box.grid(row=self.row, column=1, sticky="w", pady=2)
        self.widgets[key] = box
        if hint:
            self.hint(hint)
        self.row += 1

    def flag(self, key: str, label: str, hint: str = "") -> None:
        variable = tk.BooleanVar()
        self.vars[key] = variable
        ttk.Checkbutton(self.parent, text=label, variable=variable).grid(
            row=self.row, column=1, sticky="w", pady=2)
        if hint:
            self.hint(hint)
        self.row += 1

    def buttons(self, pairs) -> None:
        frame = ttk.Frame(self.parent)
        frame.grid(row=self.row, column=0, columnspan=3, sticky="w", pady=(10, 2))
        for label, command in pairs:
            ttk.Button(frame, text=label, command=command).pack(side="left", padx=(0, 6))
        self.row += 1

    def read(self) -> dict:
        return {key: variable.get() for key, variable in self.vars.items()}

    def watch(self, callback) -> None:
        for variable in self.vars.values():
            variable.trace_add("write", lambda *_: callback())

    def fill(self, values: dict) -> None:
        for key, variable in self.vars.items():
            if key in values and values[key] is not None:
                variable.set(values[key])


def spawn_list(value) -> list[str]:
    """The containers an item.toml names, whether written as a list or one string."""
    if not value:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(part).strip() for part in value]


def whole_numbers(values: dict, keys) -> None:
    """Turn these fields into ints in place: blank stays blank so the key is
    dropped, and text that is not a number yet is left out of this collect."""
    for key in keys:
        text = str(values.get(key, "")).strip()
        if not text:
            values[key] = ""
            continue
        try:
            values[key] = int(text, 0)
        except ValueError:
            values.pop(key, None)


def named_choice(rows) -> list[str]:
    return ["%s (%d)" % (name, kind) for kind, name in rows]


def split_choice(text: str) -> tuple[str, int | None]:
    name = text.split(" (")[0].strip()
    number = None
    if "(" in text and text.rstrip().endswith(")"):
        try:
            number = int(text.rsplit("(", 1)[1].rstrip(")"))
        except ValueError:
            number = None
    return name, number


class IdentityPanel(ttk.Frame):
    """One form per pack kind, and the buttons that write what it describes."""

    def __init__(self, parent: tk.Misc, app: Workbench):
        super().__init__(parent, padding=10)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.scroll = Scrolled(self)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        self.scroll.body.columnconfigure(0, weight=1)
        self.frames: dict[str, ttk.Frame] = {}
        self.fields: dict[str, Fields] = {}
        self.articles: list[dict] = []
        self.article_picked: int | None = None
        self.item_candidates: list[str] = []
        self.loading = False
        self.pending: str | None = None
        self._build_fighter()
        self._build_item()
        self._build_stage()
        for kind, frame in self.frames.items():
            wrap_within(frame, self.fields[kind].hints)
        self.show(packs.FIGHTER)
        for fields in self.fields.values():
            fields.watch(self.changed)
        for variable in list(self.spawn_vars.values()) + list(self.form_vars.values()):
            variable.trace_add("write", lambda *_: self.changed())

    def changed(self) -> None:
        """Any edit reaches the part and the Rust tab once the typing settles."""
        if self.loading or self.pending is not None:
            return
        self.pending = self.after(150, self.sync)

    def sync(self) -> None:
        if self.pending is not None:
            self.after_cancel(self.pending)
            self.pending = None
        kind = self.app.kind.get()
        before = (self.app.state.get("base_kind"), packs.identity(self.app.state, kind))
        self.collect(quiet=True)
        after = (self.app.state.get("base_kind"), packs.identity(self.app.state, kind))
        self.app.refresh_parts()
        if before != after:
            self.app.params.load()
        self.app.rust.refresh()

    def _frame(self, kind: str) -> Fields:
        frame = ttk.Frame(self.scroll.body)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(2, weight=1)
        self.frames[kind] = frame
        fields = Fields(frame)
        self.fields[kind] = fields
        return fields

    def _build_fighter(self) -> None:
        fields = self._frame(packs.FIGHTER)
        catalog = self.app.catalog
        fields.choice("base_fighter", "Base fighter",
                      named_choice(catalog.fighter_bases()),
                      hint="what your clone is built on")
        fields.entry("resource_name", "Resource name",
                     hint="your files live under fighter/<this>")
        fields.entry("ui_chara", "ui_chara", hint="blank means ui_chara_<resource>")
        fields.entry("fighter_kind_name", "Kind name",
                     hint="blank means fighter_kind_<resource>")
        fields.entry("color_start", "First costume", width=6)
        fields.entry("color_count", "Costumes", width=6,
                     hint="how many the clone has; past what the pack ships, c00 is reused")
        fields.entry("display_name", "Name label", hint="fighter.toml: the nam_chr*_00_<x> label suffix in msg_name.xmsbt; blank = the name")
        fields.entry("series", "Series", hint="fighter.toml: ui_series_id, such as mario")
        fields.entry("disp_order", "CSS position", width=6, hint="fighter.toml: -1 hides it")
        fields.entry("narration", "Announcer call",
                     hint="fighter.toml: vc_narration_characall_<name>, blank uses the base's")
        fields.flag("staffroll", "Ships its own staff roll texture",
                    hint="fighter.toml: standard/staffroll/texture/standard_staffroll_<name>.nutexb")
        fields.flag("own_css", "Plugin keeps its CSK and ParamConfig code",
                    hint="a one-slot mod's plugin: its add_chara_db_entry_info publishes the row (Manifest: own_css(), fighter.toml: css = false) and its param_config::update_* set the vl.prc values; the Rust tab shows both with the clone's names")
        fields.entry("kirby_statuses", "Kirby copy statuses", width=6,
                     hint="fighter.toml: how many status kinds Kirby's copy needs; the engine picks the numbers")
        fields.flag("owns_param_resources", "Ships its own vl.prc and params")
        fields.flag("kirby_copy_full_model", "Kirby wears the whole body, not a cap")
        fields.choice("kirby_copy_donor", "Kirby copy donor",
                      [""] + [name for _, name in catalog.fighter_bases()],
                      hint="whose copy model your clone borrows; blank takes the base's own hat")
        fields.entry("kirby_copy_suffix", "Copy suffix", hint="default fitkirby")
        fields.choice("kirby_copy_motion_donor", "Copy motion donor",
                      [""] + [name for _, name in catalog.fighter_bases()])
        fields.flag("declare_shipped", "Declare the files this pack ships (--pack-dir)")

        frame = self.frames[packs.FIGHTER]
        articles = ttk.LabelFrame(frame, text="Articles", padding=6)
        articles.grid(row=fields.row, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        fields.row += 1
        self.article_owner = tk.StringVar()
        self.article_weapon = tk.StringVar()
        self.article_name = tk.StringVar()
        ttk.Label(articles, text="Source fighter").grid(row=0, column=0, sticky="w")
        owner = ttk.Combobox(articles, textvariable=self.article_owner,
                             values=catalog.weapon_owners(), width=16)
        owner.grid(row=0, column=1, padx=4)
        owner.bind("<<ComboboxSelected>>", self._weapons_changed)
        ttk.Label(articles, text="Source weapon").grid(row=0, column=2, sticky="w")
        self.weapon_box = ttk.Combobox(articles, textvariable=self.article_weapon, width=38)
        self.weapon_box.grid(row=0, column=3, padx=4)
        ttk.Label(articles, text="Your directory name").grid(row=1, column=0, sticky="w",
                                                            pady=(4, 0))
        ttk.Entry(articles, textvariable=self.article_name, width=20).grid(
            row=1, column=1, padx=4, pady=(4, 0))
        self.article_copy = tk.BooleanVar()
        ttk.Checkbutton(articles, text="for a move Kirby copies",
                        variable=self.article_copy).grid(row=1, column=2, pady=(4, 0))
        buttons = ttk.Frame(articles)
        buttons.grid(row=1, column=3, sticky="w", padx=4, pady=(4, 0))
        ttk.Button(buttons, text="Add", command=self.add_article).pack(side="left")
        ttk.Button(buttons, text="Remove",
                   command=self.remove_article).pack(side="left", padx=4)
        self.article_list = tk.Listbox(articles, height=4, exportselection=False)
        self.article_list.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        self.article_list.bind("<<ListboxSelect>>", self.article_chosen)
        articles.columnconfigure(3, weight=1)

        fields.buttons((
            ("Write fighter.toml", self.write_fighter_toml),
            ("Write config.json", self.write_fighter_config),
            ("Save descriptor", self.save_descriptor),
            ("Show Rust", lambda: self.app.tabs.select(self.app.rust)),
            ("Rename files", self.rename_files),
            ("Renumber costumes", self.renumber_costumes),
        ))

    def _build_item(self) -> None:
        fields = self._frame(packs.ITEM)
        catalog = self.app.catalog
        fields.choice("base_item", "Base item", named_choice(catalog.item_bases()),
                      hint="what your item is built on")
        fields.choice("resource_name", "Resource name", (),
                      hint="your files live under item/<this>")
        self.item_resource = fields.vars["resource_name"]
        box = fields.widgets["resource_name"]
        box.bind("<<ComboboxSelected>>", self.item_chosen)
        fields.entry("agent_name", "Agent name", hint="blank means the resource name")
        fields.entry("ui_id", "ui_id", hint="blank means ui_item_<resource>")
        fields.entry("training_order", "Training order", width=6)
        fields.entry("spawn_per", "Natural spawn weight", width=8,
                     hint="blank means it never drops by itself; the Assist trophy is 150")
        fields.entry("spawn_min", "Fewest at once", width=6)
        fields.entry("spawn_max", "Most at once", width=6)
        frame = self.frames[packs.ITEM]
        sources = ttk.LabelFrame(frame, text="Also comes out of these containers",
                                 padding=6)
        sources.grid(row=fields.row, column=0, columnspan=3, sticky="w", pady=(8, 2))
        fields.row += 1
        self.spawn_vars = {}
        for index, source in enumerate(SPAWN_CONTAINERS):
            variable = tk.BooleanVar()
            self.spawn_vars[source] = variable
            ttk.Checkbutton(sources, text=source, variable=variable).grid(
                row=0, column=index, padx=4, sticky="w")
        note = ttk.Label(sources, text="the weight alone makes it appear on the stage; "
                                       "tick the containers it can also come out of",
                         foreground="#555", justify="left")
        note.grid(row=1, column=0, columnspan=5, sticky="w", pady=(4, 0))
        fields.hints.append(note)
        fields.flag("declare_shipped", "Declare the files this pack ships (--pack-dir)")
        fields.buttons((
            ("Write item.toml", self.write_item_toml),
            ("Write config.json", self.write_item_config),
            ("Rename files", self.rename_files),
        ))

    def _build_stage(self) -> None:
        fields = self._frame(packs.STAGE)
        catalog = self.app.catalog
        places = catalog.stage_places()
        fields.entry("place", "Place", hint="lowercase folder name under stage/")
        fields.entry("display_name", "Display name")
        fields.entry("id_name", "StageID name", hint="blank means CamelCase of the place")
        fields.entry("series", "Series", hint="ui_series_id, such as mario or sonic")
        fields.entry("disp_order", "Grid position", width=6, hint="-1 hides it")
        fields.choice("donor", "Behaviour donor", places,
                      hint="the vanilla stage whose behaviour runs and whose files "
                           "fill in what you do not ship")
        fields.choice("resource_place", "Resource place", [""] + places,
                      hint="load files from this stage's folders instead of your own")
        fields.flag("ships_battle_tree", "Ships a stage/<place>/battle tree")
        fields.choice("bgm", "Music playlist",
                      [""] + [name for name, _ in catalog.bgm_sets()],
                      hint="blank borrows the donor's music")
        fields.entry("bgm_setting_no", "Playlist column", width=6,
                     hint="which column of that playlist, counted from 0")
        fields.flag("bgm_selector", "Gets the album selector")
        fields.choice("content_donor", "Content donor", [""] + places,
                      hint="tools only: the stage whose files fill gaps, if not the "
                           "behaviour donor")
        fields.choice("content_donor_tree", "Content donor tree", ["", "normal", "battle"],
                      hint="tools only: when the files came from a different tree")
        fields.flag("carry_donor_scenery", "Inherit the donor's scenery directories",
                    hint="tools only: off drops the donor's scenery, which its "
                         "behaviour may still look for")
        frame = self.frames[packs.STAGE]
        forms = ttk.LabelFrame(frame, text="Forms", padding=6)
        forms.grid(row=fields.row, column=0, columnspan=3, sticky="w", pady=(8, 2))
        fields.row += 1
        self.form_vars = {}
        for index, form in enumerate(("normal", "omega", "battlefield")):
            variable = tk.BooleanVar(value=form == "normal")
            self.form_vars[form] = variable
            ttk.Checkbutton(forms, text=form, variable=variable).grid(
                row=0, column=index, padx=4)
        fields.buttons((
            ("Write stage.toml", self.write_stage_toml),
            ("Write config.json", self.write_stage_config),
            ("Stamp sound bank id", self.stamp_bank),
            ("Rename files", self.rename_files),
        ))

    def rename_files(self) -> None:
        """Rename the part's folders, files and labels from the name on disk to
        the name on the form, after a look at what that touches."""
        if not self.app.require_folder():
            return
        kind = self.app.kind.get()
        self.collect(quiet=True)
        typed = packs.identity(self.app.state, kind)
        on_disk = packs.own_names(self.app.folder, packs.TREE_OF_KIND[kind],
                                  self.app.vanilla_names(kind))
        if kind == packs.FIGHTER:
            on_disk += [name for name in packs.vanilla_slot_names(
                self.app.folder, packs.TREE_OF_KIND[kind], self.app.vanilla_names(kind))
                if name not in on_disk]
        if not on_disk:
            self.app.log("nothing to rename: the pack ships no %s of its own" % kind)
            return
        others = {packs.identity(part, kind) for part in self.app.sections[kind]
                  if part is not self.app.state}
        free = [name for name in on_disk if name not in others]
        guess = free[0] if len(free) == 1 else (typed if typed in on_disk else on_disk[0])

        def confirm(plan: dict) -> bool:
            stuck = "".join("\n  %s" % path.as_posix() for path in plan["stuck"])
            return messagebox.askyesno(
                TITLE, "Rename %s to %s?\n\n%d folders and files renamed, %d text files "
                       "edited.%s" % (plan["old"], plan["new"], len(plan["moves"]),
                                      len(plan["edits"]),
                                      "\n\nStill carry the old name inside and need a "
                                      "rebuild or a hand edit:" + stuck if stuck else ""))

        RenameDialog(self, kind, on_disk, guess, typed if typed != guess else "",
                     lambda old, new: self.app.rename_part(kind, old, new, confirm))

    def renumber_costumes(self) -> None:
        """Move the fighter's costumes to c00..: the select screen the engine
        publishes starts at c00, and every added-slot moveset starts higher."""
        if not self.app.require_folder():
            return
        self.collect(quiet=True)
        resource = packs.identity(self.app.state, packs.FIGHTER)
        on_disk = packs.own_names(self.app.folder, packs.FIGHTER,
                                  self.app.vanilla_names(packs.FIGHTER))
        if resource not in on_disk:
            if not on_disk:
                self.app.log("nothing to renumber: the pack ships no fighter of its own "
                             "(Rename files first if it is an added-slot moveset)")
                return
            resource = on_disk[0]

        def confirm(plan: dict) -> bool:
            numbers = sorted(plan["mapping"])
            lines = ["Move %s's costumes c%02d to c%02d onto c00 to c%02d?" % (
                resource, numbers[0], numbers[-1], len(numbers) - 1),
                "", "%d folder(s) and file(s) move (model, motion, camera, Kirby copy, "
                    "sound banks, one-slot effects, trails)." % len(plan["moves"])]
            if plan["effect"]:
                lines.append("%s is copied to %s, the name the engine loads."
                             % (plan["effect"][0].rsplit("/", 1)[-1],
                                plan["effect"][1].rsplit("/", 1)[-1]))
            for name in plan["leftovers"]:
                lines.append("%s is removed (kept in Backups): it patches the base's "
                             "select screen row." % name)
            if plan["unmapped"]:
                lines.append("Left alone, no body costume has their number: %s%s"
                             % (", ".join(plan["unmapped"][:3]),
                                " and %d more" % (len(plan["unmapped"]) - 3)
                                if len(plan["unmapped"]) > 3 else ""))
            if plan["blocked"]:
                lines.append("Left alone, their target exists: %s"
                             % ", ".join(source for source, _ in plan["blocked"][:3]))
            lines += ["", "config.json is not changed: write it again afterwards."]
            return messagebox.askyesno(TITLE, "\n".join(lines))

        self.app.renumber_part(resource, confirm)

    def set_item_candidates(self, names) -> None:
        """Offer every item tree the pack ships, since a pack may hold several."""
        self.item_candidates = list(names)
        box = self.fields[packs.ITEM].widgets.get("resource_name")
        if box is not None:
            box.configure(values=self.item_candidates)

    def item_chosen(self, _event=None) -> None:
        """Re-read the base of the item tree the maker switched to."""
        folder = self.app.folder
        resource = self.item_resource.get().strip()
        if folder is None or not resource:
            return
        section = self.app.part(packs.ITEM)
        if section.get("resource_name") == resource:
            return
        section["resource_name"] = resource
        base = packs.base_from_config(packs.read_config(folder), packs.ITEM, resource,
                                     self.app.catalog.item_dirs())
        if base:
            kind = self.app.catalog.kind_of_item(base)
            section["base_item"] = base
            if kind is not None:
                section["base_kind"] = kind
                self.fields[packs.ITEM].vars["base_item"].set("%s (%d)" % (base, kind))
            self.app.log("scan: %s is built on %s" % (resource, base))

    def show(self, kind: str) -> None:
        for name, frame in self.frames.items():
            if name == kind:
                frame.grid()
            else:
                frame.grid_remove()
        self.scroll.after_idle(self.scroll.fit)

    def load(self) -> None:
        """Fill every form from its own section, so the parts cannot cross."""
        if self.pending is not None:
            self.after_cancel(self.pending)
            self.pending = None
        self.loading = True
        try:
            self._load()
        finally:
            self.loading = False

    def _load(self) -> None:
        catalog = self.app.catalog
        fighter = dict((number, name) for number, name in catalog.fighter_bases())
        item = dict((number, name) for number, name in catalog.item_kinds())
        for kind, fields in self.fields.items():
            section = self.app.part(kind)
            for variable in fields.vars.values():
                variable.set(False if isinstance(variable, tk.BooleanVar) else "")
            fields.fill(section)
            base = section.get("base_kind")
            if base is None:
                continue
            base = int(base)
            if kind == packs.FIGHTER and base in fighter:
                fields.vars["base_fighter"].set("%s (%d)" % (fighter[base], base))
            if kind == packs.ITEM and base in item:
                fields.vars["base_item"].set("%s (%d)" % (item[base], base))
        self.articles = list(self.app.part(packs.FIGHTER).get("articles") or [])
        self.refresh_articles()
        chosen = spawn_list(self.app.part(packs.ITEM).get("spawn_from"))
        for source, variable in self.spawn_vars.items():
            variable.set(source in chosen)
        forms = self.app.part(packs.STAGE).get("forms") or ["normal"]
        for form, variable in self.form_vars.items():
            variable.set(form in forms)

    def collect(self, quiet: bool = False) -> dict:
        """Read every field of the visible form into the shared state. A field
        left blank drops its key, so a value can be taken back."""
        if self.pending is not None:
            self.after_cancel(self.pending)
            self.pending = None
        kind = self.app.kind.get()
        values = self.fields[kind].read()
        state = self.app.state
        if kind == packs.FIGHTER:
            text = values.pop("base_fighter", "")
            name, number = split_choice(text)
            if number is not None:
                state["base_kind"] = number
                state["base_resource_name"] = name
            elif not text.strip():
                state.pop("base_kind", None)
                state.pop("base_resource_name", None)
            state["articles"] = self.articles
            for key in ("color_start", "color_count"):
                try:
                    values[key] = int(values.get(key) or (0 if key == "color_start" else 8))
                except ValueError:
                    values.pop(key, None)
            whole_numbers(values, ("disp_order", "kirby_statuses"))
        elif kind == packs.ITEM:
            text = values.pop("base_item", "")
            name, number = split_choice(text)
            if number is not None:
                state["base_kind"] = number
                state["base_item"] = name
            elif not text.strip():
                state.pop("base_kind", None)
                state.pop("base_item", None)
            whole_numbers(values, ("training_order", "spawn_min", "spawn_max", "spawn_per"))
            state["spawn_from"] = [source for source, variable in self.spawn_vars.items()
                                   if variable.get()]
        elif kind == packs.STAGE:
            whole_numbers(values, ("disp_order", "bgm_setting_no"))
            columns = self.app.catalog.bgm_columns(values.get("bgm", ""))
            column = values.get("bgm_setting_no")
            if not quiet and columns is not None and isinstance(column, int) \
                    and column >= columns:
                self.app.log("%s holds %d column(s), so bgm_setting_no %d is out of "
                             "range" % (values.get("bgm"), columns, column))
            state["forms"] = [form for form, variable in self.form_vars.items()
                              if variable.get()]
        for key, value in values.items():
            if value in ("", None):
                state.pop(key, None)
            else:
                state[key] = value
        return state

    def _weapons_changed(self, _event=None) -> None:
        owner = self.article_owner.get()
        weapons = self.app.catalog.weapons_for(owner)
        self.weapon_box.configure(values=["WEAPON_KIND_%s (%d)" % (const.upper(), kind)
                                          for kind, const in weapons])

    def add_article(self) -> None:
        """Add a source to a directory the scan found, or add a new article outright."""
        const, _ = split_choice(self.article_weapon.get())
        name = self.article_name.get().strip()
        if not const or not name:
            messagebox.showinfo(TITLE, "Pick a source weapon and give the article a "
                                       "directory name of its own.")
            return
        entry = {"owner": self.article_owner.get(), "weapon": const, "name": name,
                 "kirby_copy": bool(self.article_copy.get())}
        for index, known in enumerate(self.articles):
            if known.get("name") == name:
                self.articles[index] = entry
                break
        else:
            self.articles.append(entry)
        self.refresh_articles()
        self.app.part(packs.FIGHTER)["articles"] = self.articles
        self.app.rust.refresh()

    def remove_article(self) -> None:
        chosen = sorted(self.article_list.curselection(), reverse=True)
        if not chosen:
            target = self.article_target()
            if target is None:
                messagebox.showinfo(TITLE, "Click the article to remove, or type its "
                                           "directory name.")
                return
            chosen = [target]
        for index in chosen:
            gone = self.articles.pop(index)
            self.app.log("removed the article %s" % gone.get("name"))
        self.article_picked = None
        self.refresh_articles()
        self.app.part(packs.FIGHTER)["articles"] = self.articles
        self.app.rust.refresh()

    def article_chosen(self, _event=None) -> None:
        """Clicking a scanned directory puts its name in the field to give it a source."""
        selection = self.article_list.curselection()
        if selection and selection[0] < len(self.articles):
            self.article_picked = selection[0]
            self.article_name.set(self.articles[selection[0]].get("name") or "")

    def article_target(self) -> int | None:
        """Which article Remove means: the selected row, the last one clicked, or the
        one whose name is in the field. A list can lose its highlight to any other
        widget that takes the selection, so the click is remembered as well."""
        selection = self.article_list.curselection()
        if selection:
            return selection[0]
        name = self.article_name.get().strip()
        if name:
            for index, article in enumerate(self.articles):
                if article.get("name") == name:
                    return index
        if self.article_picked is not None and self.article_picked < len(self.articles):
            return self.article_picked
        return None

    def refresh_articles(self) -> None:
        self.article_list.delete(0, "end")
        for article in self.articles:
            if not (article.get("owner") and article.get("weapon")):
                self.article_list.insert("end", "%s: ships files, needs a source weapon"
                                         % article.get("name"))
                continue
            self.article_list.insert("end", "%s from %s (%s)%s" % (
                article.get("name"), article.get("owner"), article.get("weapon"),
                " on the Kirby copy" if article.get("kirby_copy") else ""))

    def _generator_argv(self, kind: str) -> list[str] | None:
        state = self.collect()
        folder = self.app.folder
        base = state.get("base_resource_name" if kind == packs.FIGHTER else "base_item")
        clone = state.get("resource_name")
        if not base or not clone:
            messagebox.showinfo(TITLE, "Pick a base and a resource name first.")
            return None
        argv = ["--base", str(base), "--clone", str(clone), "--kind", kind,
                "--out", str(folder / "config.json")]
        if state.get("declare_shipped"):
            argv += ["--pack-dir", str(folder)]
        if self.app.merge_needed(str(clone)):
            argv.append("--merge")
        argv += ["--arc-index", str(self.app.catalog.arc_index)]
        return argv

    def write_fighter_config(self) -> None:
        if not self.app.require_folder():
            return
        argv = self._generator_argv(packs.FIGHTER)
        if argv is None:
            return
        state = self.app.state
        if isinstance(state.get("color_count"), int):
            argv += ["--color-start", str(state.get("color_start") or 0),
                     "--color-count", str(state["color_count"])]
        if state.get("kirby_copy_suffix"):
            argv += ["--kirby-copy-suffix", str(state["kirby_copy_suffix"])]
        if state.get("kirby_copy_donor"):
            argv += ["--kirby-copy-donor", str(state["kirby_copy_donor"])]
        if state.get("kirby_copy_motion_donor"):
            argv += ["--kirby-copy-motion-donor", str(state["kirby_copy_motion_donor"])]
        self.app.keep("config.json")
        self.app.run_tool("make_clone_pack", argv)
        self.app.save_state()
        self.app.files.refresh()

    def write_item_config(self) -> None:
        if not self.app.require_folder():
            return
        argv = self._generator_argv(packs.ITEM)
        if argv is not None:
            self.app.keep("config.json")
            self.app.run_tool("make_clone_pack", argv)
            self.app.files.refresh()

    def manifest_parts(self, kind: str) -> list[dict]:
        """Every part of this kind that names itself, the current one as the
        form now shows it, in the values a manifest holds."""
        self.collect()
        keys = packs.ITEM_KEYS if kind == packs.ITEM else packs.STAGE_KEYS
        out = []
        for part in self.app.sections[kind]:
            if not packs.identity(part, kind):
                continue
            values = {key: part[key] for key in keys if key in part}
            if kind == packs.ITEM:
                if values.get("spawn_from"):
                    values["spawn_from"] = ", ".join(spawn_list(values["spawn_from"]))
                elif "spawn_from" in values:
                    del values["spawn_from"]
            out.append(values)
        return out

    def write_fighter_toml(self) -> None:
        """fighter.toml is the registration of a pack with no plugin: the engine
        reads it at boot. A plugin registers from the Manifest on the Rust tab
        instead; if both exist the file is read first and wins."""
        if not self.app.require_folder():
            return
        self.collect()
        state = dict(self.app.part(packs.FIGHTER))
        if not state.get("resource_name"):
            messagebox.showinfo(TITLE, "Give the fighter a resource name first.")
            return
        if not (state.get("base_resource_name") or state.get("base_fighter")):
            messagebox.showinfo(TITLE, "Pick the base fighter first.")
            return
        if len(self.app.sections[packs.FIGHTER]) > 1:
            self.app.log("fighter.toml: several fighters in one pack need [[fighter]] blocks; "
                         "the window writes the current one flat, so put each fighter in "
                         "its own pack folder or edit the file by hand")
        written = packs.write_fighter_manifest(self.app.folder / packs.FIGHTER_MANIFEST, state)
        self.app.log("fighter.toml: wrote %s" % ", ".join(written))
        self.app.log("    the engine registers the fighter from this file at boot; a pack "
                     "with a plugin registers from the Manifest on the Rust tab instead, "
                     "and a plugin that also registers gets this file's kind back")
        engine_rules, config_rules = emit.split_rules(state)
        if state.get("own_css"):
            if engine_rules:
                self.app.log("    [params]: %d rule(s) the game reads past ParamConfig "
                             "(fighter_param, param_motion, common, param_thrown); the engine "
                             "applies them" % len(engine_rules))
            if config_rules:
                self.app.log("    %d vl.prc rule(s) are not in fighter.toml: they are the plugin's "
                             "param_config::update_* calls (Rust tab)" % len(config_rules))
            self.app.log("    css = false: the plugin publishes the CSS row through CSK "
                         "(register_css_entry on the Rust tab)")
        elif engine_rules or config_rules:
            self.app.log("    [params]: %d rule(s); the engine applies them all"
                         % (len(engine_rules) + len(config_rules)))
        self.app.save_state()
        self.app.log_kept()

    def write_item_toml(self) -> None:
        if not self.app.require_folder():
            return
        parts = self.manifest_parts(packs.ITEM)
        if not parts:
            messagebox.showinfo(TITLE, "Give the item a resource name first.")
            return
        written = packs.write_manifests(self.app.folder / "item.toml", parts,
                                        packs.ITEM_KEYS)
        self.app.log("item.toml: wrote %s%s" % (
            ", ".join(written),
            " for %d items" % len(parts) if len(parts) > 1 else ""))
        if len(parts) == 1:
            tables = emit.item_table_lines(self.app.part(packs.ITEM))
            if tables and packs.write_item_tables(self.app.folder / "item.toml", tables):
                self.app.log("item.toml: wrote %s from the Parameters tab; an engine "
                             "without fighter.toml support ignores those tables"
                             % ", ".join(line for line in tables if line.startswith("[")))
        if len(parts) > 1:
            self.app.log("    two or more items in one item.toml need an engine newer "
                         "than 0.2.1-beta.1; that engine skips the whole file. For it, "
                         "keep one item per pack folder")
        self.app.save_state()
        self.app.log_kept()

    def write_stage_toml(self) -> None:
        if not self.app.require_folder():
            return
        parts = self.manifest_parts(packs.STAGE)
        if not parts:
            messagebox.showinfo(TITLE, "Give the stage a place first.")
            return
        for values in parts:
            if values.get("bgm_setting_no") is not None and not values.get("bgm"):
                self.app.log("%s: Playlist column needs a playlist; without one it is "
                             "ignored" % values.get("place"))
        written = packs.write_manifests(self.app.folder / "stage.toml", parts,
                                        packs.STAGE_KEYS)
        self.app.log("stage.toml: wrote %s%s" % (
            ", ".join(written),
            " for %d stages" % len(parts) if len(parts) > 1 else ""))
        if len(parts) > 1:
            self.app.log("    two or more stages in one stage.toml need an engine newer "
                         "than 0.2.1-beta.1; that engine skips the whole file. For it, "
                         "keep one stage per pack folder")
        self.app.save_state()
        self.app.log_kept()

    def write_stage_config(self) -> None:
        if not self.app.require_folder():
            return
        self.write_stage_toml()
        self.app.keep("config.json")
        self.app.run_tool("lint_stage_pack",
                          [str(self.app.folder), "--write-config",
                           "--arc-index", str(self.app.catalog.arc_index)],
                          pass_argv=True)
        self.app.files.refresh()

    def stamp_bank(self) -> None:
        if not self.app.require_folder():
            return
        self.app.keep(*("sound/bank/stage/se_stage_%s.nus3bank" % part["place"]
                        for part in self.app.sections[packs.STAGE] if part.get("place")))
        self.app.run_tool("lint_stage_pack",
                          [str(self.app.folder), "--write-bank-id",
                           "--arc-index", str(self.app.catalog.arc_index)],
                          pass_argv=True)

    def save_descriptor(self) -> None:
        if not self.app.require_folder():
            return
        self.collect()
        self.app.save_state()
        self.app.rust.refresh()


class FilesPanel(ttk.Frame):
    """What the folder actually ships, against what its config.json declares."""

    def __init__(self, parent: tk.Misc, app: Workbench):
        super().__init__(parent, padding=10)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Button(self, text="Refresh", command=self.refresh).grid(row=0, column=0,
                                                                   sticky="w")
        self.text = tk.Text(self, wrap="none", height=20)
        self.text.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        across = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        across.grid(row=2, column=0, sticky="ew")
        self.text.configure(yscrollcommand=scroll.set, xscrollcommand=across.set)

    def refresh(self) -> None:
        self.text.delete("1.0", "end")
        if self.app.folder is None:
            self.text.insert("end", "No pack open.\n")
            return
        summary = packs.summarize(self.app.folder)
        config = packs.config_summary(self.app.folder)
        lines = ["%s" % self.app.folder, ""]
        lines.append("parts: %s" % (", ".join(summary["kinds"]) or "none yet"))
        if summary["manifests"]:
            lines.append("manifests: " + ", ".join(summary["manifests"]))
        for kind in packs.KINDS:
            names = [self.app.part_label(kind, part) for part in self.app.sections[kind]
                     if packs.identity(part, kind)]
            if len(names) > 1:
                lines.append("%s parts: %s" % (kind, ", ".join(names)))
        lines.append("")
        lines.append("ships %d asset file(s)" % summary["files"])
        for tree, count in summary["trees"].items():
            lines.append("    %-12s %d" % (tree, count))
        if summary["colors"]:
            lines.append("costumes: " + ", ".join(
                "c%s (%d)" % (color, summary["color_counts"][color])
                for color in summary["colors"]))
        scanned = [article.get("name")
                   for article in (self.app.part(packs.FIGHTER).get("articles") or [])]
        if scanned:
            lines.append("articles of this fighter: " + ", ".join(scanned))
        if summary["articles"]:
            lines.append("model and motion directories beside body: "
                         + ", ".join(summary["articles"]))
        lines.append("plugin.nro: %s" % ("yes" if summary["plugin"] else "no"))
        lines.append("")
        if config.get("error"):
            lines.append("config.json will not parse: %s" % config["error"])
        elif config:
            lines.append("config.json declares %d dir(s), %d base(s), %d share(s), "
                         "%d group(s) holding %d file(s)"
                         % (config["new-dir-infos"], config["new-dir-infos-base"],
                            config["share-to-vanilla"], config["new-dir-files"],
                            config["declared"]))
            if summary["files"] and not config["declared"]:
                lines.append("some files this pack ships are not declared. Turn on "
                             "\"Declare the files this pack ships\" and write the "
                             "config again, or the game never loads them.")
        else:
            lines.append("no config.json yet. Write one from the Identity tab.")
        self.text.insert("end", "\n".join(lines) + "\n")


FIELD_COLUMNS = (("name", "Name", 330, "w"), ("type", "Type", 62, "w"),
                 ("offset", "Offset", 64, "e"), ("value", "Value", 130, "e"),
                 ("word", "Word", 110, "w"), ("vanilla", "Vanilla", 110, "e"),
                 ("file", "File", 180, "w"))
RULE_COLUMNS = (("where", "Where", 150, "w"), ("field", "Field", 330, "w"),
                ("op", "Op", 50, "w"), ("value", "Value", 130, "e"),
                ("note", "Note", 220, "w"))


class Sheet(ttk.Frame):
    """A table with headings and a scrollbar, addressed by row number like a list.
    Columns not meant for the current surface are hidden rather than rebuilt."""

    def __init__(self, parent: tk.Misc, columns, height: int):
        super().__init__(parent)
        self.keys = [key for key, _, _, _ in columns]
        self.tree = ttk.Treeview(self, columns=self.keys, show="headings", height=height,
                                 selectmode="browse")
        for key, heading, width, anchor in columns:
            self.tree.heading(key, text=heading, anchor=anchor)
            self.tree.column(key, width=width, minwidth=40, anchor=anchor,
                             stretch=(key == self.keys[0]))
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.tree.tag_configure("changed", foreground=CHANGED)
        self.count = 0

    def show_columns(self, keys) -> None:
        self.tree.configure(displaycolumns=[key for key in self.keys if key in keys])

    def shown_columns(self) -> list[str]:
        shown = self.tree.cget("displaycolumns")
        if shown in ("#all", ""):
            return list(self.keys)
        return list(shown)

    def clear(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.count = 0

    def append(self, values: dict, changed: bool = False) -> int:
        self.tree.insert("", "end", iid=str(self.count),
                         values=[str(values.get(key, "")) for key in self.keys],
                         tags=("changed",) if changed else ())
        self.count += 1
        return self.count - 1

    def size(self) -> int:
        return self.count

    def row(self, index: int) -> dict:
        values = self.tree.item(str(index), "values")
        return dict(zip(self.keys, (str(value) for value in values)))

    def rows(self) -> list[dict]:
        return [self.row(index) for index in range(self.count)]

    def is_changed(self, index: int) -> bool:
        return "changed" in self.tree.item(str(index), "tags")

    def selection(self) -> list[int]:
        return sorted(int(iid) for iid in self.tree.selection())

    def select(self, index: int) -> None:
        self.tree.selection_set(str(index))
        self.tree.see(str(index))

    def clear_selection(self) -> None:
        self.tree.selection_remove(*self.tree.selection())

    def on_select(self, callback) -> None:
        self.tree.bind("<<TreeviewSelect>>", callback)


class ParamsPanel(ttk.Frame):
    """Pick a field by name, give it a value, and get the call that sets it."""

    def __init__(self, parent: tk.Misc, app: Workbench):
        super().__init__(parent, padding=10)
        self.app = app
        self.rules: list[dict] = []
        self.rule_picked: int | None = None
        self.columnconfigure(3, weight=1)

        self.table = tk.StringVar(value=PARAM_TABLES[0])
        self.search = tk.StringVar()
        self.field = tk.StringVar()
        self.value = tk.StringVar(value="1.0")
        self.operation = tk.StringVar(value="Set")

        ttk.Label(self, text="Table").grid(row=0, column=0, sticky="w")
        self.table_box = ttk.Combobox(self, textvariable=self.table, width=16,
                                      values=list(PARAM_TABLES))
        self.table_box.grid(row=0, column=1, sticky="w")
        self.table_box.bind("<<ComboboxSelected>>", lambda _: self.refresh_fields())
        ttk.Label(self, text="File").grid(row=0, column=2, sticky="e")
        self.source = tk.StringVar(value=ANY_FILE)
        self.source_box = ttk.Combobox(self, textvariable=self.source, width=12,
                                       state="readonly")
        self.source_box.grid(row=0, column=3, sticky="w", padx=4)
        self.source_box.bind("<<ComboboxSelected>>", lambda _: self.refresh_fields())
        ttk.Label(self, text="Find").grid(row=0, column=4, sticky="e")
        self.search_box = ttk.Entry(self, textvariable=self.search, width=24)
        self.search_box.grid(row=0, column=5, sticky="w", padx=4)
        self.search_box.bind("<KeyRelease>", lambda _: self.refresh_fields())

        self.field_list = Sheet(self, FIELD_COLUMNS, height=12)
        self.field_list.grid(row=1, column=0, columnspan=6, sticky="nsew", pady=6)
        self.field_list.on_select(self.choose_field)
        self.rowconfigure(1, weight=3)

        row = ttk.Frame(self)
        row.grid(row=2, column=0, columnspan=6, sticky="ew")
        row.columnconfigure(1, weight=3)
        row.columnconfigure(5, weight=2)
        ttk.Label(row, text="Field").grid(row=0, column=0, sticky="w")
        self.field_box = ttk.Entry(row, textvariable=self.field, width=18)
        self.field_box.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(row, text="Operation").grid(row=0, column=2, sticky="w", padx=(8, 2))
        self.operation_box = ttk.Combobox(row, textvariable=self.operation, width=6,
                                          values=("Set", "Mul"))
        self.operation_box.grid(row=0, column=3, sticky="w")
        ttk.Label(row, text="Value").grid(row=0, column=4, sticky="w", padx=(8, 2))
        self.value_box = ttk.Combobox(row, textvariable=self.value, width=12)
        self.value_box.grid(row=0, column=5, sticky="ew")
        self.integer = tk.BooleanVar()
        self.free_type = ttk.Checkbutton(row, text="Whole number", variable=self.integer)
        self.free_type.grid(row=0, column=6, sticky="w", padx=(8, 0))
        self.add_button = ttk.Button(row, text="Add", command=self.add_rule)
        self.add_button.grid(row=0, column=7, padx=8)
        self.remove_button = ttk.Button(row, text="Remove", command=self.remove_rule)
        self.remove_button.grid(row=0, column=8)
        self.controls = (self.add_button, self.remove_button, self.field_box,
                         self.operation_box, self.value_box, self.free_type,
                         self.search_box)

        self.owner_row = ttk.LabelFrame(self, text="Owner", padding=6)
        self.owner_row.grid(row=3, column=0, columnspan=6, sticky="ew", pady=(6, 0))
        self.owner = tk.StringVar()
        self.offset = tk.StringVar(value="")
        self.owner_prc = tk.StringVar()
        self.owner_info: dict[str, tuple[int, str, str, str]] = {}
        ttk.Label(self.owner_row, text="Owner fighter").pack(side="left")
        self.owner_box = ttk.Combobox(self.owner_row, textvariable=self.owner, width=22,
                                      values=named_choice(app.catalog.fighter_bases()))
        self.owner_box.pack(side="left", padx=4)
        self.owner_box.bind("<<ComboboxSelected>>", lambda _: self.owner_changed())
        ttk.Label(self.owner_row, text="vl.prc file").pack(side="left", padx=(10, 2))
        self.owner_prc_box = ttk.Entry(self.owner_row, textvariable=self.owner_prc,
                                       width=40)
        self.owner_prc_box.pack(side="left")
        self.owner_prc_box.bind("<Return>", lambda _: self.owner_prc_changed())
        self.owner_prc_box.bind("<FocusOut>", lambda _: self.owner_prc_changed())
        ttk.Button(self.owner_row, text="Browse", command=self.browse_owner_prc).pack(
            side="left", padx=4)
        ttk.Label(self.owner_row, text="Offset").pack(side="left", padx=(10, 2))
        self.offset_box = ttk.Entry(self.owner_row, textvariable=self.offset, width=8)
        self.offset_box.pack(side="left")
        self.owner_row.grid_remove()

        self.values_row = ttk.LabelFrame(self, text="Values from", padding=6)
        self.values_row.grid(row=3, column=0, columnspan=6, sticky="ew", pady=(6, 0))
        self.values_file = tk.StringVar()
        self.extra: dict[str, tuple[str, str, str]] = {}
        ttk.Label(self.values_row, text="item/common/param/param.prc").pack(side="left")
        self.values_box = ttk.Entry(self.values_row, textvariable=self.values_file,
                                    width=56)
        self.values_box.pack(side="left", padx=4)
        self.values_box.bind("<Return>", lambda _: self.values_file_changed())
        self.values_box.bind("<FocusOut>", lambda _: self.values_file_changed())
        ttk.Button(self.values_row, text="Browse", command=self.browse_values_file).pack(
            side="left")
        self.values_row.grid_remove()

        self.rule_list = Sheet(self, RULE_COLUMNS, height=8)
        self.rule_list.grid(row=4, column=0, columnspan=6, sticky="nsew", pady=6)
        self.rule_list.on_select(self.rule_chosen)
        self.rowconfigure(4, weight=2)
        self.note = ttk.Label(self, text="", foreground="#555", justify="left")
        self.note.grid(row=5, column=0, columnspan=6, sticky="nw")
        wrap_within(self, [self.note])
        self.refresh_fields()

    def show(self, kind: str) -> None:
        """Only the surfaces this kind of part has. A stage has none at all."""
        tables = SURFACES.get(kind, ())
        self.table_box.configure(values=list(tables))
        if not tables:
            self.table.set("")
            self.table_box.configure(state="disabled")
            self.field_list.clear()
            self.rule_list.clear()
            self.note.configure(text=NO_STAGE_PARAMS)
            self.enable(False)
            return
        self.table_box.configure(state="normal")
        self.enable(True)
        if self.table.get() not in tables:
            self.table.set(tables[0])
        self.refresh_fields()

    def enable(self, wanted: bool) -> None:
        for widget in self.controls:
            widget.configure(state="normal" if wanted else "disabled")

    def rule_key(self) -> str:
        if self.table.get() == OWNER_SURFACE:
            return "owner_params"
        return "item_params" if self.app.kind.get() == packs.ITEM else "params"

    def load(self) -> None:
        if not self.table.get():
            return
        self.rules = list(self.app.state.get(self.rule_key()) or [])
        self.refresh_rules()
        self.show_surface()
        if self.table.get() == OWNER_SURFACE and self.owner.get():
            self.owner_changed()
        shipped = self.app.catalog.common_item_prc_in_pack(self.app.folder)
        self.values_file.set(self.app.state.get("item_common_prc")
                             or (str(shipped) if shipped else ""))

    def show_surface(self) -> None:
        """Lay the panel out for this surface: not every one has a field list."""
        table = self.table.get()
        if not table:
            self.owner_row.grid_remove()
            return
        if table == OWNER_SURFACE:
            self.owner_row.grid()
        else:
            self.owner_row.grid_remove()
        if table == "item_common":
            self.values_row.grid()
        else:
            self.values_row.grid_remove()
        self.field_list.grid()
        self.rowconfigure(1, weight=3)
        for widget in (self.field_box, self.operation_box, self.source_box):
            widget.configure(state="disabled" if table in (OWNER_SURFACE, ITEM_PRC_SURFACE)
                             else ("readonly" if widget is self.source_box else "normal"))
        for widget in (self.value_box, self.add_button):
            widget.configure(state="disabled" if table == ITEM_PRC_SURFACE else "normal")
        self.search_box.configure(state="normal")
        self.free_type.configure(
            state="normal" if table in (VL_SURFACE, OWNER_SURFACE) else "disabled")

    def refresh_fields(self) -> None:
        if not self.table.get():
            return
        self.field_list.clear()
        self.show_surface()
        self.rules = list(self.app.state.get(self.rule_key()) or [])
        self.refresh_rules()
        needle = self.search.get().strip().lower()
        wanted = self.source.get()
        rows = self.surface_rows()
        self.sources = sorted({source for _, _, source in rows if source})
        self.source_box.configure(values=[ANY_FILE] + self.sources)
        if wanted != ANY_FILE and wanted not in self.sources:
            self.source.set(ANY_FILE)
            wanted = ANY_FILE
        self.source_box.configure(
            state="readonly" if len(self.sources) > 1 else "disabled")
        self.rows = [(field, kind, source) for field, kind, source in rows
                     if needle in field.lower()
                     and (wanted == ANY_FILE or source == wanted)]
        self.fields = [(field, kind) for field, kind, _ in self.rows]
        table = self.table.get()
        columns = ["name", "type"]
        if table == OWNER_SURFACE:
            columns += ["offset", "value", "word"]
        elif self.extra:
            columns += ["value", "word"]
            if any(vanilla for _, _, vanilla, _ in self.extra.values()):
                columns.append("vanilla")
        if len(self.sources) > 1:
            columns.append("file")
        self.field_list.show_columns(columns)
        for field, kind, source in self.rows[:400]:
            cell = {"name": field, "type": kind,
                    "file": "" if not source else
                    (source if source.endswith(".prc") else source + ".prc")}
            changed = False
            if table == OWNER_SURFACE:
                offset, value, bits, _ = self.owner_info.get(field, (0, "", "", ""))
                cell.update(offset="+%x" % offset, value=value, word=bits)
            elif field in self.extra:
                value, bits, vanilla, changed = self.extra[field]
                cell.update(value=value, word=bits, vanilla=vanilla)
            self.field_list.append(cell, changed)
        shown = min(len(self.rows), 400)
        self.note.configure(text=self._note(shown))

    def values_file_changed(self) -> None:
        path = self.values_file.get().strip()
        if (self.app.state.get("item_common_prc") or "") != path:
            self.app.state["item_common_prc"] = path
            self.app.save_state()
        self.refresh_fields()

    def browse_values_file(self) -> None:
        chosen = filedialog.askopenfilename(
            title="item/common/param/param.prc, as extracted from the game",
            filetypes=[("param files", "*.prc"), ("all files", "*.*")])
        if chosen:
            self.values_file.set(chosen)
            self.values_file_changed()

    def base_kind(self) -> int | None:
        section = self.app.state
        try:
            return int(section.get("base_kind"))
        except (TypeError, ValueError):
            return None

    def own_prc_rows(self, files, defaults: dict) -> list[tuple[str, str, str]]:
        """Names, values and words out of the pack's own prc files, each value
        beside the compiled default when the base fighter's table knows the name."""
        rows: list[tuple[str, str, str]] = []
        for path in files:
            values = self.app.catalog.prc_values(path)
            for name, kind, source in self.app.catalog.prc_rows(path):
                rows.append((name, kind, source))
                read = values.get(name)
                if read is None or read[1] is None:
                    continue
                text = prc.shown(kind, read[1], self.app.catalog.labels())
                default = defaults.get(name, "")
                changed = False
                if default:
                    changed = not (abs(float(default) - float(read[1]))
                                   <= 1e-6 * max(1.0, abs(float(read[1])))
                                   if kind == "f32" else str(default) == text)
                self.extra[name] = (text, prc.word(kind, read[1]), default, changed)
        return rows

    def common_rows(self) -> list[tuple[str, str, str]]:
        """The 235 common fields, with the base item's own row when the file is here."""
        rows = self.app.catalog.param_rows("item_common")
        path = self.values_file.get().strip()
        base = self.base_kind()
        if not path or base is None:
            return rows
        values = self.app.catalog.prc_row_values(path, base)
        names = dict(self.app.catalog.labels())
        names.update(self.app.catalog.item_label_names())
        for field, kind, _ in rows:
            read = values.get(field)
            if read is None and field.startswith("unk_"):
                read = values.get("0x" + field[4:])
            if read is None or read[1] is None:
                continue
            self.extra[field] = (prc.shown(read[0], read[1], names),
                                 prc.word(read[0], read[1]), "", False)
        return rows

    def owner_kind(self) -> tuple[str, int | None]:
        return split_choice(self.owner.get())

    def owner_changed(self) -> None:
        """A new owner: its vl.prc is the pack's copy, or the one remembered for it."""
        name, _ = self.owner_kind()
        remembered = (self.app.state.get("owner_prc_files") or {}).get(name, "")
        shipped = self.app.catalog.owner_prc_in_pack(self.app.folder, name)
        self.owner_prc.set(str(shipped) if shipped else remembered)
        self.refresh_fields()

    def owner_prc_changed(self) -> None:
        name, _ = self.owner_kind()
        if not name:
            return
        files = dict(self.app.state.get("owner_prc_files") or {})
        path = self.owner_prc.get().strip()
        if path:
            files[name] = path
        else:
            files.pop(name, None)
        if files != (self.app.state.get("owner_prc_files") or {}):
            self.app.state["owner_prc_files"] = files
            self.app.save_state()
        self.refresh_fields()

    def browse_owner_prc(self) -> None:
        name, _ = self.owner_kind()
        chosen = filedialog.askopenfilename(
            title="The vl.prc of %s, as extracted from the game" % (name or "the owner"),
            filetypes=[("param files", "*.prc"), ("all files", "*.*")])
        if chosen:
            self.owner_prc.set(chosen)
            self.owner_prc_changed()

    def owner_rows(self) -> list[tuple[str, str, str]]:
        """The inline words of the owner's payload, each with the value it holds:
        the prc's own when one is at hand, else the default compiled into the game."""
        self.owner_info = {}
        name, number = self.owner_kind()
        if number is None:
            return []
        path = self.owner_prc.get().strip()
        values = self.app.catalog.prc_values(path) if path else {}
        rows: list[tuple[str, str, str]] = []
        for field, kind, offset, default in self.app.catalog.owner_params(number):
            read = values.get(field)
            if read is not None and read[1] is not None:
                value = read[1]
                text = ("%.9g" % value) if kind == "f32" else str(int(value))
                source = "prc"
            else:
                text, source = default, "default" if default else ""
            bits = prc.word(kind, text) if text else ""
            self.owner_info[field] = (offset, text, bits, source)
            rows.append((field, kind, ""))
        return rows

    def surface_rows(self) -> list[tuple[str, str, str]]:
        """The field list for the current surface, from a table or the pack's own prc."""
        self.extra = {}
        table = self.table.get()
        if table == OWNER_SURFACE:
            return self.owner_rows()
        if table == "item_common":
            return self.common_rows()
        if table == ITEM_PRC_SURFACE:
            resource = self.app.part(packs.ITEM).get("resource_name", "")
            return self.own_prc_rows(
                self.app.catalog.pack_item_prc_files(self.app.folder, resource), {})
        if table != VL_SURFACE:
            return self.app.catalog.param_rows(table)
        resource = self.app.part(packs.FIGHTER).get("resource_name", "")
        base = self.base_kind()
        defaults = self.app.catalog.owner_defaults(base) if base is not None else {}
        return self.own_prc_rows(self.app.catalog.pack_prc_files(self.app.folder, resource),
                                 defaults)

    def _note(self, shown: int) -> str:
        table = self.table.get()
        if table == VL_SURFACE:
            resource = self.app.part(packs.FIGHTER).get("resource_name", "?")
            if not self.rows:
                return ("No prc files under fighter/%s/param. Type the param name "
                        "(param/field for a nested one) and tick Whole number for an "
                        "integer." % resource)
            changed = sum(1 for value in self.extra.values() if value[3])
            return ("%d of %d params from your prc files under fighter/%s/param, with "
                    "the value each holds. Click one, set a value, Add. A slash means "
                    "param/field. With a plugin that keeps its ParamConfig code these "
                    "are param_config::update_* calls on the Rust tab, with the clone's "
                    "kind; without one they are .param(..) on the Manifest, or "
                    "fighter.toml's [params]. %s"
                    % (shown, len(self.rows), resource,
                       "%d value(s) differ from the game's default (Vanilla column) "
                       "and are green." % changed if changed else
                       "Vanilla is the game's default for the base fighter; a value "
                       "that differs is green."))
        if table == ITEM_PRC_SURFACE:
            resource = self.app.part(packs.ITEM).get("resource_name", "?")
            if self.rows:
                return ("%d of %d params from your files under item/%s/param, with the "
                        "value each holds. These files load as they are: change values "
                        "in the file." % (shown, len(self.rows), resource))
            return ("No prc files under item/%s/param. Your item uses its base's file "
                    "until it ships one." % resource)
        if table == OWNER_SURFACE:
            name, number = self.owner_kind()
            if number is None:
                return ("Some items read a fighter's params instead of their own "
                        "(Steve's blocks read Steve's). Pick the fighter to see its "
                        "values by name.")
            if not self.rows:
                return "%s has no values an item can read this way." % name
            sources = {info[3] for info in self.owner_info.values()}
            if "prc" in sources:
                where = "Values read from %s." % self.owner_prc.get().strip()
            else:
                where = ("Values are the game's defaults. Put %s's vl.prc, extracted "
                         "from the game, in the box to see the real file." % name)
            return ("%d of %d values from %s. Click one, change the value, Add. Change "
                    "values that work together as a set (life with auto_damage). %s"
                    % (shown, len(self.rows), name, where))
        if table == "param_thrown":
            return ("Where a held or thrown body sits: %d rule(s). A whole vector takes "
                    "Mul only; a single component takes Set or Mul. offset* is your "
                    "clone holding, held_offset* is your clone being held. Read by the "
                    "game past ParamConfig: .param(\"param_thrown.<key>\", ..) on the "
                    "Manifest or fighter.toml's [params], never ParamConfig." % shown)
        if table == "item_common":
            path = self.values_file.get().strip()
            if self.extra:
                where = "Values are the base item's, read from %s." % path
            elif path:
                where = ("Nothing read from %s: it needs item/common/param/param.prc "
                         "and a base item." % path)
            else:
                where = ("Put item/common/param/param.prc, extracted from the game, in "
                         "the box to see the base item's values.")
            return ("%d of %d fields. Floats take a number, bools 0 or 1, kind fields a "
                    "label (item_shield_kind_lost), name fields a bone or motion name. "
                    "%s" % (shown, len(self.fields), where))
        if table == "common":
            return ("%d of %d fields from the six per-fighter files (common, item, "
                    "etc, power_up, effect, sound); the File box picks one. Change "
                    "values that work together as a set (shield_max with shield_reset). "
                    "Read by the game past ParamConfig: .param(\"common.<field>\", ..) on "
                    "the Manifest or fighter.toml's [params], never ParamConfig."
                    % (shown, len(self.rows)))
        if table == "param_motion":
            return ("%d of %d fields: dodge, roll and air dodge timings. Read by the "
                    "game past ParamConfig: .param(\"param_motion.<field>\", ..) on the "
                    "Manifest or fighter.toml's [params], never ParamConfig."
                    % (shown, len(self.fields)))
        return ("%d of %d fields. A rule applies to every costume. The game reads these "
                "past ParamConfig (FighterParamAccessor2 and straight from the row), so "
                "they are .param(..) on the Manifest or fighter.toml's [params]; the "
                "engine applies them and pushes them to ParamConfig too."
                % (shown, len(self.fields)))

    def choose_field(self, _event=None) -> None:
        selection = self.field_list.selection()
        if not selection or selection[0] >= len(self.fields):
            return
        field, kind = self.fields[selection[0]]
        self.field.set(field)
        if self.table.get() == OWNER_SURFACE:
            offset, value, _, _ = self.owner_info.get(field, (0, "", "", ""))
            self.offset.set("%#x" % offset)
            if value:
                self.value.set(value)
        if self.table.get() in (VL_SURFACE, OWNER_SURFACE):
            self.integer.set(kind in ("i32", "u32", "i8", "u8", "i16", "u16", "bool"))
        if field in self.extra and kind in PREFILL_TYPES and self.extra[field][0]:
            self.value.set(self.extra[field][0])
        if is_label_field(kind):
            self.value_box.configure(values=self.app.catalog.labels_for(field))
        elif kind == "bool":
            self.value_box.configure(values=("0", "1"))
        elif is_name_field(kind):
            self.value_box.configure(values=("top", "have", "throw", "rot"))
        else:
            self.value_box.configure(values=())

    def _type_of(self, field: str) -> str:
        for known, kind, _ in self.surface_rows():
            if known == field:
                return kind
        return ""

    def _style(self, field: str) -> str:
        """How a field is written: a float, a whole number, a label or a name."""
        for known, kind in self.app.catalog.param_fields(self.table.get()):
            if known == field:
                if is_float_field(kind):
                    return "float"
                if is_name_field(kind):
                    return "hash"
                if is_label_field(kind):
                    return "label"
                return "int"
        return "float"

    def add_rule(self) -> None:
        table = self.table.get()
        field = self.field.get().strip()
        value = self.value.get().strip()
        if table == ITEM_PRC_SURFACE:
            messagebox.showinfo(TITLE, "These files load as they are. Change the value "
                                       "in the file.")
            return
        if table == OWNER_SURFACE:
            name, number = split_choice(self.owner.get())
            if number is None:
                messagebox.showinfo(TITLE, "Pick the fighter that owns the parameters.")
                return
            try:
                offset = int(self.offset.get().strip(), 0)
            except ValueError:
                messagebox.showinfo(TITLE, "Click a value in the list, or type its "
                                           "offset (such as 0x518).")
                return
            if offset % 4 or offset >= 0x4000:
                messagebox.showinfo(TITLE, "The offset has to be a multiple of 4 below "
                                           "0x4000.")
                return
            known = {info[0]: path for path, info in self.owner_info.items()}
            types = {at: kind for _, kind, at, _ in self.app.catalog.owner_params(number)}
            rule = {"owner_kind": number, "owner": name, "offset": "%#x" % offset,
                    "value": value, "integer": bool(self.integer.get())}
            if offset in known:
                rule["field"] = known[offset]
                rule["integer"] = types.get(offset, "f32") != "f32"
            self.rules.append(rule)
            self.refresh_rules()
            self.store()
            return
        if not field:
            return
        if table == VL_SURFACE:
            if self._type_of(field) in ("list", "struct"):
                messagebox.showinfo(TITLE, "%s holds other params. Pick one of its "
                                           "fields, such as %s/<field>." % (field, field))
                return
            param, _, subparam = field.partition("/")
            self.rules.append({"table": param.strip(), "field": subparam.strip(),
                               "value": value, "op": self.operation.get(),
                               "integer": bool(self.integer.get())})
            self.refresh_rules()
            self.store()
            return
        style = self._style(field)
        if self._type_of(field) == "vector" and self.operation.get() != "Mul":
            self.operation.set("Mul")
            self.app.log("a whole hold offset vector takes Mul only, so %s is a "
                         "multiply" % field)
        if self.app.kind.get() == packs.ITEM:
            if style == "label" and value.replace("-", "").isdigit():
                style = "int"
            self.rules.append({"field": field, "value": value, "style": style})
        else:
            self.rules.append({"table": self.table.get(), "field": field,
                               "value": value, "op": self.operation.get(),
                               "integer": style in ("int", "label")})
        self.refresh_rules()
        self.store()

    def rule_chosen(self, _event=None) -> None:
        selection = self.rule_list.selection()
        if selection:
            self.rule_picked = selection[0]

    def remove_rule(self) -> None:
        chosen = sorted(self.rule_list.selection(), reverse=True)
        if not chosen:
            if self.rule_picked is None or self.rule_picked >= len(self.rules):
                messagebox.showinfo(TITLE, "Click the rule to remove first.")
                return
            chosen = [self.rule_picked]
        for index in chosen:
            del self.rules[index]
        self.rule_picked = None
        self.refresh_rules()
        self.store()

    def refresh_rules(self) -> None:
        self.rule_list.clear()
        for rule in self.rules:
            if "offset" in rule:
                self.rule_list.append({
                    "where": rule.get("owner", rule.get("owner_kind")),
                    "field": rule.get("field") or "word at +%s" % rule["offset"],
                    "op": "Set", "value": rule["value"],
                    "note": "+%s%s" % (rule["offset"].replace("0x", ""),
                                       ", whole number" if rule.get("integer") else "")})
            elif "style" in rule:
                self.rule_list.append({"where": "item_common", "field": rule["field"],
                                       "op": "Set", "value": rule["value"],
                                       "note": rule["style"]})
            else:
                self.rule_list.append({"where": rule.get("table"), "field": rule["field"],
                                       "op": rule.get("op"), "value": rule["value"],
                                       "note": "whole number" if rule.get("integer")
                                       else ""})

    def store(self) -> None:
        self.app.state[self.rule_key()] = self.rules
        self.app.rust.refresh()


class LintPanel(ttk.Frame):
    """The linters' findings, filtered by level."""

    def __init__(self, parent: tk.Misc, app: Workbench):
        super().__init__(parent, padding=10)
        self.app = app
        self.findings: list[tuple[str, str]] = []
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Button(bar, text="Lint this pack", command=self.run).pack(side="left")
        self.filters = {}
        for level in LEVELS:
            variable = tk.BooleanVar(value=True)
            self.filters[level] = variable
            ttk.Checkbutton(bar, text=level, variable=variable,
                            command=self.refresh).pack(side="left", padx=4)
        self.count = ttk.Label(bar, text="")
        self.count.pack(side="left", padx=12)

        self.tree = ttk.Treeview(self, columns=("level", "message"), show="headings")
        self.tree.heading("level", text="Level")
        self.tree.heading("message", text="Finding")
        self.tree.column("level", width=70, stretch=False)
        self.tree.column("message", width=900)
        self.tree.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

    def clear(self) -> None:
        self.findings = []
        self.refresh()

    def run(self) -> None:
        """Every linter this pack needs, so a combined pack is checked whole."""
        if not self.app.require_folder():
            return
        present = self.app.present or [self.app.kind.get()]
        wanted = []
        if any(kind in present for kind in (packs.FIGHTER, packs.ITEM)):
            wanted.append(("lint_clone_pack", False))
        if packs.STAGE in present:
            wanted.append(("lint_stage_pack", True))
        index = str(self.app.catalog.arc_index)
        self.findings = []
        for module_name, is_stage in wanted:
            module = import_tool(module_name)
            if module is None:
                self.app.log("%s is not beside this GUI, so that half is unchecked"
                             % module_name)
                continue
            try:
                found = (module.lint(str(self.app.folder), index, False) if is_stage
                         else module.lint(str(self.app.folder), index))
            except Exception:
                self.app.log(traceback.format_exc())
                continue
            self.findings += list(found)
            errors = sum(1 for level, _ in found if level == "ERROR")
            self.app.log("%s: %d finding(s), %d error(s)"
                         % (module_name, len(found), errors))
        self.refresh()

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        counts = {level: 0 for level in LEVELS}
        for level, message in self.findings:
            counts[level] = counts.get(level, 0) + 1
            if self.filters.get(level) is not None and not self.filters[level].get():
                continue
            self.tree.insert("", "end", values=(level, message))
        self.count.configure(text="  ".join("%s %d" % (level, counts.get(level, 0))
                                            for level in LEVELS))


OPTIMIZE_COLUMNS = (
    ("target", "Costume file", 380, "w"),
    ("source", "Takes the bytes of", 300, "w"),
    ("size", "Size", 80, "e"),
)


class OptimizePanel(ttk.Frame):
    """The pack made smaller: a costume's file that equals a lower costume's is
    taken out and config.json points its name at the lower costume's file."""

    def __init__(self, parent: tk.Misc, app: Workbench):
        super().__init__(parent, padding=10)
        self.app = app
        self.found: dict | None = None
        self.planned: dict | None = None
        self.kept: list = []
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Button(bar, text="Scan", command=self.scan).pack(side="left")
        self.apply_button = ttk.Button(bar, text="Apply", command=self.apply, state="disabled")
        self.apply_button.pack(side="left", padx=4)
        self.summary = ttk.Label(self, text="", justify="left")
        self.summary.grid(row=1, column=0, sticky="w", pady=(8, 4))
        self.sheet = Sheet(self, OPTIMIZE_COLUMNS, height=12)
        self.sheet.grid(row=2, column=0, sticky="nsew")
        self.note = ttk.Label(self, foreground="#555", justify="left", text=(
            "A costume's file with the same bytes as a lower costume's twin (model, "
            "motion, camera, sound bank, Kirby hat) ships once: the copy leaves the pack "
            "(kept in backups) and config.json's share-to-added points its name at the "
            "lower costume's file, which the game then loads for both. .marker files, "
            "manifests and the plugin are never touched; a name config.json already "
            "aliases is left as it is. Empty folders go too."))
        self.note.grid(row=3, column=0, sticky="w", pady=(6, 0))
        wrap_within(self, [self.summary, self.note])

    def clear(self) -> None:
        self.found = self.planned = None
        self.kept = []
        self.sheet.clear()
        self.summary.configure(text="Scan to see what the pack ships twice.")
        self.apply_button.configure(state="disabled")

    def config(self) -> dict:
        path = self.app.folder / "config.json" if self.app.folder else None
        if path is None or not path.is_file():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def scan(self) -> None:
        if not self.app.require_folder():
            return
        self.sheet.clear()
        self.found = optimize.scan(self.app.folder)
        self.planned, self.kept, notes = optimize.plan_config(self.config(), self.found["duplicates"])
        for note in notes:
            self.app.log("    optimize: " + note)
        total = sum(size for _, _, size in self.kept)
        for target, source, size in self.kept:
            self.sheet.append({"target": target, "source": source, "size": optimize.human(size)})
        self.summary.configure(text=(
            "%d of %d costume-owned files are copies of a lower costume's: %s to take out"
            ", %d empty folder(s)." % (len(self.kept), self.found["looked"], optimize.human(total),
                                        len(self.found["empty"]))))
        self.apply_button.configure(state="normal" if self.kept or self.found["empty"] else "disabled")
        self.app.log("optimize: %d duplicate(s) in %d costume-owned file(s), %s; %d empty folder(s)"
                     % (len(self.kept), self.found["looked"], optimize.human(total),
                        len(self.found["empty"])))

    def apply(self, confirm=None) -> bool:
        if self.found is None or self.planned is None:
            return False
        if confirm is None:
            confirm = lambda: messagebox.askyesno(
                TITLE, "Take %d file(s) out of the pack and share their names through "
                       "config.json? Each is copied to backups first."
                       % len(self.kept))
        if not confirm():
            return False
        for line in optimize.apply(self.app.folder, self.planned, self.kept, self.found["empty"]):
            self.app.log("    " + line)
        self.app.log_kept()
        self.app.files.refresh()
        self.app.lint.clear()
        self.scan()
        return True


class RustPanel(ttk.Frame):
    """The plugin source the Identity and Parameters tabs describe."""

    def __init__(self, parent: tk.Misc, app: Workbench):
        super().__init__(parent, padding=10)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(bar, text="Copy", command=self.copy).pack(side="left", padx=4)
        ttk.Button(bar, text="Save as lib.rs",
                   command=self.save).pack(side="left")
        self.text = tk.Text(self, wrap="none", height=24)
        self.text.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        across = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        across.grid(row=2, column=0, sticky="ew")
        self.text.configure(yscrollcommand=scroll.set, xscrollcommand=across.set)

    def parts(self) -> list[str]:
        """What the pack ships, plus the part being worked on and any part described."""
        wanted = set(self.app.present) | {self.app.kind.get()}
        wanted |= {kind for kind, sections in self.app.sections.items() if any(sections)}
        return [kind for kind in packs.KINDS if kind in wanted]

    def described(self, kind: str) -> list[dict]:
        """The parts of a kind with enough in them to emit for."""
        return [part for part in self.app.sections[kind]
                if part.get("resource_name") or part.get("base_kind") is not None]

    def source(self) -> str:
        """One file for every part of the pack that takes code."""
        parts = self.parts()
        fighters = self.described(packs.FIGHTER) if packs.FIGHTER in parts else []
        items = self.described(packs.ITEM) if packs.ITEM in parts else []
        text = emit.plugin_source(fighters, items)
        if text:
            return text
        if packs.STAGE in parts:
            return ("A stage needs no code: stage.toml and config.json are enough. "
                    "Add a plugin.nro only for behaviour stage.toml cannot describe.\n")
        return "Nothing to emit yet.\n"

    def refresh(self) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("end", self.source())

    def copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.source())
        self.app.log("copied %d character(s) to the clipboard" % len(self.source()))

    def save(self) -> None:
        if not self.app.require_folder():
            return
        path = self.app.folder / "lib.rs"
        backups.keep(path, self.app.folder)
        path.write_text(self.source(), encoding="utf-8", newline="\n")
        self.app.log("wrote %s" % path)
        self.app.log_kept()


def run(folder: str | None = None) -> int:
    """Open the window."""
    root = tk.Tk()
    width = min(1060, root.winfo_screenwidth() - 40)
    height = min(820, root.winfo_screenheight() - 100)
    root.geometry("%dx%d" % (width, height))
    root.minsize(720, 480)
    Workbench(root, folder)
    root.mainloop()
    return 0
