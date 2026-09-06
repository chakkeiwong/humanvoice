#!/usr/bin/env bash
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
document_dir="$repo_root/docs/survey"
source_name="humanvoice_survey.tex"
job_name="humanvoice_survey"

cd "$document_dir"

# Keep the rendered snapshot and its metadata reproducible; override this for a
# deliberately dated release.
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1787529600}"

python3 "$repo_root/tools/check_humanvoice_document.py" "$source_name"
python3 "$repo_root/tools/check_implementation_contract.py"

latex_flags=(-interaction=batchmode -halt-on-error -file-line-error -no-shell-escape)
pdflatex "${latex_flags[@]}" "$source_name"
bibtex "$job_name"
pdflatex "${latex_flags[@]}" "$source_name"
pdflatex "${latex_flags[@]}" "$source_name"

if rg -q 'undefined citations|There were undefined references|Citation .* undefined|Reference .* undefined' "$job_name.log"; then
  echo "The unified manuscript contains unresolved citations or references." >&2
  exit 1
fi

python3 "$repo_root/tools/check_visual_density.py" "$job_name.aux"

pdfinfo "$job_name.pdf" | rg '^(Pages|File size)'
python3 "$repo_root/tools/update_humanvoice_status.py"
