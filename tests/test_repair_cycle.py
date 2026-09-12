"""
Tests for WP-V2-4 repair cycle management.

Tests bounded repairs with convergence detection:
- Repair prompt generation
- Oscillation detection
- Cycle management
- Session persistence
"""

import pytest
from pathlib import Path

from humanvoice.repair_cycle import (
    RepairOutcome,
    RepairCycle,
    RepairSession,
    build_repair_prompt,
    detect_oscillation,
    should_continue_repair,
    finalize_repair_session,
    save_repair_session,
)


def test_build_repair_prompt():
    """Repair prompt generated with target concepts and obligations."""
    prompt = build_repair_prompt(
        unit_id="unit-001",
        source_latex="Original text here",
        target_concepts=["c1", "c2"],
        unmet_obligations=["definition", "example"],
        current_output="Failed output",
        brief={"genre": "technical"},
    )

    assert "REPAIR CYCLE" in prompt
    assert "unit-001" in prompt
    assert "c1" in prompt
    assert "definition" in prompt
    assert "Original text here" in prompt
    assert "Failed output" in prompt


def test_repair_cycle_initialization():
    """RepairCycle initializes with correct fields."""
    cycle = RepairCycle(
        cycle_num=1,
        target_concept_ids=["c1"],
        unmet_obligations=["def"],
    )

    assert cycle.cycle_num == 1
    assert cycle.target_concept_ids == ["c1"]
    assert cycle.unmet_obligations == ["def"]
    assert not cycle.repair_successful
    assert cycle.outcome is None


def test_detect_oscillation_no_cycles():
    """No oscillation detected with < 2 cycles."""
    cycles = [
        RepairCycle(1, ["c1"], ["def"], error_signature="error-123"),
    ]

    is_osc = detect_oscillation(cycles, "error-123")
    assert not is_osc


def test_detect_oscillation_different_errors():
    """No oscillation when errors differ."""
    cycles = [
        RepairCycle(1, ["c1"], ["def"], error_signature="error-123"),
        RepairCycle(2, ["c1"], ["def"], error_signature="error-456"),
    ]

    is_osc = detect_oscillation(cycles, "error-789")
    assert not is_osc


def test_detect_oscillation_recurring_error():
    """Oscillation detected when error recurs."""
    cycles = [
        RepairCycle(1, ["c1"], ["def"], error_signature="error-123"),
        RepairCycle(2, ["c1"], ["def"], error_signature="error-456"),
    ]

    is_osc = detect_oscillation(cycles, "error-123")  # Same as cycle 1
    assert is_osc


def test_repair_session_initialization():
    """RepairSession initializes with default max_cycles."""
    session = RepairSession(
        unit_id="unit-001",
        baseline_id="baseline-001",
        initial_preflight_findings=3,
    )

    assert session.unit_id == "unit-001"
    assert session.baseline_id == "baseline-001"
    assert session.initial_preflight_findings == 3
    assert session.max_cycles == 3
    assert len(session.cycles) == 0
    assert not session.is_acceptable


def test_should_continue_repair_max_cycles_exceeded():
    """Repair stops when max cycles reached."""
    session = RepairSession("u1", "b1", max_cycles=2)
    session.total_cycles_used = 2

    cycle = RepairCycle(2, ["c1"], ["def"])

    should_continue = should_continue_repair(session, cycle)
    assert not should_continue


def test_should_continue_repair_converged():
    """Repair stops when converged."""
    session = RepairSession("u1", "b1", max_cycles=3)
    session.total_cycles_used = 1

    cycle = RepairCycle(1, ["c1"], ["def"])
    cycle.outcome = RepairOutcome.CONVERGED

    should_continue = should_continue_repair(session, cycle)
    assert not should_continue


def test_should_continue_repair_oscillating():
    """Repair stops when oscillating."""
    session = RepairSession("u1", "b1", max_cycles=3)
    session.total_cycles_used = 2

    cycle = RepairCycle(2, ["c1"], ["def"])
    cycle.outcome = RepairOutcome.OSCILLATING

    should_continue = should_continue_repair(session, cycle)
    assert not should_continue


def test_should_continue_repair_continue():
    """Repair continues when conditions met."""
    session = RepairSession("u1", "b1", max_cycles=3)
    session.total_cycles_used = 1

    cycle = RepairCycle(1, ["c1"], ["def"])
    cycle.outcome = RepairOutcome.TIMEOUT  # Not terminal

    should_continue = should_continue_repair(session, cycle)
    assert should_continue


