"""
Concept dependency planning and teaching order verification.

Ensures concepts are taught in an order that respects prerequisites:
readers encounter dependencies before the concepts that require them.

Key principles:
- Dependencies are explicit concept-to-concept links
- Dependency graph must be acyclic (or cycles explicitly resolved)
- Teaching order is validated against dependencies
- Forward references require explicit justification
- Circular dependencies surface for human review
"""

from dataclasses import dataclass, field
from typing import Optional
import json
from pathlib import Path


@dataclass
class ConceptDependency:
    """One prerequisite relationship between concepts."""
    dependent_concept_id: str  # Concept that requires the prerequisite
    prerequisite_concept_id: str  # Concept that must be taught first
    dependency_type: str  # "definition" | "notation" | "mechanism" | "result"
    strength: str = "required"  # "required" | "helpful" | "optional"
    justification: Optional[str] = None


@dataclass
class DependencyGraph:
    """Complete dependency structure for a concept baseline."""
    snapshot_id: str
    baseline_id: str
    dependencies: list[ConceptDependency] = field(default_factory=list)
    resolved_cycles: list[dict] = field(default_factory=list)
    teaching_order: list[str] = field(default_factory=list)  # Topologically sorted concept IDs


def extract_dependencies_from_baseline(baseline) -> list[ConceptDependency]:
    """Extract explicit dependencies from concept baseline.

    Args:
        baseline: ConceptBaseline with prerequisite annotations

    Returns:
        List of ConceptDependency objects
    """
    dependencies = []

    for entry in baseline.concept_entries:
        for prereq in entry.prerequisites:
            dependencies.append(ConceptDependency(
                dependent_concept_id=entry.concept_id,
                prerequisite_concept_id=prereq,
                dependency_type="definition",  # Could be refined with more metadata
                strength="required",
            ))

    return dependencies


def detect_cycles(dependencies: list[ConceptDependency], concept_ids: set[str]) -> list[list[str]]:
    """Detect circular dependencies in concept graph.

    Args:
        dependencies: List of ConceptDependency objects
        concept_ids: Set of all concept IDs in baseline

    Returns:
        List of cycles, each cycle is a list of concept IDs forming a loop
    """
    # Build adjacency list
    graph = {cid: [] for cid in concept_ids}
    for dep in dependencies:
        if dep.dependent_concept_id in graph:
            graph[dep.dependent_concept_id].append(dep.prerequisite_concept_id)

    cycles = []
    visited = set()
    rec_stack = set()
    path = []

    def dfs(node):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                # Found a cycle
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)
                return True

        path.pop()
        rec_stack.remove(node)
        return False

    for node in concept_ids:
        if node not in visited:
            dfs(node)

    return cycles


def topological_sort(dependencies: list[ConceptDependency], concept_ids: set[str]) -> Optional[list[str]]:
    """Compute teaching order via topological sort.

    Args:
        dependencies: List of ConceptDependency objects
        concept_ids: Set of all concept IDs

    Returns:
        List of concept IDs in valid teaching order, or None if cycles exist
    """
    # Build adjacency list and in-degree count
    graph = {cid: [] for cid in concept_ids}
    in_degree = {cid: 0 for cid in concept_ids}

    for dep in dependencies:
        if dep.dependent_concept_id in graph and dep.prerequisite_concept_id in concept_ids:
            graph[dep.prerequisite_concept_id].append(dep.dependent_concept_id)
            in_degree[dep.dependent_concept_id] += 1

    # Kahn's algorithm
    queue = [cid for cid in concept_ids if in_degree[cid] == 0]
    result = []

    while queue:
        # Sort for determinism when multiple nodes have in-degree 0
        queue.sort()
        node = queue.pop(0)
        result.append(node)

        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # If result doesn't include all nodes, there's a cycle
    if len(result) != len(concept_ids):
        return None

    return result


