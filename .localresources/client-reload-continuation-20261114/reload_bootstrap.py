"""Load the immutable, verified HTTPS continuation."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE.parent / 'gateway-continuation-20261113'))

import gateway_program as previous  # noqa: F401
