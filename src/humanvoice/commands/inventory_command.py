"""
hv inventory - Extract concepts and explanation roles from immutable source.

Implements R25 (complete concept baseline), R26 (frozen baseline), R27 (1.0 retention).
Phase 2: Deterministic concept extraction with bidirectional coverage and human adjudication.
"""

import json
import sys
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone
from typing import Optional

from humanvoice.partition import partition_tree, span_records, verify_partition
from humanvoice.source_map import from_parser_objects, link_objects_to_spans
from humanvoice.protected_objects import extract_protected_objects
from humanvoice.concept_extraction import (
    create_extraction_windows,
    reconcile_duplicates,
    classify_scaffolding,
    surface_ambiguities,
    freeze_baseline,
    ConceptCandidate,
)
from humanvoice.model_extraction import (
    extract_concepts_from_window,
    verify_reconstruction,
    verify_coverage,
)
from humanvoice.model import ModelAdapter
from humanvoice.schemas import SchemaRegistry


def _stable_concept_id(snapshot_id: str, span_id: str, concept_index: int) -> str:
    """Generate stable concept ID from source identity, not model wording."""
    payload = f"{snapshot_id}:{span_id}:{concept_index}"
    return f"concept-{sha256(payload.encode()).hexdigest()[:16]}"


def _default_obligations(concept_type: str, genre: str) -> list[str]:
    """Assign explanation obligations by concept type and genre.

    This is a placeholder. A complete implementation would consult the brief's
    reader.prior_knowledge and exemplars to determine which obligations apply.
    """
    base = ["definition", "motivation"]

    if concept_type in ("mechanism", "derivation"):
        base.extend(["intermediate_steps", "assumptions"])
    elif concept_type in ("claim", "finding"):
        base.extend(["evidence", "qualification"])
    elif concept_type == "distinction":
        base.extend(["contrast", "example"])

    return base


