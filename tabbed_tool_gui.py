#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility launcher for the historical singular file name."""

from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).with_name("tabbed_tools_gui.py")), run_name="__main__")
