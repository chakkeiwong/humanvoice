"""Load the retained, reviewed program without rewriting paid evidence."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE.parent / 'durable-session-settings-20261114'))

import durable_program as previous  # noqa: F401
