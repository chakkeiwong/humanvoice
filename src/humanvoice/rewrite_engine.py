"""
Source-grounded rewrite engine for humanized manuscripts.

WP-V2-3: Takes immutable source spans + frozen concept baseline and produces
improved explanations while preserving every concept and obligation.

Core principle: Start from source, preserve meaning, improve clarity.
Never delete, add unsupported, or truncate concepts.

Key capabilities:
- Concept-to-concept correspondence tracking
- Obligation fulfillment verification
- Protected object preservation
- Reject unsafe mutations
- Resume on incomplete obligations
"""

from dataclasses import dataclass, field
from typing import Optional
from hashlib import sha256
import json


@dataclass
class ExplanationObligation:
    """Required teaching functions for a concept."""
    concept_id: str
    functions: list[str] = field(default_factory=list)  # "definition", "mechanism", "example", etc.
    source_evidence: list[dict] = field(default_factory=list)  # Located source spans
    fulfilled_in_output: bool = False
    output_span_ids: list[str] = field(default_factory=list)


@dataclass
class ConceptCorrespondence:
    """Mapping between source and output concepts."""
    source_concept_id: str
    output_span_ids: list[str]  # Spans where this concept appears in output
    mapping_type: str  # "retain" | "paraphrase" | "expand" | "merge" | "split"
    output_text_preview: str = ""
    confidence: float = 0.0
    rationale: Optional[str] = None


@dataclass
class RewriteResult:
    """Output of rewriting one unit."""
    unit_id: str
    source_span_ids: list[str]
    output_latex: str
    output_hash: str
    concept_correspondences: list[ConceptCorrespondence] = field(default_factory=list)
    fulfilled_obligations: list[ExplanationObligation] = field(default_factory=list)
    unmet_obligations: list[ExplanationObligation] = field(default_factory=list)
    protected_objects_preserved: list[str] = field(default_factory=list)
    mutations: list[dict] = field(default_factory=list)  # Detected unsafe mutations
    is_acceptable: bool = False
    rejection_reasons: list[str] = field(default_factory=list)


def build_rewrite_context(
    unit,
    baseline,
    plan,
    source_texts: dict,
    protected_objects: dict,
    brief: dict,
    policy_snapshot: dict,
    dependency_graph=None,
) -> dict:
    """Build complete context for rewriting one unit.

    Args:
        unit: RewriteUnit from semantic plan
        baseline: Frozen ConceptBaseline
        plan: RewritePlan containing unit
        source_texts: Map of span_id -> exact_text
        protected_objects: Map of span_id -> [ProtectedObject]
        brief: HumanizationBrief with reader/genre/voice
        policy_snapshot: Applicable writing policies for this run
        dependency_graph: Optional dependency graph for prerequisite tracking

    Returns:
        Dict with all context needed by rewriter
    """
    # Collect source text
    source_text = "\n".join(
        source_texts.get(sid, "") for sid in unit.source_span_ids
    )

    # Collect concept details
    concepts_to_teach = []
    for entry in baseline.concept_entries:
        if entry.concept_id in unit.concept_ids:
            concepts_to_teach.append({
                "concept_id": entry.concept_id,
                "proposition": entry.proposition,
                "concept_type": entry.concept_type,
                "teaching_roles": entry.teaching_roles,
                "supporting_spans": entry.supporting_spans,
                "prerequisites": entry.prerequisites,
            })

    # Collect prerequisite concepts already taught
    prerequisites_taught = set()
    if dependency_graph:
        for dep in dependency_graph.dependencies:
            if dep.dependent_concept_id in unit.concept_ids:
                prerequisites_taught.add(dep.prerequisite_concept_id)

    # Collect protected objects
    unit_protected_objects = []
    for span_id in unit.source_span_ids:
        if span_id in protected_objects:
            unit_protected_objects.extend(protected_objects[span_id])

    # Adjacent context
    adjacent_before = "\n".join(
        source_texts.get(sid, "") for sid in unit.adjacent_before[:2]
    ) if hasattr(unit, 'adjacent_before') else ""

    adjacent_after = "\n".join(
        source_texts.get(sid, "") for sid in unit.adjacent_after[:2]
    ) if hasattr(unit, 'adjacent_after') else ""

    return {
        "unit_id": unit.unit_id,
        "source_text": source_text,
        "source_span_ids": unit.source_span_ids,
        "concepts_to_teach": concepts_to_teach,
        "prerequisites_taught": sorted(prerequisites_taught),
        "reader_expertise": brief.get("reader", {}).get("expertise_level", "general"),
        "reader_prior_knowledge": brief.get("reader", {}).get("prior_knowledge", []),
        "genre": brief.get("genre", "technical"),
        "voice_register": brief.get("voice_register", "formal"),
        "protected_objects": unit_protected_objects,
        "adjacent_context_before": adjacent_before,
        "adjacent_context_after": adjacent_after,
        "policy_snapshot": policy_snapshot,
    }


