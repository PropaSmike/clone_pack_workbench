#!/usr/bin/env python3
"""The stick pad: click where the stick points to add that direction to a command's input."""

from __future__ import annotations

import math
import re
import tkinter as tk

NEUTRAL_THRESHOLD = 0.2
VANILLA_STICK_RANGE = ((-32.5, 32.5), (32.5, 57.5), (57.5, 122.5), (122.5, 153.5),
                       (32.5, 57.5), (57.5, 122.5), (122.5, 153.5))
MAX_STEPS = 12
STEP = 0.5
PATH_RADIUS = 0.6
LABEL_RADIUS = 0.83

BACKGROUND = "#33373b"
RING = "#d2d4d6"
DOT = "#3ab06a"
ZONE = "#454a50"
HOVER = "#4b5158"
LABEL = "#8c939a"
LABEL_HOVER = "#f0f1f2"


def direction(x: float, y: float, threshold: float = NEUTRAL_THRESHOLD,
              ranges=VANILLA_STICK_RANGE) -> int:
    """The numpad direction the engine reads for the stick at (x, y), x forward and y up."""
    if math.hypot(x, y) <= threshold:
        return 5
    angle = math.degrees(math.atan2(x, y))
    up, up_forward, forward, down_forward, up_back, back, down_back = ranges
    if up[0] <= angle <= up[1]:
        return 8
    if up_forward[0] < angle <= up_forward[1]:
        return 9
    if forward[0] < angle <= forward[1]:
        return 6
    if down_forward[0] < angle <= down_forward[1]:
        return 3
    if -up_back[1] <= angle < -up_back[0]:
        return 7
    if -back[1] <= angle < -back[0]:
        return 4
    if -down_back[1] <= angle < -down_back[0]:
        return 1
    return 2


def point(angle: float, radius: float = 1.0) -> tuple[float, float]:
    """The stick at that angle from straight up, forward positive."""
    return math.sin(math.radians(angle)) * radius, math.cos(math.radians(angle)) * radius


def zones(ranges=VANILLA_STICK_RANGE) -> list[tuple[int, float, float]]:
    """Each direction's arcs around the stick, as (digit, from, to) in degrees from straight up."""
    runs: list[tuple[int, float, float]] = []
    angle = -180.0
    while angle < 180.0:
        digit = direction(*point(angle + STEP / 2), 0.0, ranges)
        if runs and runs[-1][0] == digit:
            runs[-1] = (digit, runs[-1][1], angle + STEP)
        else:
            runs.append((digit, angle, angle + STEP))
        angle += STEP
    if len(runs) > 1 and runs[0][0] == runs[-1][0]:
        digit, start, _ = runs.pop()
        runs[0] = (digit, start - 360.0, runs[0][2])
    return runs


def centers(ranges=VANILLA_STICK_RANGE) -> dict[int, float]:
    """The middle of each direction's widest arc."""
    widest: dict[int, tuple[float, float]] = {}
    for digit, start, end in zones(ranges):
        if digit not in widest or end - start > widest[digit][1] - widest[digit][0]:
            widest[digit] = (start, end)
    return {digit: (start + end) / 2 for digit, (start, end) in widest.items()}


def extend(digits: str, digit: int) -> tuple[str, str]:
    """The input with one more direction, or the input unchanged and why."""
    if len(digits) >= MAX_STEPS:
        return digits, "an input has at most %d directions" % MAX_STEPS
    if not digits and digit == 5:
        return digits, "an input starts on a direction, not neutral"
    if digits.endswith(str(digit)):
        return digits, "the stick is already there: go through the middle to repeat it"
    return digits + str(digit), ""


def ranges_from(text: str):
    """The stick ranges typed in the panel, or the game's own when they are not seven pairs."""
    pairs = re.findall(r"\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]", text or "")
    try:
        ranges = tuple((float(low), float(high)) for low, high in pairs)
    except ValueError:
        return VANILLA_STICK_RANGE
    if len(ranges) != len(VANILLA_STICK_RANGE) or any(
            low > high or not -180.0 <= low <= 180.0 or not -180.0 <= high <= 180.0 for low, high in ranges):
        return VANILLA_STICK_RANGE
    return ranges


