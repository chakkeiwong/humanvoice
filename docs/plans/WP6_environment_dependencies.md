# Humanvoice v1.1 Environment and Dependencies

**Date:** 2026-08-28  
**Purpose:** Document tested environment for independent reproduction

## Tested Platform

- **OS:** Linux 6.8.0-40-generic (Ubuntu with glibc 2.35)
- **Python:** 3.13.13
- **Shell:** bash
- **TeX:** pdfTeX 3.141592653-2.6-1.40.22 (TeX Live 2022/dev/Debian)
- **kpathsea:** 6.3.4/dev

## Python Dependencies (Locked Versions)

Production dependencies:
```
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
referencing==0.37.0
anthropic==0.42.0
```

Development/testing dependencies:
```
pytest==9.1.1
pytest-timeout>=2.1.0
```

**Installation:**
```bash
pip install jsonschema==4.26.0 jsonschema-specifications==2025.9.1 referencing==0.37.0
pip install anthropic==0.42.0  # For model-dependent commands
pip install pytest==9.1.1 pytest-timeout  # For test suite
```

Or from lock file:
```bash
pip install -r requirements-lock.txt
pip install pytest-timeout  # Not pinned
```

## Environment Variables

Required for model-dependent commands (plan, draft, repair):
```bash
export ANTHROPIC_API_KEY="your-key-here"
```

Optional for build determinism:
```bash
export SOURCE_DATE_EPOCH="1234567890"  # Unix timestamp for reproducible builds
```

## Installation from Clean Checkout

```bash
# 1. Clone repository
git clone <repository-url> humanvoice
cd humanvoice

# 2. Verify prerequisites
python --version  # Should be >= 3.10 (tested with 3.13.13)
pdflatex --version  # Should report pdfTeX (tested with TeX Live 2022)

# 3. Install package
pip install -e .

# 4. Install locked dependencies
pip install -r requirements-lock.txt

# 5. Verify installation
hv --help  # Should show command list

# 6. Run test suite (deterministic path, no API key needed)
python -m pytest tests/test_init.py -v
python -m pytest tests/test_preflight.py -v
python -m pytest tests/test_release_command.py -v

# 7. Run contract verification
python tools/check_implementation_contract.py

# 8. Run full test suite (requires API key for model property tests)
export ANTHROPIC_API_KEY="..."
python -m pytest tests/ -v  # Should show 67 passed
python -m pytest tools/ -v -k test_  # Should show 61 passed

# 9. Run fixture validation
python tools/run_fixture_suite.py  # Should show 4/4 ready fixtures pass
python tools/run_mutation_replay.py  # Should show 9/9 mutations caught
```

## Known Platform Dependencies

**Required:**
- Linux or Unix-like OS (tested on Ubuntu, should work on macOS/WSL)
- Python 3.10+ (tested with 3.13.13)
- pdfTeX from TeX Live distribution

**Not required:**
- GPU or CUDA (uses API model, not local inference)
- Docker or containers (runs directly on host)
- Network access for deterministic tests (only model-dependent tests need API)

## Version Compatibility Notes

**Python:**
- Minimum: 3.10 (per pyproject.toml)
- Tested: 3.13.13
- Expected to work: 3.10-3.13

**TeX Live:**
- Tested: 2022/dev/Debian
- Expected to work: TeX Live 2020+
- Required flags: `-no-shell-escape`, `-halt-on-error`, `-file-line-error`

**jsonschema:**
- Pinned: 4.26.0
- Uses JSON Schema Draft 2020-12
- Required for schema validation

**anthropic:**
- Pinned: 0.42.0 (API client for Claude)
- Only needed for model-dependent commands (plan, draft, repair)
- Deterministic commands (init, preflight, release) work without it

## Verification Commands

After installation, verify the environment:

```bash
# Check package installation
python -c "import humanvoice; print(humanvoice.__file__)"

# Check CLI entry point
which hv

# Check schema validator
python -c "import jsonschema; print(jsonschema.__version__)"

# Check TeX installation
which pdflatex

# Run quick smoke test
python -m pytest tests/test_init.py -v
```

Expected output:
- Package found in `src/humanvoice`
- CLI at `/path/to/bin/hv`
- jsonschema version 4.26.0
- pdflatex found in PATH
- 5/5 init tests pass

## Reproducing Test Results

Full suite results from 2026-08-28:

```
Product tests:     67 passed in 0.81s
Tools tests:       61 passed in 1.45s
Fixture suite:     4/4 ready fixtures pass, 12 not executed (planned/unavailable)
Mutation replay:   9/9 mutations caught, 0 missed, 0 errors
Contract checker:  All assertions pass
```

To reproduce:
```bash
python -m pytest tests/ -v --tb=short
python -m pytest tools/ -v -k test_ --tb=short
python tools/run_fixture_suite.py
python tools/run_mutation_replay.py
python tools/check_implementation_contract.py
```

## Known Environment Variations

**May affect results:**
- TeX Live version < 2020 (parser may behave differently)
- Python < 3.10 (incompatible, will fail to install)
- jsonschema != 4.26.0 (validation behavior may differ)

**Should not affect results:**
- OS (Linux vs macOS vs WSL)
- Python 3.10-3.13 minor versions
- TeX Live 2020-2024 versions
- File system case sensitivity (all paths use correct case)

## Dependency Rationale

| Package | Purpose | Why Pinned |
|---------|---------|------------|
| jsonschema 4.26.0 | Schema validation | Draft 2020-12 support, validation semantics |
| referencing 0.37.0 | Schema references | Dependency of jsonschema |
| anthropic 0.42.0 | Claude API client | Model invocation for WP4 commands |
| pytest 9.1.1 | Test framework | Test execution |
| pytest-timeout | Test timeouts | Prevent hanging tests (not pinned, >=2.1.0) |

## Container/Virtual Environment

Not required, but recommended for isolation:

```bash
# Using venv
python -m venv humanvoice-env
source humanvoice-env/bin/activate
pip install -e .
pip install -r requirements-lock.txt

# Using conda
conda create -n humanvoice python=3.13
conda activate humanvoice
pip install -e .
pip install -r requirements-lock.txt
```

## Next: Independent Reproduction

For WP3 independent operator reproduction, use this document with the [reproducibility checklist](WP6_reproducibility_checklist.md) to verify:
1. Clean checkout on fresh machine
2. Installation from scratch following commands above
3. Test suite execution (67 product + 61 tools pass)
4. Fixture validation (4/4 pass)
5. Mutation replay (9/9 caught)

Report any deviations from expected results.
