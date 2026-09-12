"""
Repair cycle management for WP-V2-4.

Bounded repairs with convergence detection and oscillation prevention:
1. Accept preflight result with unmet obligations
2. Issue targeted repair prompt (concept/obligation specific)
3. Run preflight on repaired output
4. Detect convergence or oscillation
5. Block after max cycles (default 3)
"""

from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
import json


class RepairOutcome(Enum):
    """Outcome of repair cycle."""
    CONVERGED = "converged"      # Repair succeeded
    OSCILLATING = "oscillating"  # Same error recurring
    TIMEOUT = "timeout"          # Max cycles reached
    UNRESOLVABLE = "unresolvable"  # Cannot be repaired


@dataclass
class RepairCycle:
    """One iteration of targeted repair."""
    cycle_num: int
    target_concept_ids: List[str]  # Concepts to repair
    unmet_obligations: List[str]   # Specific obligations to address
    repair_prompt: str = ""
    output_latex: str = ""
    repair_successful: bool = False
    outcome: Optional[RepairOutcome] = None
    error_signature: str = ""  # Hash of error for oscillation detection


@dataclass
class RepairSession:
    """Complete repair session for one unit."""
    unit_id: str
    baseline_id: str
    initial_preflight_findings: int = 0
    max_cycles: int = 3
    cycles: List[RepairCycle] = field(default_factory=list)
    final_outcome: Optional[RepairOutcome] = None
    is_acceptable: bool = False
    total_cycles_used: int = 0


def build_repair_prompt(
    unit_id: str,
    source_latex: str,
    target_concepts: List[str],
    unmet_obligations: List[str],
    current_output: str,
    brief: dict,
) -> str:
    """Build targeted repair prompt for specific obligations.

    Args:
        unit_id: Unit ID
        source_latex: Original source text
        target_concepts: Concepts that need repair
        unmet_obligations: Specific unmet obligations
        current_output: Current (failed) rewrite
        brief: Reader brief

    Returns:
        Repair prompt requesting targeted fixes
    """
    prompt = f"""REPAIR CYCLE: Fix specific unmet teaching obligations.

UNIT: {unit_id}
TARGET CONCEPTS: {', '.join(target_concepts)}
OBLIGATIONS TO ADDRESS: {', '.join(unmet_obligations)}

ORIGINAL SOURCE:
{source_latex}

CURRENT (FAILED) OUTPUT:
{current_output}

YOUR TASK:
Rewrite ONLY the sections addressing these concepts and obligations.
Do NOT change other content. Preserve all existing correspondences.
Do NOT delete any concepts or add unsupported claims.

REQUIRED FIXES:
- Add missing explanations for: {', '.join(unmet_obligations)}
- Keep all other content unchanged
- Preserve protected objects exactly
- Maintain LaTeX validity

OUTPUT FORMAT:
Return JSON with:
{{
  "replacement_latex": "Repaired LaTeX (full unit)",
  "concept_correspondences": [...],
  "protected_objects_preserved": [...],
  "repairs_made": ["list of specific fixes"],
  "explanation": "What was fixed"
}}
"""
    return prompt


def detect_oscillation(
    cycles: List[RepairCycle],
    current_error_signature: str,
) -> bool:
    """Detect if repair is oscillating (same error recurring).

    Args:
        cycles: Repair cycles completed
        current_error_signature: Hash of current error

    Returns:
        True if oscillation detected
    """
    if len(cycles) < 2:
        return False

    # Check if current error matches any previous cycle's error
    for cycle in cycles[:-1]:  # Exclude current cycle
        if cycle.error_signature == current_error_signature:
            return True

    return False


