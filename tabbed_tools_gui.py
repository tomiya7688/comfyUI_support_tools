#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Central Kadoka Tools GUI launcher.

Implementation is split into one-responsibility modules under ``scripts``.
"""

from pathlib import Path
import sys


SD_ROOT = Path(__file__).resolve().parent
if str(SD_ROOT) not in sys.path:
    sys.path.insert(0, str(SD_ROOT))

from scripts.app import main


def _run() -> None:
    if "--smoke-test" in sys.argv:
        print("KadokaTools import smoke test: OK")
        return
    main()


if __name__ == "__main__":
    _run()
