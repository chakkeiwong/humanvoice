#!/usr/bin/env python3
"""
Humanvoice CLI entry point.

The v2 command surface:
  hv init       - Create immutable source snapshot and validate brief
  hv inventory  - Extract and freeze complete concept baseline
  hv plan       - Build dependency-aware teaching plan from frozen baseline
  hv rewrite    - Rewrite source passages with concept preservation
  hv preflight  - Run independent critics and structural checks
  hv repair     - Apply bounded repairs (max 3 cycles with oscillation detection)
  hv assemble   - Assemble rewritten units via source patches
  hv release    - Generate immutable reader packet (human acceptance is separate)
  hv pipeline   - Master orchestration (legacy v1)

Exit codes per implementation contract:
  0 - pass or released
  1 - deterministic gate failure
  2 - abstention or unresolved policy-dependent result
  3 - invalid input, brief, schema, or command usage
  4 - internal implementation error
  5 - security or trust-boundary violation
"""

import sys
import argparse
from pathlib import Path


def build_parser():
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog='hv',
        description='Humanvoice - local-first authoring system for technical documents'
    )
    parser.add_argument('--version', action='version', version='%(prog)s 0.1.0')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # hv init
    init_parser = subparsers.add_parser('init', help='Create immutable source snapshot and validate brief')
    init_parser.add_argument('source', type=Path, help='Source directory or file')
    init_parser.add_argument('--brief', type=Path, required=True, help='Reader brief (JSON)')
    init_parser.add_argument('--output', type=Path, required=True, help='Output directory for snapshot')

    # hv inventory
    inventory_parser = subparsers.add_parser('inventory', help='Extract and freeze complete concept baseline')
    inventory_parser.add_argument('snapshot', type=Path, help='Snapshot directory from hv init')
    inventory_parser.add_argument('--mock', action='store_true', help='Use mock mode (no model calls)')
    inventory_parser.add_argument('--freeze', action='store_true', help='Freeze baseline after extraction')
    inventory_parser.add_argument('--adjudicator', type=str, default='test-harness', help='Adjudicator identifier')

    # hv pipeline
    pipeline_parser = subparsers.add_parser('pipeline', help='Master orchestration: plan→draft→repair→assemble→release')
    pipeline_parser.add_argument('snapshot', type=Path, help='Snapshot directory from hv init')
    pipeline_parser.add_argument('--brief', type=Path, required=True, help='Reader brief (JSON)')
    pipeline_parser.add_argument('--run-id', type=str, help='Reuse existing run ID')
    pipeline_parser.add_argument('--mock', action='store_true', help='Use mock mode (no API calls)')

    # hv plan
    plan_parser = subparsers.add_parser('plan', help='Build dependency-aware teaching plan from frozen baseline')
    plan_parser.add_argument('snapshot', type=Path, help='Snapshot directory from hv init')
    plan_parser.add_argument('--max-unit-size', type=int, default=2000, help='Target max words per unit (default: 2000)')

    # hv rewrite
    rewrite_parser = subparsers.add_parser('rewrite', help='Rewrite source passages with concept preservation')
    rewrite_parser.add_argument('snapshot', type=Path, help='Snapshot directory from hv init')
    rewrite_parser.add_argument('--baseline-id', required=True, help='Baseline ID (e.g., baseline-001)')
    rewrite_parser.add_argument('--plan-id', required=True, help='Plan ID (e.g., plan-001)')
    rewrite_parser.add_argument('--mock', action='store_true', help='Use mock mode (no model calls)')

    # hv draft
    draft_parser = subparsers.add_parser('draft', help='Produce unit-level draft within blueprint boundary')
    draft_parser.add_argument('snapshot', type=Path, help='Snapshot directory from hv init')
    draft_parser.add_argument('--blueprint', type=Path, required=True, help='Blueprint from hv plan')
    draft_parser.add_argument('--brief', type=Path, required=True, help='Reader brief (JSON)')

    # Exactly one mode is required: single section, missing only, or all
    mode_group = draft_parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--section', type=int, metavar='N', help='Draft section N (0-based)')
    mode_group.add_argument('--missing', action='store_true', help='Draft only sections without a draft on disk')
    mode_group.add_argument('--all', action='store_true', help='Draft every section, continuing past failures')

    draft_parser.add_argument('--mock', action='store_true', help='Use mock mode (no API calls)')

    # hv assemble
    assemble_parser = subparsers.add_parser('assemble', help='Assemble drafted sections into complete document')
    assemble_parser.add_argument('snapshot', type=Path, help='Snapshot directory from hv init')
    assemble_parser.add_argument('--brief', type=Path, required=True, help='Reader brief (JSON)')
    assemble_parser.add_argument('--output', type=Path, default=None,
                                 help='Output directory (default: <snapshot>/.humanvoice/revisions/assembled)')
    assemble_parser.add_argument('--skip-blackline', action='store_true',
                                 help='Skip blacklined comparison (draft review only; release will block)')

    # hv validate-blueprint
    validate_bp_parser = subparsers.add_parser('validate-blueprint',
                                                help='Check if blueprint subsections fit within token ceiling')
    validate_bp_parser.add_argument('blueprint', type=Path, help='Blueprint JSON file')
    validate_bp_parser.add_argument('-v', '--verbose', action='store_true',
                                     help='Show all subsections, not just unsafe ones')

    # hv preflight
    preflight_parser = subparsers.add_parser('preflight', help='Run independent critics and structural checks')
    preflight_parser.add_argument('snapshot', type=Path, help='Snapshot directory from hv init')
    preflight_parser.add_argument('--brief', type=Path, required=True, help='Reader brief (JSON)')
    preflight_parser.add_argument('--deterministic', action='store_true',
                                   help='Deterministic mode (no model invocation)')

    # hv repair
    repair_parser = subparsers.add_parser('repair', help='Apply bounded repairs to a draft')
    repair_parser.add_argument('draft', type=Path, help='Draft .tex file from hv draft')
    repair_parser.add_argument('--findings', type=Path, required=True,
                              help='Preflight result or findings array (JSON)')
    repair_parser.add_argument('--brief', type=Path, required=True, help='Reader brief (JSON)')
    repair_parser.add_argument('--output-dir', type=Path, default=None,
                              help='Revisions directory (default: <draft dir>/revisions)')
    repair_parser.add_argument('--mock', action='store_true', help='Use mock mode (no API calls)')

    # hv release
    release_parser = subparsers.add_parser('release', help='Generate immutable reader packet')
    release_parser.add_argument('snapshot', type=Path, help='Snapshot directory from hv init')
    release_parser.add_argument('--brief', type=Path, required=True, help='Reader brief (JSON)')
    release_parser.add_argument('--output', type=Path, default=None,
                               help='Output directory for release packet (default: <snapshot>/release)')

    return parser


