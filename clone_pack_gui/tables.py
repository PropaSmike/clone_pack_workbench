#!/usr/bin/env python3
"""A list of fighter.toml tables edited one row at a time: the fields, Add, Remove and the list."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import gimmicks


class Field:
    """One input of a row: an entry, a choice or a check that writes a fixed value."""

    def __init__(self, key: str, label: str, width: int = 10, widget: str = "entry",
                 choices=(), checked: str = "true"):
        self.key = key
        self.label = label
        self.width = width
        self.widget = widget
        self.choices = tuple(choices)
        self.checked = checked
        self.variable: tk.Variable = tk.BooleanVar() if widget == "check" else tk.StringVar()
        self.box: ttk.Combobox | None = None


class TableEditor(ttk.LabelFrame):
    """Add puts the fields in the list, replacing the row with the same identity; clicking a row
    puts it back in the fields."""

    def __init__(self, parent, title: str, table: str, fields: list[Field], describe=None,
                 identity=None, on_change=None, per_row: int = 4, height: int = 3, prepare=None,
                 hint: str = ""):
        super().__init__(parent, text=title, padding=6)
        self.table = table
        self.fields = fields
        self.describe = describe or self.default_describe
        self.identity = identity
        self.on_change = on_change or (lambda: None)
        self.prepare = prepare
        self.rows: list[dict] = []
        self.picked: int | None = None
        grid = ttk.Frame(self)
        grid.grid(row=0, column=0, columnspan=2, sticky="w")
        for index, field in enumerate(fields):
            row, column = divmod(index, per_row)
            if field.widget == "check":
                ttk.Checkbutton(grid, text=field.label, variable=field.variable).grid(
                    row=row, column=column * 2, columnspan=2, sticky="w", padx=(0, 10), pady=2)
                continue
            ttk.Label(grid, text=field.label).grid(row=row, column=column * 2, sticky="w", pady=2)
            if field.widget == "choice":
                field.box = ttk.Combobox(grid, textvariable=field.variable, width=field.width,
                                         values=field.choices)
                field.box.grid(row=row, column=column * 2 + 1, sticky="w", padx=(4, 10), pady=2)
            else:
                ttk.Entry(grid, textvariable=field.variable, width=field.width).grid(
                    row=row, column=column * 2 + 1, sticky="w", padx=(4, 10), pady=2)
        buttons = ttk.Frame(self)
        buttons.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(buttons, text="Add", command=self.add).pack(side="left")
        ttk.Button(buttons, text="Remove", command=self.remove).pack(side="left", padx=4)
        self.listbox = tk.Listbox(self, height=height, exportselection=False)
        self.listbox.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.listbox.bind("<<ListboxSelect>>", self.chosen)
        self.hint = ttk.Label(self, text=hint, foreground="#555", justify="left")
        if hint:
            self.hint.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.columnconfigure(1, weight=1)

    def field(self, key: str) -> Field | None:
        return next((field for field in self.fields if field.key == key), None)

    def set_choices(self, key: str, choices) -> None:
        field = self.field(key)
        if field is not None and field.box is not None:
            field.choices = tuple(choices)
            field.box.configure(values=field.choices)

    def read(self) -> dict:
        """The fields as a row of TOML text; blank fields and clear checks are left out."""
        row: dict = {}
        for field in self.fields:
            if field.widget == "check":
                if field.variable.get():
                    row[field.key] = field.checked
                continue
            text = str(field.variable.get()).strip()
            if not text or field.key in row:
                continue
            row[field.key] = text if field.key in gimmicks.PLAIN_KEYS else gimmicks.to_toml(
                self.table, field.key, text)
        return row

    def fill(self, row: dict) -> None:
        for field in self.fields:
            value = row.get(field.key)
            if field.widget == "check":
                field.variable.set(value == field.checked)
                continue
            if value is None or any(other.widget == "check" and other.key == field.key
                                    and value == other.checked for other in self.fields):
                field.variable.set("")
            else:
                field.variable.set(value if field.key in gimmicks.PLAIN_KEYS else gimmicks.display(value))

    def add(self) -> None:
        row = self.read()
        if self.prepare is not None:
            row = self.prepare(row, self.rows)
            if isinstance(row, str):
                messagebox.showinfo("Clone Pack Workbench", row)
                return
        problem = gimmicks.row_problem(self.table, row)
        if problem:
            messagebox.showinfo("Clone Pack Workbench", problem)
            return
        key = self.identity(row) if self.identity else None
        for index, known in enumerate(self.rows):
            if key is not None and self.identity(known) == key:
                self.rows[index] = row
                break
        else:
            self.rows.append(row)
        self.refresh()
        self.on_change()

    def remove(self) -> None:
        selection = self.listbox.curselection()
        index = selection[0] if selection else self.picked
        if index is None or index >= len(self.rows):
            messagebox.showinfo("Clone Pack Workbench", "Click the row to remove.")
            return
        self.rows.pop(index)
        self.picked = None
        self.refresh()
        self.on_change()

    def chosen(self, _event=None) -> None:
        selection = self.listbox.curselection()
        if selection and selection[0] < len(self.rows):
            self.picked = selection[0]
            self.fill(self.rows[selection[0]])

    def set_rows(self, rows) -> None:
        self.rows = [dict(row) for row in rows or []]
        self.picked = None
        self.refresh()

    def refresh(self) -> None:
        self.listbox.delete(0, "end")
        for row in self.rows:
            self.listbox.insert("end", self.describe(row))

    @staticmethod
    def default_describe(row: dict) -> str:
        return ", ".join("%s %s" % (key, gimmicks.display(value)) for key, value in row.items())
