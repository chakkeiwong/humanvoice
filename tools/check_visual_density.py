#!/usr/bin/env python3
"""Check the distribution of numbered figures and tables in the built proposal."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


ENTRY = re.compile(
    r"\\@writefile\{lo(?P<list>[ft])\}"
    r"\{\\contentsline \{(?P<kind>figure|table)\}.*"
    r"\}\{(?P<page>\d+)\}\{(?P=kind)"
)


@dataclass(frozen=True)
class Visual:
    kind: str
    page: int


def parse_visuals(aux_text: str) -> list[Visual]:
    visuals: list[Visual] = []
    for line in aux_text.splitlines():
        match = ENTRY.search(line)
        if match:
            visuals.append(Visual(match.group("kind"), int(match.group("page"))))
    return visuals


def density_summary(visuals: list[Visual]) -> dict[str, float | int]:
    if not visuals:
        return {
            "figures": 0,
            "tables": 0,
            "total": 0,
            "body_pages": 0,
            "pages_per_visual": float("inf"),
            "largest_page_gap": 0,
        }

    pages = sorted({visual.page for visual in visuals})
    gaps = [pages[0] - 1, *(right - left for left, right in zip(pages, pages[1:]))]
    body_pages = max(pages)
    return {
        "figures": sum(visual.kind == "figure" for visual in visuals),
        "tables": sum(visual.kind == "table" for visual in visuals),
        "total": len(visuals),
        "body_pages": body_pages,
        "pages_per_visual": body_pages / len(visuals),
        "largest_page_gap": max(gaps),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("aux", type=Path)
    parser.add_argument("--min-figures", type=int, default=20)
    parser.add_argument("--min-total", type=int, default=80)
    parser.add_argument("--max-pages-per-visual", type=float, default=3.0)
    args = parser.parse_args()

    summary = density_summary(parse_visuals(args.aux.read_text(encoding="utf-8")))
    checks = {
        "figure_program": summary["figures"] >= args.min_figures,
        "numbered_visual_program": summary["total"] >= args.min_total,
        "average_visual_density": (
            summary["pages_per_visual"] <= args.max_pages_per_visual
        ),
    }

    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    print(
        "INFO "
        f"figures={summary['figures']} "
        f"tables={summary['tables']} "
        f"numbered_visuals={summary['total']} "
        f"body_pages_through_last_visual={summary['body_pages']} "
        f"pages_per_visual={summary['pages_per_visual']:.2f} "
        f"largest_page_gap={summary['largest_page_gap']}"
    )
    print(
        "DIAGNOSTIC ONLY: density does not establish that a visual is accurate, "
        "necessary, legible, or understood."
    )
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
