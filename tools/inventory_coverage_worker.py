"""Apply deterministic punctuation replay inside independent reproduction."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from tools import inventory_punctuation as punctuation
from tools import reproduction_overload_worker as previous


if __name__ == "__main__":
    with previous.continuation.archive.access(), punctuation.runtime():
        raise SystemExit(previous.execute(sys.argv[1], probe="--probe" in sys.argv[2:]))
