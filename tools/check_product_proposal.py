#!/usr/bin/env python3
"""Compatibility import for the former proposal checker.

The public candidate is now ``humanvoice_survey.tex``. New callers should use
``check_humanvoice_document.py`` directly.
"""

from check_humanvoice_document import document_checks as proposal_checks

__all__ = ["proposal_checks"]
