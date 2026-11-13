"""Load the retained validation program without changing its evidence."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'writer-validation-repair-20261113'))
sys.dont_write_bytecode = True

import validation_program as previous  # noqa: F401 -- initializes retained dependencies
