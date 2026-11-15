#!/usr/bin/env python3
"""Light and dark: the ttk styles, the classic Tk widgets, the panels' own colours and the
Windows title bar. Light is the platform's own theme, untouched; dark is clam recoloured.
System follows Windows' app setting, also while the window is open."""

from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

import tkinter as tk
from tkinter import ttk

MODES = ("system", "light", "dark")
LABELS = {"system": "System", "light": "Light", "dark": "Dark"}
LIGHT = {"hint": "#555555", "warn": "#aa3333", "error": "#b00020", "changed": "#1a6e2e",
         "code": "#eef0f3", "rule": "#c8ccd2", "link": "#1a5fb4"}
DARK = {"background": "#202225", "surface": "#2b2d31", "field": "#18191c", "border": "#3d4046",
        "foreground": "#e3e5e8", "muted": "#a3a8ae", "disabled": "#6d7178",
        "select": "#2d5b8c", "select_foreground": "#ffffff", "accent": "#5b9be0",
        "button": "#35383d", "button_active": "#41454b", "button_pressed": "#2d5b8c",
        "heading": "#2f3237", "hint": "#9ea4ab", "warn": "#f2a65e", "error": "#ff7b72",
        "changed": "#6fd68f", "code": "#2b2d31", "rule": "#45484e", "link": "#79b8ff"}
NAMED_STYLES = (("Hint.TLabel", "hint"), ("Warn.TLabel", "warn"), ("Error.TLabel", "error"))
SETTINGS_NAME = "settings.json"
SYSTEM_POLL_MS = 4000
DWMWA_USE_IMMERSIVE_DARK_MODE = (20, 19)
SWP_FRAME_ONLY = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020

_state: dict = {"mode": "system", "dark": False, "light_theme": None, "light_tk": None,
                "listeners": []}


def settings_path() -> Path:
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "Clone Pack Workbench" / SETTINGS_NAME
    return Path.home() / ".config" / "clone_pack_workbench" / SETTINGS_NAME


def load_mode() -> str:
    try:
        mode = json.loads(settings_path().read_text(encoding="utf-8")).get("theme")
    except (OSError, ValueError, AttributeError):
        mode = None
    return mode if mode in MODES else "system"


def save_mode(mode: str) -> None:
    path = settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data["theme"] = mode
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def system_is_dark() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def mode() -> str:
    return _state["mode"]


def is_dark() -> bool:
    return _state["dark"]


def color(name: str) -> str:
    return (DARK if _state["dark"] else LIGHT)[name]


def watch(callback) -> None:
    """Call this after every switch, for colours a widget keeps itself (tags, drawn lines)."""
    _state["listeners"].append(callback)


def _tk_defaults(root: tk.Misc) -> dict:
    text, listbox, frame = tk.Text(root), tk.Listbox(root), tk.Frame(root)
    values = {"text_background": text.cget("background"), "text_foreground": text.cget("foreground"),
              "select": text.cget("selectbackground"), "select_foreground": text.cget("selectforeground"),
              "insert": text.cget("insertbackground"), "list_background": listbox.cget("background"),
              "list_foreground": listbox.cget("foreground"),
              "list_select": listbox.cget("selectbackground"),
              "list_select_foreground": listbox.cget("selectforeground"),
              "window": frame.cget("background")}
    for widget in (text, listbox, frame):
        widget.destroy()
    return values


def _tk_dark() -> dict:
    p = DARK
    return {"text_background": p["field"], "text_foreground": p["foreground"], "select": p["select"],
            "select_foreground": p["select_foreground"], "insert": p["foreground"],
            "list_background": p["field"], "list_foreground": p["foreground"],
            "list_select": p["select"], "list_select_foreground": p["select_foreground"],
            "window": p["background"]}