def run(args) -> int:
    """
    Extract concepts and explanation roles from immutable source.

    Exit codes:
      0 - inventory complete, baseline frozen
      3 - invalid input (missing snapshot, incomplete baseline)
      4 - internal error (I/O failure, parser error)
      5 - security violation (path traversal)
    """
    snapshot_dir = args.snapshot.resolve()

    # Check snapshot exists and has manifest
    if not snapshot_dir.exists():
        print(f"Error: Snapshot does not exist: {snapshot_dir}", file=sys.stderr)
        return 3

    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: Snapshot manifest not found: {manifest_path}", file=sys.stderr)
        return 3

    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Manifest is not valid JSON: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"Error: Cannot read manifest: {e}", file=sys.stderr)
        return 4

    snapshot_id = manifest["snapshot_id"]
    source_dir = snapshot_dir / "source"

    if not source_dir.exists():
        print(f"Error: Source directory not found: {source_dir}", file=sys.stderr)
        return 3

    # Phase 1: Deterministic source partitioning
    print(f"Partitioning source tree: {source_dir}", file=sys.stderr)

    # Enumerate .tex files
    tex_files = sorted(source_dir.rglob("*.tex"))
    relative_paths = [str(f.relative_to(source_dir)) for f in tex_files]
    source_hash = manifest.get("source_hash", "unknown")
    run_id = manifest.get("run_id", "unknown-run")
    created_at = datetime.now(timezone.utc).isoformat()

    try:
        by_file, abstentions = partition_tree(source_dir, relative_paths, source_hash)

        # Verify completeness
        for rel_path, spans in by_file.items():
            verify_partition(spans, str(source_dir / rel_path))

        # Calculate totals
        total_spans = sum(len(spans) for spans in by_file.values())
        total_bytes = sum(
            max((s.byte_end for s in spans), default=0) for spans in by_file.values()
        )

        print(f"Partitioned {len(by_file)} files:", file=sys.stderr)
        print(f"  {total_spans} spans covering {total_bytes:,} bytes", file=sys.stderr)
        if abstentions:
            print(f"  {len(abstentions)} abstentions", file=sys.stderr)

    except Exception as e:
        print(f"Error: Source partitioning failed: {e}", file=sys.stderr)
        return 4

    # Phase 2: Link protected objects to spans
    print("Linking protected objects to spans...", file=sys.stderr)

    protected_manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"

    if protected_manifest_path.exists():
        try:
            with open(protected_manifest_path, 'r') as f:
                protected_data = json.load(f)

            # Convert to MappedObject format
            mapped_objects = from_parser_objects(protected_data, source_dir)

            # Link to spans across all files
            all_spans = []
            for spans in by_file.values():
                all_spans.extend(spans)

            links = link_objects_to_spans(mapped_objects, all_spans)

            print(f"Linked {links.total_links} protected objects to spans", file=sys.stderr)
            if links.straddling_objects:
                print(f"  Warning: {len(links.straddling_objects)} objects straddle span boundaries", file=sys.stderr)
                for obj_id in links.straddling_objects[:5]:
                    print(f"    {obj_id}", file=sys.stderr)
                if len(links.straddling_objects) > 5:
                    print(f"    ... and {len(links.straddling_objects) - 5} more", file=sys.stderr)

        except Exception as e:
            print(f"Warning: Protected object linking failed: {e}", file=sys.stderr)
            links = None
    else:
        print("  No protected object manifest found", file=sys.stderr)
        links = None

    # Phase 3: Creating extraction windows
    print("", file=sys.stderr)
    print("Phase 3: Creating extraction windows", file=sys.stderr)

    # Convert spans to dict format for extraction module
    span_dicts = []
    for rel_path, spans in by_file.items():
        for record in span_records(
            spans,
            run_id=run_id,
            snapshot_id=snapshot_id,
            source_hash=source_hash,
            created_at=created_at,
        ):
            span_dicts.append(record)

    windows = create_extraction_windows(span_dicts, window_size=15, overlap=3)
    print(f"  Created {len(windows)} extraction windows", file=sys.stderr)

    # Phase 4: Model-based concept extraction with independent critics
    print("Phase 4: Model-based concept extraction", file=sys.stderr)

    # Load brief if available
    brief_path = snapshot_dir / ".humanvoice" / "brief.json"
    if brief_path.exists():
        with open(brief_path, 'r') as f:
            brief = json.load(f)
    else:
        # Minimal default brief
        brief = {
            "reader": {"expertise_level": "graduate_student"},
            "genre": "technical",
        }

    # Check for model authorization
    model = None
    registry = None

    # Check if mock mode or remote inference authorized
    mock_mode = getattr(args, 'mock', False)
    remote_authorized = brief.get('remote_inference_authorized', False)

    if mock_mode:
        print("  Running in mock mode (no actual model calls)", file=sys.stderr)
        # Create mock model and registry for testing
        from humanvoice.model import ModelAdapter, ModelConfig
        config = ModelConfig.from_profile()
        model = ModelAdapter(
            config=config,
            mock_mode=True,
            snapshot_dir=snapshot_dir,
        )
        registry = SchemaRegistry()
    elif not remote_authorized and 'ANTHROPIC_API_KEY' not in sys.modules.get('os', __import__('os')).environ:
        print("  Warning: No model authorization (brief.remote_inference_authorized=false and no ANTHROPIC_API_KEY)", file=sys.stderr)
        print("  Skipping model extraction", file=sys.stderr)
    else:
        try:
            import os
            from humanvoice.model import ModelAdapter, ModelConfig

            config = ModelConfig.from_profile()
            model = ModelAdapter(
                config=config,
                mock_mode=False,
                snapshot_dir=snapshot_dir,
            )
            registry = SchemaRegistry()
            print(f"  Model adapter ready: {config.model_version}", file=sys.stderr)
        except Exception as e:
            print(f"  Warning: Could not initialize model: {e}", file=sys.stderr)
            print("  Skipping model extraction", file=sys.stderr)

    all_concepts = []
    all_abstentions = []
    all_reconstruction_verdicts = []
    all_coverage_verdicts = []

    if model and registry:
        # Build span_id -> text map by reading source files
        span_texts = {}
        for rel_path, spans in by_file.items():
            source_file = source_dir / rel_path
            try:
                with open(source_file, 'rb') as f:
                    file_bytes = f.read()
                for span_dict in span_dicts:
                    if span_dict['source_file'] == rel_path:
                        span_id = span_dict['record_id']
                        byte_start = span_dict['byte_start']
                        byte_end = span_dict['byte_end']
                        span_texts[span_id] = file_bytes[byte_start:byte_end].decode('utf-8', errors='replace')
            except Exception as e:
                print(f"  Warning: Could not read source file {rel_path}: {e}", file=sys.stderr)

        for i, window in enumerate(windows):
            print(f"  Extracting window {i+1}/{len(windows)} ({len(window.span_ids)} spans)...", file=sys.stderr)

            # Extract concepts from this window
            result = extract_concepts_from_window(
                window=window,
                brief=brief,
                model=model,
                registry=registry,
                span_texts=span_texts,
            )

            if result.abstentions:
                all_abstentions.extend(result.abstentions)
                print(f"    Abstained: {', '.join(result.abstentions)}", file=sys.stderr)
                continue

            if result.concepts:
                print(f"    Extracted {len(result.concepts)} concepts", file=sys.stderr)
                all_concepts.extend(result.concepts)

                # Run independent reconstruction critic
                window_spans = [s for s in span_dicts if s['record_id'] in window.span_ids]
                reconstruction_verdicts = verify_reconstruction(
                    concepts=result.concepts,
                    source_spans=window_spans,
                    model=model,
                )
                all_reconstruction_verdicts.extend(reconstruction_verdicts)

                supported = sum(1 for v in reconstruction_verdicts if v.verdict == "supported")
                contradicted = sum(1 for v in reconstruction_verdicts if v.verdict == "contradicted")
                unresolved = sum(1 for v in reconstruction_verdicts if v.verdict == "unresolved")
                print(f"    Reconstruction: {supported} supported, {contradicted} contradicted, {unresolved} unresolved", file=sys.stderr)

                # Run independent coverage critic
                coverage_verdicts = verify_coverage(
                    spans=window_spans,
                    concepts=result.concepts,
                    model=model,
                )
                all_coverage_verdicts.extend(coverage_verdicts)

                covered = sum(1 for v in coverage_verdicts if v.verdict == "covered")
                gaps = sum(1 for v in coverage_verdicts if v.verdict == "gap")
                print(f"    Coverage: {covered} covered, {gaps} gaps", file=sys.stderr)

        print("", file=sys.stderr)
        print(f"Extraction complete:", file=sys.stderr)
        print(f"  Total concepts extracted: {len(all_concepts)}", file=sys.stderr)
        print(f"  Abstentions: {len(all_abstentions)}", file=sys.stderr)
        print(f"  Reconstruction verdicts: {len(all_reconstruction_verdicts)}", file=sys.stderr)
        print(f"  Coverage verdicts: {len(all_coverage_verdicts)}", file=sys.stderr)
    else:
        print("", file=sys.stderr)
        print("Model extraction skipped (no authorization or initialization failed)", file=sys.stderr)

    # Write intermediate results
    inventory_dir = snapshot_dir / ".humanvoice" / "inventory"
    inventory_dir.mkdir(parents=True, exist_ok=True)

    # Save span records
    spans_path = inventory_dir / "spans.jsonl"
    with open(spans_path, 'w') as f:
        for record in span_dicts:
            json.dump(record, f)
            f.write('\n')

    print(f"", file=sys.stderr)
    print(f"Wrote {total_spans} span records to {spans_path.relative_to(snapshot_dir)}", file=sys.stderr)

    # Save protected object links if available
    if links:
        links_path = inventory_dir / "protected_links.json"
        with open(links_path, 'w') as f:
            json.dump({
                "total_links": links.total_links,
                "span_to_objects": {k: list(v) for k, v in links.span_to_objects.items()},
                "straddling_objects": links.straddling_objects,
            }, f, indent=2)
        print(f"Wrote protected object links to {links_path.relative_to(snapshot_dir)}", file=sys.stderr)

    # Save extraction results if model ran
    if all_concepts:
        concepts_path = inventory_dir / "concepts.jsonl"
        with open(concepts_path, 'w') as f:
            for concept in all_concepts:
                json.dump({
                    "concept_id": concept.concept_id,
                    "proposition": concept.proposition,
                    "concept_type": concept.concept_type,
                    "source_span_ids": concept.source_span_ids,
                    "teaching_roles": concept.teaching_roles,
                    "supporting_spans": concept.supporting_spans,
                    "prerequisites": concept.prerequisites,
                    "confidence": concept.confidence,
                }, f)
                f.write('\n')
        print(f"Wrote {len(all_concepts)} concepts to {concepts_path.relative_to(snapshot_dir)}", file=sys.stderr)

    # Return status based on actual completion
    extraction_status = "not_implemented" if not model else ("complete" if all_concepts else "no_concepts")

    result = {
        "status": "partitioned",
        "snapshot_id": snapshot_id,
        "total_files": len(by_file),
        "total_spans": total_spans,
        "total_bytes": total_bytes,
        "concept_extraction": extraction_status,
        "total_concepts": len(all_concepts),
        "total_abstentions": len(all_abstentions),
    }
    print(json.dumps(result, indent=2))

    # Exit code 0 only when extraction actually completed
    # Exit 3 for incomplete/invalid state (no model, no concepts)
    if not model:
        print("Warning: No model available, extraction skipped", file=sys.stderr)
        return 3  # Invalid: extraction required but not performed

    if not all_concepts:
        print("Warning: Zero concepts extracted", file=sys.stderr)
        return 3  # Invalid: extraction ran but produced nothing

    # Freeze baseline if requested
    if args.freeze:
        print("", file=sys.stderr)
        print("Freezing baseline...", file=sys.stderr)

        # Collect scaffolding candidates (stub for now)
        from humanvoice.concept_extraction import ScaffoldingCandidate
        scaffolding_candidates = []  # TODO: collect actual scaffolding from extraction

        adjudication_date = datetime.now(timezone.utc).isoformat()

        baseline_sig = freeze_baseline(
            snapshot_id=snapshot_id,
            source_hash=source_hash,
            spans=span_dicts,
            concepts=all_concepts,
            scaffolding=scaffolding_candidates,
            adjudicator_id=args.adjudicator,
            adjudication_date=adjudication_date,
        )

        # Save baseline signature
        baseline_path = inventory_dir / "baseline.json"
        with open(baseline_path, 'w') as f:
            json.dump({
                "baseline_id": baseline_sig.baseline_id,
                "baseline_hash": baseline_sig.baseline_hash,
                "snapshot_id": baseline_sig.snapshot_id,
                "source_hash": baseline_sig.source_hash,
                "total_spans": baseline_sig.total_spans,
                "total_concepts": baseline_sig.total_concepts,
                "unresolved_items": baseline_sig.unresolved_items,
                "adjudicator_id": baseline_sig.adjudicator_id,
                "adjudication_date": baseline_sig.adjudication_date,
                "signature_method": baseline_sig.signature_method,
            }, f, indent=2)

        print(f"Baseline frozen: {baseline_sig.baseline_hash[:16]}...", file=sys.stderr)
        print(f"Wrote baseline signature to {baseline_path.relative_to(snapshot_dir)}", file=sys.stderr)

    return 0


if __name__ == '__main__':
    sys.exit(run(None))