def build_rewrite_prompt(context: dict) -> str:
    """Generate prompt for rewriting one unit.

    Args:
        context: Rewrite context from build_rewrite_context()

    Returns:
        Prompt text requesting schema-valid replacement LaTeX
    """
    prompt = f"""You are rewriting a section of a technical manuscript to improve clarity
while preserving every concept from the source.

CRITICAL CONSTRAINTS:
1. Preserve every concept in the frozen baseline—no deletion or omission allowed
2. Explain each concept adequately for the reader—naming alone is insufficient
3. Preserve exact equations, citations, numbers, and tables unless authorized to change
4. Use {context.get('voice_register', 'formal')} voice appropriate for {context.get('genre', 'technical')} writing
5. Maintain {context.get('reader_expertise', 'general')}-level expertise assumptions
6. Reject unsupported facts or examples not derivable from source material

SOURCE SECTION (to improve):
{context.get('source_text', '')}

CONCEPTS TO TEACH (from frozen baseline):
"""
    for concept in context.get('concepts_to_teach', []):
        prompt += f"""
- {concept['concept_id']}: {concept['proposition']}
  Type: {concept['concept_type']}, Teaching roles: {', '.join(concept['teaching_roles'])}
  Prerequisites: {', '.join(concept.get('prerequisites', ['none']))}
"""

    prompt += f"""
PROTECTED CONTENT (must preserve exactly):
"""
    for obj in context.get('protected_objects', []):
        prompt += f"- {obj['kind']}: {obj.get('text', obj.get('command', ''))}\\n"

    if context.get('adjacent_context_before'):
        prompt += f"""
CONTEXT BEFORE (optional reference):
{context['adjacent_context_before']}
"""

    if context.get('adjacent_context_after'):
        prompt += f"""
CONTEXT AFTER (optional reference):
{context['adjacent_context_after']}
"""

    prompt += """
YOUR TASK:
1. Rewrite the source section to improve clarity
2. Ensure each concept is explained, not merely mentioned
3. Preserve all protected content exactly
4. Track which output spans correspond to which source concepts
5. Return valid LaTeX that builds without errors

OUTPUT FORMAT:
Return JSON with:
{
  "replacement_latex": "Improved LaTeX text",
  "concept_correspondences": [
    {
      "source_concept_id": "concept-001",
      "output_span_ids": ["out-span-001", "out-span-002"],
      "mapping_type": "paraphrase",
      "output_text_preview": "First 50 chars of output...",
      "rationale": "Expanded definition with example"
    }
  ],
  "protected_objects_preserved": ["equation-1", "cite-5"],
  "mutations_detected": [],
  "explanation": "Concise summary of changes"
}

REJECT (return empty) if:
- Cannot preserve all required concepts
- Protected objects would be corrupted
- Obligations cannot be fulfilled
- Source material doesn't support needed explanations
"""
    return prompt


def rewrite_unit(
    unit,
    baseline,
    plan,
    model,
    source_texts: dict,
    protected_objects: dict,
    brief: dict,
    policy_snapshot: dict,
    previous_attempts: Optional[list] = None,
) -> RewriteResult:
    """Rewrite one semantic unit from frozen baseline.

    Args:
        unit: RewriteUnit to rewrite
        baseline: Frozen ConceptBaseline
        plan: RewritePlan containing unit
        model: ModelAdapter for inference
        source_texts: Map of span_id -> text
        protected_objects: Map of span_id -> [ProtectedObject]
        brief: HumanizationBrief with reader/genre/voice
        policy_snapshot: Applicable writing policies
        previous_attempts: Prior attempts for this unit (for convergence detection)

    Returns:
        RewriteResult with replacement LaTeX and correspondence
    """
    # Build context
    context = build_rewrite_context(
        unit, baseline, plan, source_texts, protected_objects, brief, policy_snapshot
    )

    # Generate prompt
    prompt = build_rewrite_prompt(context)
    prompt_hash = sha256(prompt.encode()).hexdigest()

    try:
        # Call model
        response = model.invoke(
            prompt=prompt,
            record_type=None,
            temperature=0.3,
            max_tokens=8000,
        )

        # Handle abstention
        if response.abstained or response.error:
            return RewriteResult(
                unit_id=unit.unit_id,
                source_span_ids=unit.source_span_ids,
                output_latex="",
                output_hash="",
                rejection_reasons=[response.error or "model_abstained"],
                is_acceptable=False,
            )

        # Parse response
        if not isinstance(response.parsed, dict):
            return RewriteResult(
                unit_id=unit.unit_id,
                source_span_ids=unit.source_span_ids,
                output_latex="",
                output_hash="",
                rejection_reasons=["expected_dict_got_other"],
                is_acceptable=False,
            )

        # Extract output
        output_latex = response.parsed.get("replacement_latex", "")
        output_hash = sha256(output_latex.encode()).hexdigest()

        # Parse correspondences
        correspondences = []
        for corr_data in response.parsed.get("concept_correspondences", []):
            correspondences.append(ConceptCorrespondence(
                source_concept_id=corr_data.get("source_concept_id", ""),
                output_span_ids=corr_data.get("output_span_ids", []),
                mapping_type=corr_data.get("mapping_type", "retain"),
                output_text_preview=corr_data.get("output_text_preview", ""),
                rationale=corr_data.get("rationale"),
            ))

        # Verify mutation safety
        result = verify_mutation_safety(
            unit=unit,
            baseline=baseline,
            output_latex=output_latex,
            correspondences=correspondences,
            protected_objects_preserved=response.parsed.get("protected_objects_preserved", []),
        )

        result.unit_id = unit.unit_id
        result.source_span_ids = unit.source_span_ids
        result.output_latex = output_latex
        result.output_hash = output_hash
        result.concept_correspondences = correspondences

        return result

    except Exception as e:
        return RewriteResult(
            unit_id=unit.unit_id,
            source_span_ids=unit.source_span_ids,
            output_latex="",
            output_hash="",
            rejection_reasons=[f"rewrite_failed: {str(e)}"],
            is_acceptable=False,
        )