def _dress_clam(style: ttk.Style) -> None:
    p = DARK
    style.configure(".", background=p["background"], foreground=p["foreground"],
                    bordercolor=p["border"], darkcolor=p["background"], lightcolor=p["surface"],
                    troughcolor=p["field"], selectbackground=p["select"],
                    selectforeground=p["select_foreground"], fieldbackground=p["field"],
                    insertcolor=p["foreground"], arrowcolor=p["foreground"], focuscolor=p["accent"])
    style.map(".", background=[("disabled", p["background"]), ("active", p["button_active"])],
              foreground=[("disabled", p["disabled"])],
              selectbackground=[("!focus", p["select"])],
              selectforeground=[("!focus", p["select_foreground"])])
    style.configure("TFrame", background=p["background"])
    style.configure("TLabel", background=p["background"], foreground=p["foreground"])
    style.configure("TButton", background=p["button"], bordercolor=p["border"],
                    lightcolor=p["button"], darkcolor=p["button"], padding=(8, 3))
    style.map("TButton",
              background=[("disabled", p["background"]), ("pressed", p["button_pressed"]),
                          ("active", p["button_active"])],
              lightcolor=[("pressed", p["button_pressed"]), ("active", p["button_active"])],
              darkcolor=[("pressed", p["button_pressed"]), ("active", p["button_active"])],
              foreground=[("disabled", p["disabled"])])
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=p["background"], foreground=p["foreground"],
                        indicatorbackground=p["field"], indicatorforeground=p["foreground"],
                        upperbordercolor=p["border"], lowerbordercolor=p["border"])
        style.map(name, background=[("active", p["background"])],
                  indicatorbackground=[("pressed", p["surface"]), ("disabled", p["background"])],
                  foreground=[("disabled", p["disabled"])])
    style.configure("TEntry", fieldbackground=p["field"], foreground=p["foreground"],
                    insertcolor=p["foreground"], bordercolor=p["border"],
                    lightcolor=p["field"], darkcolor=p["field"])
    style.map("TEntry", fieldbackground=[("readonly", p["surface"]), ("disabled", p["background"])],
              bordercolor=[("focus", p["accent"])], lightcolor=[("focus", p["accent"])],
              darkcolor=[("focus", p["accent"])], foreground=[("disabled", p["disabled"])])
    style.configure("TCombobox", fieldbackground=p["field"], background=p["button"],
                    foreground=p["foreground"], arrowcolor=p["foreground"], bordercolor=p["border"],
                    lightcolor=p["field"], darkcolor=p["field"], insertcolor=p["foreground"],
                    selectbackground=p["select"], selectforeground=p["select_foreground"])
    style.map("TCombobox",
              fieldbackground=[("readonly", "focus", p["select"]), ("readonly", p["field"]),
                               ("disabled", p["background"])],
              foreground=[("readonly", "focus", p["select_foreground"]), ("disabled", p["disabled"])],
              background=[("pressed", p["button_active"]), ("active", p["button_active"])],
              bordercolor=[("focus", p["accent"])], arrowcolor=[("disabled", p["disabled"])])
    style.configure("TNotebook", background=p["background"], bordercolor=p["border"],
                    lightcolor=p["background"], darkcolor=p["background"])
    style.configure("TNotebook.Tab", background=p["surface"], foreground=p["muted"],
                    bordercolor=p["border"], lightcolor=p["surface"], darkcolor=p["surface"])
    style.map("TNotebook.Tab",
              background=[("selected", p["background"]), ("active", p["button_active"])],
              foreground=[("selected", p["foreground"]), ("active", p["foreground"])],
              lightcolor=[("selected", p["background"])])
    style.configure("Treeview", background=p["field"], fieldbackground=p["field"],
                    foreground=p["foreground"], bordercolor=p["border"],
                    lightcolor=p["field"], darkcolor=p["field"])
    style.map("Treeview", background=[("selected", p["select"])],
              foreground=[("selected", p["select_foreground"])])
    style.configure("Treeview.Heading", background=p["heading"], foreground=p["foreground"],
                    bordercolor=p["border"], lightcolor=p["heading"], darkcolor=p["heading"])
    style.map("Treeview.Heading", background=[("active", p["button_active"])])
    style.configure("TLabelframe", background=p["background"], bordercolor=p["border"],
                    lightcolor=p["background"], darkcolor=p["background"])
    style.configure("TLabelframe.Label", background=p["background"], foreground=p["foreground"])
    style.configure("TScrollbar", background=p["button"], troughcolor=p["background"],
                    bordercolor=p["background"], arrowcolor=p["muted"],
                    lightcolor=p["button"], darkcolor=p["button"])
    style.map("TScrollbar", background=[("disabled", p["background"]), ("active", p["button_active"])],
              arrowcolor=[("disabled", p["disabled"])])
    style.configure("TPanedwindow", background=p["background"])
    style.configure("Sash", background=p["background"], bordercolor=p["background"],
                    lightcolor=p["border"], darkcolor=p["border"])
    style.configure("TSeparator", background=p["border"])