def main():
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 3

    # Route to command handlers
    if args.command == 'init':
        from humanvoice.commands import init_command
        return init_command.run(args)
    elif args.command == 'inventory':
        from humanvoice.commands import inventory_command
        return inventory_command.run(args)
    elif args.command == 'pipeline':
        from humanvoice.commands import pipeline_command
        return pipeline_command.run(args)
    elif args.command == 'preflight':
        from humanvoice.commands import preflight_command
        return preflight_command.run(args)
    elif args.command == 'plan':
        from humanvoice.commands import plan_v2_command
        return plan_v2_command.run(args)
    elif args.command == 'rewrite':
        from humanvoice.commands import rewrite_command
        return rewrite_command.main()
    elif args.command == 'validate-blueprint':
        from humanvoice.commands import validate_blueprint_command
        return validate_blueprint_command.main(sys.argv[2:])
    elif args.command == 'draft':
        from humanvoice.commands import draft_command
        return draft_command.run(args)
    elif args.command == 'assemble':
        from humanvoice.commands import assemble_command
        return assemble_command.run(args)
    elif args.command == 'repair':
        from humanvoice.commands import repair_command
        return repair_command.run(args)
    elif args.command == 'release':
        from humanvoice.commands import release_command
        return release_command.run(args)
    else:
        parser.print_help()
        return 3


if __name__ == '__main__':
    sys.exit(main())