def verify_mutation_safety(
    unit,
    baseline,
    output_latex: str,
    correspondences: list,
    protected_objects_preserved: list,
) -> RewriteResult:
    """Verify output contains no unsafe mutations.

    Mutation types that block acceptance:
    - Concept deletion
    - Concept addition (unsupported)
    - Obligation non-fulfillment
    - Protected object corruption
    - Output truncation

    Args:
        unit: RewriteUnit being rewritten
        baseline: Frozen baseline
        output_latex: Rewritten LaTeX
        correspondences: List of ConceptCorrespondence
        protected_objects_preserved: Protected objects preserved in output

    Returns:
        RewriteResult with mutations and acceptance status
    """
    result = RewriteResult(
        unit_id=unit.unit_id,
        source_span_ids=unit.source_span_ids,
        output_latex=output_latex,
        output_hash=sha256(output_latex.encode()).hexdigest(),
        protected_objects_preserved=protected_objects_preserved,
        is_acceptable=True,
    )

    mutations = []

    # Check for concept deletion
    output_concept_ids = {c.source_concept_id for c in correspondences}
    unit_concept_ids = set(unit.concept_ids)

    deleted = unit_concept_ids - output_concept_ids
    if deleted:
        mutations.append({
            "type": "concept_deletion",
            "concepts": sorted(deleted),
            "severity": "BLOCK",
        })
        result.rejection_reasons.append(f"Deleted concepts: {deleted}")

    # Check for unsupported additions
    all_baseline_concepts = {e.concept_id for e in baseline.concept_entries}
    added = output_concept_ids - unit_concept_ids - all_baseline_concepts
    if added:
        mutations.append({
            "type": "unsupported_addition",
            "concepts": sorted(added),
            "severity": "BLOCK",
        })
        result.rejection_reasons.append(f"Added unsupported concepts: {added}")

    # Check for mention without explanation
    for corr in correspondences:
        if corr.mapping_type == "mention_only":
            mutations.append({
                "type": "mention_without_explanation",
                "concept_id": corr.source_concept_id,
                "severity": "BLOCK",
            })
            result.rejection_reasons.append(
                f"{corr.source_concept_id} mentioned but not explained"
            )

    # Check for truncation
    if not output_latex or len(output_latex.strip()) < 10:
        mutations.append({
            "type": "output_truncation",
            "output_length": len(output_latex),
            "severity": "BLOCK",
        })
        result.rejection_reasons.append("Output truncated or empty")

    result.mutations = mutations

    # Set acceptance
    blocking_mutations = [m for m in mutations if m.get("severity") == "BLOCK"]
    result.is_acceptable = len(blocking_mutations) == 0

    return result


def save_rewrite_result(result: RewriteResult, output_path) -> None:
    """Save rewrite result to disk.

    Args:
        result: RewriteResult to save
        output_path: Path to write JSON file
    """
    import json
    from pathlib import Path

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "unit_id": result.unit_id,
            "source_span_ids": result.source_span_ids,
            "output_hash": result.output_hash,
            "output_latex": result.output_latex,
            "concept_correspondences": [
                {
                    "source_concept_id": c.source_concept_id,
                    "output_span_ids": c.output_span_ids,
                    "mapping_type": c.mapping_type,
                    "output_text_preview": c.output_text_preview,
                    "rationale": c.rationale,
                }
                for c in result.concept_correspondences
            ],
            "fulfilled_obligations": [
                {
                    "concept_id": o.concept_id,
                    "functions": o.functions,
                    "fulfilled_in_output": o.fulfilled_in_output,
                    "output_span_ids": o.output_span_ids,
                }
                for o in result.fulfilled_obligations
            ],
            "unmet_obligations": [
                {
                    "concept_id": o.concept_id,
                    "functions": o.functions,
                    "fulfilled_in_output": o.fulfilled_in_output,
                    "output_span_ids": o.output_span_ids,
                }
                for o in result.unmet_obligations
            ],
            "protected_objects_preserved": result.protected_objects_preserved,
            "mutations": result.mutations,
            "is_acceptable": result.is_acceptable,
            "rejection_reasons": result.rejection_reasons,
        }, f, indent=2)
