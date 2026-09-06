#!/usr/bin/env bash
set -euo pipefail

# Compatibility entry point: the public candidate is now one TeX manuscript.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$script_dir/build_humanvoice.sh" "$@"