def create_dependency_graph(baseline, resolved_cycles: Optional[list] = None) -> DependencyGraph:
    """Build dependency graph from concept baseline.

    Args:
        baseline: ConceptBaseline with concepts and prerequisites
        resolved_cycles: Optional list of human-resolved circular dependencies

    Returns:
        DependencyGraph with teaching order computed
    """
    dependencies = extract_dependencies_from_baseline(baseline)
    concept_ids = {entry.concept_id for entry in baseline.concept_entries}

    # Check for cycles
    cycles = detect_cycles(dependencies, concept_ids)

    # Compute teaching order
    teaching_order = topological_sort(dependencies, concept_ids)

    if teaching_order is None and not resolved_cycles:
        # Cycles exist and haven't been resolved
        teaching_order = []

    graph = DependencyGraph(
        snapshot_id=baseline.snapshot_id,
        baseline_id=baseline.baseline_id,
        dependencies=dependencies,
        resolved_cycles=resolved_cycles or [],
        teaching_order=teaching_order or [],
    )

    return graph


def verify_teaching_order(
    proposed_order: list[str],
    dependencies: list[ConceptDependency],
) -> tuple[bool, list[str]]:
    """Verify that a proposed teaching order respects all dependencies.

    Args:
        proposed_order: List of concept IDs in proposed teaching order
        dependencies: List of ConceptDependency objects

    Returns:
        Tuple of (is_valid, list of violations)
    """
    # Build position index
    position = {cid: i for i, cid in enumerate(proposed_order)}

    violations = []
    for dep in dependencies:
        if dep.strength != "required":
            continue  # Only check required dependencies

        dependent_pos = position.get(dep.dependent_concept_id)
        prereq_pos = position.get(dep.prerequisite_concept_id)

        if dependent_pos is None or prereq_pos is None:
            continue  # Concept not in this order (might be in different section)

        if prereq_pos >= dependent_pos:
            violations.append(
                f"{dep.dependent_concept_id} requires {dep.prerequisite_concept_id}, "
                f"but appears at position {dependent_pos} before prerequisite at {prereq_pos}"
            )

    return len(violations) == 0, violations


def save_dependency_graph(graph: DependencyGraph, output_path: Path) -> None:
    """Write dependency graph to disk.

    Args:
        graph: DependencyGraph to save
        output_path: Path to write JSON file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "snapshot_id": graph.snapshot_id,
            "baseline_id": graph.baseline_id,
            "dependencies": [
                {
                    "dependent_concept_id": dep.dependent_concept_id,
                    "prerequisite_concept_id": dep.prerequisite_concept_id,
                    "dependency_type": dep.dependency_type,
                    "strength": dep.strength,
                    "justification": dep.justification,
                }
                for dep in graph.dependencies
            ],
            "resolved_cycles": graph.resolved_cycles,
            "teaching_order": graph.teaching_order,
        }, f, indent=2)


def load_dependency_graph(input_path: Path) -> DependencyGraph:
    """Load dependency graph from disk.

    Args:
        input_path: Path to dependency graph JSON

    Returns:
        DependencyGraph object
    """
    with open(input_path, 'r') as f:
        data = json.load(f)

    dependencies = []
    for dep_data in data["dependencies"]:
        dependencies.append(ConceptDependency(
            dependent_concept_id=dep_data["dependent_concept_id"],
            prerequisite_concept_id=dep_data["prerequisite_concept_id"],
            dependency_type=dep_data["dependency_type"],
            strength=dep_data.get("strength", "required"),
            justification=dep_data.get("justification"),
        ))

    return DependencyGraph(
        snapshot_id=data["snapshot_id"],
        baseline_id=data["baseline_id"],
        dependencies=dependencies,
        resolved_cycles=data.get("resolved_cycles", []),
        teaching_order=data.get("teaching_order", []),
    )


def identify_forward_references(
    teaching_order: list[str],
    dependencies: list[ConceptDependency],
) -> list[dict]:
    """Identify concepts that are used before being taught.

    Args:
        teaching_order: List of concept IDs in teaching order
        dependencies: List of ConceptDependency objects

    Returns:
        List of forward reference violations with details
    """
    position = {cid: i for i, cid in enumerate(teaching_order)}
    forward_refs = []

    for dep in dependencies:
        dependent_pos = position.get(dep.dependent_concept_id)
        prereq_pos = position.get(dep.prerequisite_concept_id)

        if dependent_pos is not None and prereq_pos is not None:
            if prereq_pos > dependent_pos:  # Prerequisite comes after dependent
                forward_refs.append({
                    "dependent": dep.dependent_concept_id,
                    "prerequisite": dep.prerequisite_concept_id,
                    "dependent_position": dependent_pos,
                    "prerequisite_position": prereq_pos,
                    "distance": prereq_pos - dependent_pos,
                })

    return forward_refs
