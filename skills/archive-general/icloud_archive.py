#!/usr/bin/env python3
"""Legacy command name for Archive General."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name("archive.py")), run_name="__main__")