def test_finalize_repair_session_converged():
    """Finalized session marked acceptable when converged."""
    session = RepairSession("u1", "b1")
    cycle = RepairCycle(1, ["c1"], ["def"])
    cycle.outcome = RepairOutcome.CONVERGED
    session.cycles = [cycle]

    finalized = finalize_repair_session(session)

    assert finalized.is_acceptable
    assert finalized.final_outcome == RepairOutcome.CONVERGED


def test_finalize_repair_session_oscillating():
    """Finalized session marked unacceptable when oscillating."""
    session = RepairSession("u1", "b1", max_cycles=3)
    session.total_cycles_used = 3
    cycle = RepairCycle(3, ["c1"], ["def"])
    cycle.outcome = RepairOutcome.OSCILLATING
    session.cycles = [cycle]

    finalized = finalize_repair_session(session)

    assert not finalized.is_acceptable
    assert finalized.final_outcome == RepairOutcome.OSCILLATING


def test_finalize_repair_session_timeout():
    """Finalized session marked unacceptable on timeout."""
    session = RepairSession("u1", "b1", max_cycles=2)
    session.total_cycles_used = 2
    cycle = RepairCycle(2, ["c1"], ["def"])
    cycle.outcome = RepairOutcome.TIMEOUT
    session.cycles = [cycle]

    finalized = finalize_repair_session(session)

    assert not finalized.is_acceptable
    assert finalized.final_outcome == RepairOutcome.TIMEOUT


def test_finalize_repair_session_no_cycles():
    """Finalized session marked timeout when no cycles."""
    session = RepairSession("u1", "b1")

    finalized = finalize_repair_session(session)

    assert not finalized.is_acceptable
    assert finalized.final_outcome == RepairOutcome.TIMEOUT


def test_save_repair_session(tmp_path):
    """Repair session saved to JSON."""
    session = RepairSession(
        unit_id="unit-001",
        baseline_id="baseline-001",
        initial_preflight_findings=2,
        max_cycles=3,
        total_cycles_used=1,
    )

    cycle = RepairCycle(1, ["c1"], ["def"])
    cycle.outcome = RepairOutcome.CONVERGED
    cycle.repair_successful = True
    session.cycles = [cycle]
    session.final_outcome = RepairOutcome.CONVERGED
    session.is_acceptable = True

    output_file = tmp_path / "session.json"
    save_repair_session(session, output_file)

    assert output_file.exists()

    import json
    with open(output_file) as f:
        data = json.load(f)

    assert data["unit_id"] == "unit-001"
    assert data["total_cycles_used"] == 1
    assert data["final_outcome"] == "converged"
    assert data["is_acceptable"]
    assert len(data["cycles"]) == 1


def test_repair_outcome_enum_values():
    """RepairOutcome enum has correct values."""
    assert RepairOutcome.CONVERGED.value == "converged"
    assert RepairOutcome.OSCILLATING.value == "oscillating"
    assert RepairOutcome.TIMEOUT.value == "timeout"
    assert RepairOutcome.UNRESOLVABLE.value == "unresolvable"


def test_repair_cycle_error_signature():
    """Error signature tracked for oscillation detection."""
    cycle1 = RepairCycle(1, ["c1"], ["def"], error_signature="sig-abc")
    cycle2 = RepairCycle(2, ["c1"], ["def"], error_signature="sig-def")

    assert cycle1.error_signature == "sig-abc"
    assert cycle2.error_signature == "sig-def"
    assert cycle1.error_signature != cycle2.error_signature


def test_repair_session_cycle_tracking():
    """Repair session accumulates cycles correctly."""
    session = RepairSession("u1", "b1", max_cycles=3)

    cycle1 = RepairCycle(1, ["c1"], ["def"])
    cycle1.outcome = RepairOutcome.TIMEOUT
    session.cycles.append(cycle1)

    cycle2 = RepairCycle(2, ["c1"], ["def"])
    cycle2.outcome = RepairOutcome.CONVERGED
    session.cycles.append(cycle2)

    assert len(session.cycles) == 2
    assert session.cycles[0].cycle_num == 1
    assert session.cycles[1].cycle_num == 2
