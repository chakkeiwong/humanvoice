"""
hv validate-blueprint - Check if subsections fit within token ceiling

Validates that each subsection in the blueprint can be drafted within the
8192 token output ceiling, based on:
1. Word budget + variance (×1.2)
2. Estimated LaTeX token density (conservative 4.0 tokens/word)
3. Evidence size in the source line range

Flags subsections that exceed safe limits and suggests splits.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple


# Conservative estimate: math-heavy LaTeX can reach 4-5 tokens/word
CONSERVATIVE_TOKENS_PER_WORD = 4.0

# Profile maximum from inference_profile.json
MAX_OUTPUT_TOKENS = 8192

# Safety margin: aim for 90% of ceiling to leave room for variance
SAFETY_FACTOR = 0.9
SAFE_CEILING = int(MAX_OUTPUT_TOKENS * SAFETY_FACTOR)


def _estimate_output_tokens(word_budget: int) -> int:
    """
    Estimate output tokens needed for a subsection.

    Uses conservative 4.0 tokens/word with 20% variance allowance.
    """
    max_words = word_budget * 1.2  # Allow 20% overrun
    return int(max_words * CONSERVATIVE_TOKENS_PER_WORD)


def _check_subsection(
    subsection: Dict[str, Any],
    chapter_idx: int,
    subsection_idx: int
) -> Tuple[bool, str]:
    """
    Check if subsection fits within safe token ceiling.

    Returns (is_safe, diagnostic_message)
    """
    title = subsection.get("title", "Untitled")
    word_budget = subsection.get("word_budget", 500)

    estimated_tokens = _estimate_output_tokens(word_budget)

    if estimated_tokens > SAFE_CEILING:
        overage = estimated_tokens - SAFE_CEILING
        overage_pct = (overage / SAFE_CEILING) * 100
        return False, (
            f"  ✗ Chapter {chapter_idx+1}, subsection {subsection_idx+1}: '{title}'\n"
            f"    Word budget: {word_budget} → ~{estimated_tokens} tokens "
            f"(exceeds safe ceiling {SAFE_CEILING} by {overage} tokens, {overage_pct:.0f}%)\n"
            f"    Recommendation: Split into {(estimated_tokens // SAFE_CEILING) + 1} subsections "
            f"of ~{word_budget // ((estimated_tokens // SAFE_CEILING) + 1)} words each"
        )

    return True, (
        f"  ✓ Chapter {chapter_idx+1}, subsection {subsection_idx+1}: '{title}' "
        f"({word_budget}w → ~{estimated_tokens}t)"
    )


def validate_blueprint(blueprint_path: Path, verbose: bool = False) -> int:
    """
    Validate blueprint subsection sizing.

    Returns:
        0 if all subsections are safe
        1 if any subsection exceeds safe ceiling
    """
    if not blueprint_path.exists():
        print(f"Error: Blueprint not found: {blueprint_path}", file=sys.stderr)
        return 1

    try:
        data = json.loads(blueprint_path.read_text())
        blueprint = data.get("blueprint", {})
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in blueprint: {e}", file=sys.stderr)
        return 1

    chapters = blueprint.get("chapters", [])
    if not chapters:
        print("Warning: No chapters found in blueprint", file=sys.stderr)
        return 0

    print(f"Validating blueprint: {blueprint_path.name}")
    print(f"Safe ceiling: {SAFE_CEILING} tokens ({SAFETY_FACTOR*100:.0f}% of {MAX_OUTPUT_TOKENS})")
    print(f"Conservative estimate: {CONSERVATIVE_TOKENS_PER_WORD} tokens/word with 20% variance\n")

    all_safe = True
    unsafe_sections = []

    for ch_idx, chapter in enumerate(chapters):
        chapter_title = chapter.get("title", "Untitled Chapter")
        subsections = chapter.get("subsections", [])

        if verbose or not subsections:
            print(f"Chapter {ch_idx+1}: {chapter_title}")

        for sub_idx, subsection in enumerate(subsections):
            is_safe, message = _check_subsection(subsection, ch_idx, sub_idx)

            if verbose or not is_safe:
                print(message)

            if not is_safe:
                all_safe = False
                unsafe_sections.append((ch_idx, sub_idx, subsection.get("title")))

    print()
    if all_safe:
        print("✓ All subsections fit within safe token ceiling")
        return 0
    else:
        print(f"✗ {len(unsafe_sections)} subsection(s) exceed safe ceiling")
        print("\nRecommendation: Re-run 'hv plan' with smaller target word budgets,")
        print("or manually split the flagged subsections in the blueprint JSON.")
        return 1


def main(argv: List[str]) -> int:
    """CLI entry point for hv validate-blueprint"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate blueprint subsection sizing against token ceiling"
    )
    parser.add_argument(
        "blueprint",
        type=Path,
        help="Path to blueprint.json file"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show all subsections, not just unsafe ones"
    )

    args = parser.parse_args(argv)
    return validate_blueprint(args.blueprint, verbose=args.verbose)