def _options(root: tk.Misc, colours: dict) -> None:
    for pattern, key in (("*Text.background", "text_background"), ("*Text.foreground", "text_foreground"),
                         ("*Text.selectBackground", "select"), ("*Text.selectForeground", "select_foreground"),
                         ("*Text.insertBackground", "insert"),
                         ("*Listbox.background", "list_background"),
                         ("*Listbox.foreground", "list_foreground"),
                         ("*Listbox.selectBackground", "list_select"),
                         ("*Listbox.selectForeground", "list_select_foreground"),
                         ("*Toplevel.background", "window")):
        root.option_add(pattern, colours[key], "interactive")


def _widgets(widget: tk.Misc):
    yield widget
    for child in widget.winfo_children():
        yield from _widgets(child)


def _recolour(widget: tk.Misc, colours: dict, frame: str) -> None:
    if getattr(widget, "keeps_colours", False):
        return
    kind = widget.winfo_class()
    if kind == "Text":
        widget.configure(background=colours["text_background"], foreground=colours["text_foreground"],
                         selectbackground=colours["select"], selectforeground=colours["select_foreground"],
                         insertbackground=colours["insert"])
    elif kind == "Listbox":
        _listbox(widget.tk, str(widget), colours)
    elif kind == "Canvas":
        widget.configure(background=frame)
    elif kind in ("Toplevel", "Tk"):
        widget.configure(background=colours["window"])
    elif kind == "TCombobox":
        popdown = "%s.popdown" % widget
        if widget.tk.call("winfo", "exists", popdown + ".f.l"):
            _listbox(widget.tk, popdown + ".f.l", colours)


def _listbox(interp, path: str, colours: dict) -> None:
    interp.call(path, "configure", "-background", colours["list_background"],
                "-foreground", colours["list_foreground"],
                "-selectbackground", colours["list_select"],
                "-selectforeground", colours["list_select_foreground"])


def title_bar(window: tk.Misc, dark: bool | None = None) -> None:
    """Windows draws the title bar; ask it for the dark one, and redraw the frame now."""
    if sys.platform != "win32":
        return
    dark = _state["dark"] if dark is None else dark
    try:
        window.update_idletasks()
        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = (ctypes.c_void_p,)
        user32.GetParent.restype = ctypes.c_void_p
        handle = user32.GetParent(window.winfo_id())
        if not handle:
            return
        value = ctypes.c_int(1 if dark else 0)
        set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        set_attribute.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint)
        for attribute in DWMWA_USE_IMMERSIVE_DARK_MODE:
            if set_attribute(handle, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
        user32.SetWindowPos.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_uint)
        user32.SetWindowPos(handle, None, 0, 0, 0, 0, SWP_FRAME_ONLY)
    except (AttributeError, OSError, tk.TclError):
        pass


def dress(window: tk.Misc) -> None:
    """A window made after the switch: its background and title bar."""
    try:
        window.configure(background=(_tk_dark() if _state["dark"] else _state["light_tk"] or {})
                         .get("window", window.cget("background")))
    except tk.TclError:
        pass
    window.bind("<Map>", lambda event: title_bar(window) if event.widget is window else None, add="+")
    title_bar(window)


def apply(root: tk.Misc, chosen: str) -> None:
    """Switch every widget of the window to light or dark."""
    style = ttk.Style(root)
    if _state["light_theme"] is None:
        _state["light_theme"] = style.theme_use()
        _state["light_tk"] = _tk_defaults(root)
    _state["mode"] = chosen if chosen in MODES else "system"
    dark = _state["mode"] == "dark" or (_state["mode"] == "system" and system_is_dark())
    _state["dark"] = dark
    if dark:
        style.theme_use("clam")
        _dress_clam(style)
    else:
        style.theme_use(_state["light_theme"])
    for name, key in NAMED_STYLES:
        style.configure(name, foreground=color(key))
    colours = _tk_dark() if dark else _state["light_tk"]
    _options(root, colours)
    frame = style.lookup("TFrame", "background") or colours["window"]
    for widget in _widgets(root):
        try:
            _recolour(widget, colours, frame)
        except tk.TclError:
            pass
        if widget.winfo_class() in ("Toplevel", "Tk"):
            title_bar(widget, dark)
    alive = []
    for callback in _state["listeners"]:
        try:
            callback()
            alive.append(callback)
        except tk.TclError:
            pass
    _state["listeners"] = alive


def follow_system(root: tk.Misc) -> None:
    """While the choice is System, switch when Windows does."""
    def poll() -> None:
        if _state["mode"] == "system" and system_is_dark() != _state["dark"]:
            apply(root, "system")
        root.after(SYSTEM_POLL_MS, poll)

    root.after(SYSTEM_POLL_MS, poll)
