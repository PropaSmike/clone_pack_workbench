#!/usr/bin/env python3
"""Run the workbench.

    python clone_pack_gui
    python clone_pack_gui "C:/.../ultimate/mods/Clone Engine - Wawa"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clone_pack_gui.app import run  # noqa: E402


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    return run(argv[0] if argv else None)


if __name__ == "__main__":
    raise SystemExit(main())