def run_repair_cycle(
    unit_id: str,
    baseline_id: str,
    source_latex: str,
    current_output: str,
    preflight_result: dict,
    model,
    brief: dict,
    cycle_num: int = 1,
) -> RepairCycle:
    """Execute one repair cycle.

    Args:
        unit_id: Unit ID
        baseline_id: Baseline ID
        source_latex: Original source
        current_output: Failed rewrite to repair
        preflight_result: Preflight verification result
        model: ModelAdapter
        brief: Reader brief
        cycle_num: Which cycle this is (1, 2, 3, ...)

    Returns:
        RepairCycle with outcome
    """
    cycle = RepairCycle(
        cycle_num=cycle_num,
        target_concept_ids=preflight_result.get("repair_targets", []),
        unmet_obligations=preflight_result.get("unmet_obligations", []),
    )

    # Build targeted repair prompt
    cycle.repair_prompt = build_repair_prompt(
        unit_id,
        source_latex,
        cycle.target_concept_ids,
        cycle.unmet_obligations,
        current_output,
        brief,
    )

    try:
        # Call model for repair
        if model is None:
            # Mock repair
            cycle.output_latex = current_output  # Placeholder
            cycle.repair_successful = False
        else:
            response = model.invoke(
                prompt=cycle.repair_prompt,
                record_type=None,
                temperature=0.3,
                max_tokens=8000,
            )

            if response.abstained or response.error:
                cycle.repair_successful = False
                cycle.outcome = RepairOutcome.UNRESOLVABLE
                cycle.error_signature = response.error or "abstained"
            else:
                cycle.output_latex = response.parsed.get("replacement_latex", "")
                cycle.repair_successful = bool(cycle.output_latex)

                if cycle.repair_successful:
                    cycle.outcome = RepairOutcome.CONVERGED
                    cycle.error_signature = ""

    except Exception as e:
        cycle.repair_successful = False
        cycle.outcome = RepairOutcome.UNRESOLVABLE
        cycle.error_signature = str(e)

    return cycle


def should_continue_repair(
    session: RepairSession,
    last_cycle: RepairCycle,
) -> bool:
    """Determine if repair should continue to next cycle.

    Args:
        session: Current repair session
        last_cycle: Last completed cycle

    Returns:
        True if repair should continue
    """
    # Max cycles exceeded
    if session.total_cycles_used >= session.max_cycles:
        return False

    # Already converged
    if last_cycle.outcome == RepairOutcome.CONVERGED:
        return False

    # Oscillation or unresolvable
    if last_cycle.outcome in (RepairOutcome.OSCILLATING, RepairOutcome.UNRESOLVABLE):
        return False

    return True


def finalize_repair_session(session: RepairSession) -> RepairSession:
    """Compute final session outcome and status.

    Args:
        session: Completed repair session

    Returns:
        Updated session with final outcome
    """
    if not session.cycles:
        session.final_outcome = RepairOutcome.TIMEOUT
        session.is_acceptable = False
        return session

    last_cycle = session.cycles[-1]

    # Determine outcome
    if last_cycle.outcome == RepairOutcome.CONVERGED:
        session.final_outcome = RepairOutcome.CONVERGED
        session.is_acceptable = True
    elif last_cycle.outcome == RepairOutcome.OSCILLATING:
        session.final_outcome = RepairOutcome.OSCILLATING
        session.is_acceptable = False
    elif session.total_cycles_used >= session.max_cycles:
        session.final_outcome = RepairOutcome.TIMEOUT
        session.is_acceptable = False
    else:
        session.final_outcome = RepairOutcome.UNRESOLVABLE
        session.is_acceptable = False

    return session


def save_repair_session(session: RepairSession, output_path) -> None:
    """Save repair session to JSON.

    Args:
        session: RepairSession
        output_path: Path to write
    """
    from pathlib import Path

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "unit_id": session.unit_id,
            "baseline_id": session.baseline_id,
            "initial_findings": session.initial_preflight_findings,
            "max_cycles": session.max_cycles,
            "total_cycles_used": session.total_cycles_used,
            "final_outcome": session.final_outcome.value if session.final_outcome else None,
            "is_acceptable": session.is_acceptable,
            "cycles": [
                {
                    "cycle_num": c.cycle_num,
                    "target_concepts": c.target_concept_ids,
                    "unmet_obligations": c.unmet_obligations,
                    "repair_successful": c.repair_successful,
                    "outcome": c.outcome.value if c.outcome else None,
                }
                for c in session.cycles
            ],
        }, f, indent=2)