def threshold_from(text: str) -> float:
    """The neutral threshold typed in the panel, or the game's own."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return NEUTRAL_THRESHOLD
    return value if 0.0 <= value < 1.0 else NEUTRAL_THRESHOLD


class StickPad(tk.Canvas):
    """The stick seen from the front, the fighter facing right: a click adds the direction under it."""

    def __init__(self, master, variable: tk.StringVar, settings, note=None, size: int = 150):
        super().__init__(master, width=size, height=size, background=BACKGROUND,
                         highlightthickness=0, cursor="crosshair")
        self.variable = variable
        self.settings = settings
        self.note = note or (lambda text: None)
        self.size = size
        self.hover: int | None = None
        self.bind("<Button-1>", self.click)
        self.bind("<Button-3>", lambda _event: self.undo())
        self.bind("<Motion>", lambda event: self.set_hover(self.digit_at(event.x, event.y)))
        self.bind("<Leave>", lambda _event: self.set_hover(None))
        variable.trace_add("write", lambda *_: self.draw())
        self.draw()

    @property
    def radius(self) -> float:
        return self.size / 2 - 10

    def pixel(self, x: float, y: float) -> tuple[float, float]:
        center = self.size / 2
        return center + x * self.radius, center - y * self.radius

    def digit_at(self, px: float, py: float) -> int:
        center = self.size / 2
        threshold, ranges = self.settings()
        return direction((px - center) / self.radius, (center - py) / self.radius, threshold, ranges)

    def digits(self) -> str:
        return "".join(char for char in self.variable.get() if char in "123456789")

    def click(self, event) -> None:
        text, problem = extend(self.digits(), self.digit_at(event.x, event.y))
        self.note(problem)
        if not problem:
            self.variable.set(text)

    def undo(self) -> None:
        self.note("")
        self.variable.set(self.digits()[:-1])

    def clear(self) -> None:
        self.note("")
        self.variable.set("")

    def set_hover(self, digit: int | None) -> None:
        if digit != self.hover:
            self.hover = digit
            self.draw()

    def circle(self, radius: float, **options) -> None:
        center = self.size / 2
        self.create_oval(center - radius, center - radius, center + radius, center + radius, **options)

    def draw(self) -> None:
        self.delete("all")
        threshold, ranges = self.settings()
        runs = zones(ranges)
        middles = centers(ranges)
        center = self.size / 2
        radius = self.radius
        box = (center - radius, center - radius, center + radius, center + radius)
        for digit, start, end in runs:
            if digit == self.hover:
                self.create_arc(*box, start=90 - end, extent=end - start, fill=HOVER, outline="",
                                style=tk.PIESLICE)
        for _, start, _ in runs:
            x, y = point(start)
            self.create_line(*self.pixel(x * threshold, y * threshold), *self.pixel(x, y), fill=ZONE)
        self.circle(radius * threshold, outline=ZONE, fill=HOVER if self.hover == 5 else BACKGROUND)
        for digit, angle in middles.items():
            self.create_text(*self.pixel(*point(angle, LABEL_RADIUS)), text=str(digit),
                             fill=LABEL_HOVER if digit == self.hover else LABEL, font=("Segoe UI", 8))
        self.circle(radius, outline=RING, dash="-", width=2)
        path = [(0.0, 0.0)]
        for char in self.digits():
            digit = int(char)
            path.append((0.0, 0.0) if digit == 5 else point(middles.get(digit, 0.0), PATH_RADIUS))
        if len(path) > 1:
            points = [value for x, y in path for value in self.pixel(x, y)]
            self.create_line(*points, fill=DOT, width=2, capstyle=tk.ROUND, joinstyle=tk.ROUND)
        x, y = self.pixel(*path[-1])
        self.create_oval(x - 5, y - 5, x + 5, y + 5, fill=DOT, outline="")
