"""Import the tested session continuation without modifying retained dependencies."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'writer-session-binding-repair-20261113'))
sys.dont_write_bytecode = True

import session_program as previous  # noqa: F401 -- initialize retained modules
