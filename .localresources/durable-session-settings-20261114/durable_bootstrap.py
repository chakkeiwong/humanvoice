"""Import reviewed continuation without changing retained sources."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE.parent / 'client-reload-continuation-20261114'))

import reload_program as previous  # noqa: F401
