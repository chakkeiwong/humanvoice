# Humanvoice v1.2 Remedy Implementation Plan

**Date:** 2026-08-26  
**Status:** Draft for review  
**Context:** Response to 2026-08-29 pilot failure (protected_correspondence: pass, 0 manifests, 105 missing equations)  
**Foundation:** DynareMCP lessons-learned systematic review  
**Target:** External release with fail-closed correspondence verification

---

## Executive Summary

The 2026-08-29 humanvoice pilot released with all gates reporting "pass" while 105 of 109 equations were missing. This is the same fail-open pattern recorded across ~500 DynareMCP iterations: **honest labeling and workflow compliance replaced objective measurement**.

This plan implements fail-closed correspondence verification for humanvoice v1.2 external release. The core architecture change: **extract protected objects before drafting, route evidence explicitly, verify correspondence at every boundary, block release when gaps detected**.

**Timeline:** 6-8 weeks  
**Scope:** Protected-object extraction, evidence routing, fail-closed gates, assembly verification, repair capability  
**Out of scope:** Full argument-state architecture (requires Stage B pilot), MCTS controller, thesis trajectory checkpoints

---

## Root Cause Analysis

### What Failed

**Observed:** `hv draft` produced 7 section files, gates reported pass, but equations dropped 109→4, labels 168→7.

**Measured causes:**
1. **Evidence truncation:** draft_command.py:122 truncates to 3,000 of 169,097 chars (1.8% coverage, 0 of 109 equations)
2. **Training substitution:** Model generated plausible prose from training, not from source
3. **Fail-open gate:** `protected_correspondence` reported pass with **zero manifests on disk**
4. **No object extraction:** System never parsed source for protected objects before drafting
5. **No correspondence tracking:** No record of which source objects appear where in output

### Why Remedies Will Work This Time

**DynareMCP tried 27+ remedies. Most failed. The ones that worked had these properties:**

1. **Machine-readable schemas** (not prompt text) — artifact-class distinction matrix, valid-tick ledger, stop-certificate schema all improved governance
2. **External validators with veto power** — controller stop validator concept (unimplemented) correctly diagnosed "must continue" invariant
3. **Fail-closed by default** — worked in security gates (T1-T5), failed in research/synthesis gates
4. **Objective measurement not proxy** — "reader understands X now" > "files compiled"
5. **Adversarial regression tests** — only way to prevent failure-mode regression

**This plan implements all five for humanvoice correspondence verification.**

---

## Implementation Phases

### Phase 0: Test Infrastructure (Week 1)

**Purpose:** Adversarial regression tests before implementation, not after.

**Deliverables:**

1. **Baseline fixture:** ZLB HMC survey snapshot with known ground truth
   - Source: `/home/ubuntu/workspace/humanvoice/fixtures/zlb_hmc_survey/`
   - Commit hash, file hash, line count
   - Manual protected-object inventory: 109 equations, 168 labels, 5 display math, 32 sections
   - Store as `fixtures/zlb_hmc_survey/baseline_manifest.json`

2. **Regression test suite:**
   ```python
   # test_correspondence_gates.py
   
   def test_fail_closed_missing_source_manifest():
       """Gate must block when source manifest missing, not pass"""
       snapshot = create_test_snapshot(source_manifest=None)
       result = check_protected_manifest_correspondence(snapshot)
       assert result is not None  # Blocked
       assert result["reason"] == "missing_source_manifest"
   
   def test_fail_closed_missing_draft_manifests():
       """Gate must block when draft manifests missing, not pass"""
       snapshot = create_test_snapshot(draft_manifests=[])
       result = check_protected_manifest_correspondence(snapshot)
       assert result is not None
       assert result["reason"] == "no_draft_manifests"
   
   def test_correspondence_50_percent_loss():
       """Gate must block when 50% of objects missing"""
       snapshot = create_test_snapshot(
           source_objects=100,
           draft_objects=50
       )
       result = check_protected_manifest_correspondence(snapshot)
       assert result is not None
       assert "loss" in result["reason"]
   
   def test_correspondence_95_percent_threshold():
       """Gate must pass when ≥95% objects preserved"""
       snapshot = create_test_snapshot(
           source_objects=109,
           draft_objects=104  # 95.4%
       )
       result = check_protected_manifest_correspondence(snapshot)
       assert result is None  # Pass
   
   def test_assembly_correspondence_regression():
       """Assembly must not lose objects that draft preserved"""
       draft_manifests = [...]  # 104 equations across 7 sections
       assembled = assemble_from_drafts(draft_manifests)
       assembled_objects = extract_protected_objects(assembled)
       assert len(assembled_objects["equations"]) >= 104
   ```

3. **Acceptance criteria:** All 5 tests pass before Phase 1 begins

**Success metric:** Test suite exists and currently **fails** (demonstrating fail-open defect)

### Phase 1: Protected-Object Extraction (Weeks 1-2)

**Purpose:** Parse source before drafting, establish baseline for all downstream checks.

**Implementation:**

1. **New module:** `src/humanvoice/protected_objects.py`

```python
from dataclasses import dataclass
from typing import List, Dict, Optional
from pathlib import Path
import re
from pylatexenc.latexwalker import LatexWalker, LatexEnvironmentNode, LatexMacroNode

@dataclass
class ProtectedObject:
    """Single protected object with provenance"""
    object_type: str  # equation, label, citation, displaymath, table
    content: str
    source_file: Path
    line_number: int
    context_before: str
    context_after: str
    hash: str

@dataclass
class ProtectedManifest:
    """Complete inventory of protected objects in document"""
    source_file: Path
    snapshot_id: str
    extraction_timestamp: str
    equations: List[ProtectedObject]
    labels: List[ProtectedObject]
    citations: List[ProtectedObject]
    displaymath: List[ProtectedObject]
    tables: List[ProtectedObject]
    total_count: int
    extraction_method: str
    
    def to_json(self) -> dict:
        """Serialize for storage"""
        ...
    
    @classmethod
    def from_json(cls, data: dict) -> 'ProtectedManifest':
        """Deserialize from storage"""
        ...

def extract_protected_objects(source_path: Path) -> ProtectedManifest:
    """
    Parse LaTeX source and extract all protected objects.
    
    Uses pylatexenc for equation environments, regex for labels/citations.
    Records line numbers and context for correspondence tracking.
    """
    content = source_path.read_text()
    lines = content.split('\n')
    
    equations = []
    labels = []
    citations = []
    displaymath = []
    tables = []
    
    # Parse with pylatexenc for equation environments
    walker = LatexWalker(content)
    nodelist, pos, len_ = walker.get_latex_nodes()
    
    for node in nodelist:
        if isinstance(node, LatexEnvironmentNode):
            if node.environmentname in ['equation', 'align', 'gather', 'multline']:
                line_num = content[:node.pos].count('\n') + 1
                obj = ProtectedObject(
                    object_type='equation',
                    content=content[node.pos:node.pos+node.len],
                    source_file=source_path,
                    line_number=line_num,
                    context_before=_get_context(lines, line_num, before=2),
                    context_after=_get_context(lines, line_num, after=2),
                    hash=_compute_hash(content[node.pos:node.pos+node.len])
                )
                equations.append(obj)
            elif node.environmentname == 'displaymath':
                # Similar extraction
                displaymath.append(...)
            elif node.environmentname in ['table', 'tabular']:
                tables.append(...)
    
    # Parse labels with regex
    for match in re.finditer(r'\\label\{([^}]+)\}', content):
        line_num = content[:match.start()].count('\n') + 1
        obj = ProtectedObject(
            object_type='label',
            content=match.group(1),
            source_file=source_path,
            line_number=line_num,
            context_before=_get_context(lines, line_num, before=1),
            context_after=_get_context(lines, line_num, after=1),
            hash=_compute_hash(match.group(1))
        )
        labels.append(obj)
    
    # Parse citations
    for match in re.finditer(r'\\cite[tp]?\{([^}]+)\}', content):
        # Similar extraction
        citations.append(...)
    
    return ProtectedManifest(
        source_file=source_path,
        snapshot_id=_get_snapshot_id(),
        extraction_timestamp=datetime.now().isoformat(),
        equations=equations,
        labels=labels,
        citations=citations,
        displaymath=displaymath,
        tables=tables,
        total_count=len(equations) + len(labels) + len(citations) + len(displaymath) + len(tables),
        extraction_method="pylatexenc_v2.10_plus_regex"
    )

def _get_context(lines: List[str], line_num: int, before: int = 0, after: int = 0) -> str:
    """Extract surrounding lines for context"""
    start = max(0, line_num - before - 1)
    end = min(len(lines), line_num + after)
    return '\n'.join(lines[start:end])

def _compute_hash(content: str) -> str:
    """Compute stable hash for object content"""
    import hashlib
    normalized = re.sub(r'\s+', ' ', content).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]
```

2. **Integration with init command:**

```python
# In init_command.py, after source file is copied:

def run(args):
    # ... existing init logic ...
    
    # Extract protected objects from source
    source_path = snapshot_dir / args.source
    logger.info(f"Extracting protected objects from {source_path}")
    
    manifest = extract_protected_objects(source_path)
    manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest.to_json(), indent=2))
    
    logger.info(f"Extracted {manifest.total_count} protected objects:")
    logger.info(f"  Equations: {len(manifest.equations)}")
    logger.info(f"  Labels: {len(manifest.labels)}")
    logger.info(f"  Citations: {len(manifest.citations)}")
    logger.info(f"  Display math: {len(manifest.displaymath)}")
    logger.info(f"  Tables: {len(manifest.tables)}")
    
    # Store manifest path in snapshot metadata
    metadata["source_protected_manifest"] = str(manifest_path.relative_to(snapshot_dir))
    
    # ... rest of init logic ...
```

**Deliverables:**
- `protected_objects.py` with extraction logic
- Integration in `init_command.py`
- `source_manifest.json` generated for test fixture
- Unit tests for extraction accuracy (spot-check ZLB survey: must find 109 equations)

**Success metric:** Extraction finds ≥95% of manually inventoried objects in test fixture

### Phase 2: Evidence Routing for Draft (Weeks 2-3)

**Purpose:** Replace 3,000-char truncation with targeted evidence per section.

**Current defect in draft_command.py:**
```python
# Line 122: WRONG
{evidence_content[:3000]}
{"...(truncated for length)" if len(evidence_content) > 3000 else ""}
```

**Remedy architecture:**

1. **Load source manifest before drafting:**

```python
def _load_source_manifest(snapshot_dir: Path) -> ProtectedManifest:
    """Load protected objects from source"""
    manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Source manifest missing: {manifest_path}. Run hv init first.")
    return ProtectedManifest.from_json(json.loads(manifest_path.read_text()))
```

2. **Route protected objects to section context:**

```python
def _prepare_section_evidence(
    section: dict,
    source_content: str,
    source_manifest: ProtectedManifest,
    evidence_files: List[Path]
) -> dict:
    """
    Prepare evidence for one section, including:
    - Targeted source excerpt (not full source)
    - Protected objects relevant to this section
    - Evidence file content if applicable
    """
    
    # Determine which protected objects are relevant to this section
    # Heuristic: objects whose line numbers fall within section boundaries
    section_start = section.get('source_start_line', 0)
    section_end = section.get('source_end_line', float('inf'))
    
    relevant_equations = [
        eq for eq in source_manifest.equations
        if section_start <= eq.line_number <= section_end
    ]
    relevant_labels = [
        lb for lb in source_manifest.labels
        if section_start <= lb.line_number <= section_end
    ]
    relevant_citations = [
        ct for ct in source_manifest.citations
        if section_start <= ct.line_number <= section_end
    ]
    
    # Extract targeted source excerpt
    source_lines = source_content.split('\n')
    if section_start > 0 and section_end < float('inf'):
        # Section boundaries known, use them
        excerpt = '\n'.join(source_lines[section_start-1:section_end])
    else:
        # Boundaries unknown, use full source (degraded mode)
        # TODO: Add section boundary detection
        excerpt = source_content
    
    # Build evidence package
    evidence = {
        'source_excerpt': excerpt,
        'excerpt_char_count': len(excerpt),
        'protected_objects': {
            'equations': [
                {
                    'content': eq.content,
                    'line': eq.line_number,
                    'hash': eq.hash,
                    'context': eq.context_before + '\n' + eq.context_after
                }
                for eq in relevant_equations
            ],
            'labels': [
                {'content': lb.content, 'line': lb.line_number, 'hash': lb.hash}
                for lb in relevant_labels
            ],
            'citations': [
                {'content': ct.content, 'line': ct.line_number, 'hash': ct.hash}
                for ct in relevant_citations
            ]
        },
        'evidence_files': _load_evidence_content(evidence_files)  # Existing logic
    }
    
    return evidence
```

3. **Update draft prompt to emphasize protected objects:**

```python
# In _draft_section, replace truncation with routed evidence
evidence = _prepare_section_evidence(section, source_content, source_manifest, evidence_files)

prompt = f"""You are drafting section {section_index+1} of {len(sections)} for a LaTeX document.

Section title: {section.get('title', 'Untitled')}
Section brief: {section.get('brief', 'No brief provided')}

CRITICAL: This section must preserve the following protected objects from the source:

Equations ({len(evidence['protected_objects']['equations'])}):
{_format_protected_objects(evidence['protected_objects']['equations'])}

Labels ({len(evidence['protected_objects']['labels'])}):
{_format_protected_objects(evidence['protected_objects']['labels'])}

Citations ({len(evidence['protected_objects']['citations'])}):
{_format_protected_objects(evidence['protected_objects']['citations'])}

Source excerpt for this section:
{evidence['source_excerpt']}

Evidence files:
{evidence['evidence_files']}

Your draft must include ALL equations, labels, and citations listed above. Do not generate plausible-sounding alternatives from your training. If you cannot determine how to incorporate a protected object, include it verbatim with a comment explaining the uncertainty.

Generate a complete LaTeX document section."""
```

4. **Emit draft manifest after generation:**

```python
def _emit_draft_manifest(
    draft_content: str,
    section: dict,
    run_dir: Path,
    source_manifest: ProtectedManifest
) -> Path:
    """
    Extract protected objects from generated draft and record manifest.
    This enables correspondence checking.
    """
    draft_manifest = extract_protected_objects_from_text(
        content=draft_content,
        source_file=run_dir / "draft.tex"  # Temporary path for provenance
    )
    
    manifest_path = run_dir / "draft_manifest.json"
    manifest_path.write_text(json.dumps(draft_manifest.to_json(), indent=2))
    
    return manifest_path
```

**Deliverables:**
- Modified `draft_command.py` with evidence routing
- Draft manifest emission per section
- Updated prompt template
- Integration test: draft ZLB survey sections, verify manifests show ≥95% equation retention

**Success metric:** Test fixture draft produces 7 draft manifests with combined ≥104 equations

### Phase 3: Fail-Closed Correspondence Gate (Week 3-4)

**Purpose:** Rewrite `check_protected_manifest_correspondence()` to block when evidence missing or gap detected.

**Current defect in release_command.py:**
```python
# WRONG: No check if runs_dir exists or contains manifests
# If missing, gate passes silently
```

**Remedy implementation:**

```python
def check_protected_manifest_correspondence(snapshot_dir: Path) -> Optional[dict]:
    """
    Verify protected objects from source appear in drafts and assembly.
    
    Returns None if pass (no block).
    Returns block dict with reason/detail if fail.
    
    FAIL-CLOSED: Blocks when:
    - Source manifest missing (init didn't run or failed)
    - Draft manifests missing (draft didn't emit them)
    - Assembly manifest missing (assemble didn't verify)
    - Gap >5% between source and final output
    """
    
    # Check 1: Source manifest must exist
    source_manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
    if not source_manifest_path.exists():
        return {
            "reason": "missing_source_manifest",
            "detail": f"Source protected manifest not found: {source_manifest_path}. Cannot verify correspondence without baseline."
        }
    
    source_manifest = ProtectedManifest.from_json(json.loads(source_manifest_path.read_text()))
    
    # Check 2: Draft manifests must exist
    runs_dir = snapshot_dir / ".humanvoice" / "runs"
    if not runs_dir.exists():
        return {
            "reason": "no_draft_runs",
            "detail": f"Runs directory not found: {runs_dir}. Draft command must complete before release."
        }
    
    draft_manifests = list(runs_dir.glob("*/draft_manifest.json"))
    if len(draft_manifests) == 0:
        return {
            "reason": "no_draft_manifests",
            "detail": f"No draft manifests found in {runs_dir}. Draft command must emit manifest per section."
        }
    
    # Check 3: Assembly manifest must exist
    assembly_manifest_path = snapshot_dir / ".humanvoice" / "revisions" / "assembled" / "assembly_correspondence_manifest.json"
    if not assembly_manifest_path.exists():
        return {
            "reason": "missing_assembly_correspondence",
            "detail": f"Assembly correspondence manifest not found: {assembly_manifest_path}. Assemble command must verify correspondence."
        }
    
    assembly_manifest = json.loads(assembly_manifest_path.read_text())
    
    # Check 4: Measure correspondence gap
    source_count = source_manifest.total_count
    assembled_count = assembly_manifest["total_protected_objects"]
    
    if assembled_count < source_count * 0.95:
        loss_count = source_count - assembled_count
        loss_pct = (loss_count / source_count) * 100
        
        return {
            "reason": "correspondence_gap_exceeds_threshold",
            "detail": f"Protected object loss: {loss_count} of {source_count} ({loss_pct:.1f}%). Threshold: 5%. Assembly must preserve ≥95% of source objects.",
            "gap_analysis": {
                "source_total": source_count,
                "assembled_total": assembled_count,
                "loss_count": loss_count,
                "loss_percentage": loss_pct,
                "by_type": assembly_manifest.get("gap_by_type", {})
            }
        }
    
    # Check 5: Verify manifest integrity (not just counts)
    integrity_check = _verify_manifest_integrity(source_manifest, assembly_manifest)
    if integrity_check is not None:
        return integrity_check
    
    # All checks passed
    return None

def _verify_manifest_integrity(source_manifest: ProtectedManifest, assembly_manifest: dict) -> Optional[dict]:
    """
    Verify that correspondence manifest contains actual mappings, not just counts.
    Prevents "reported 104 equations but mapping is empty" failure.
    """
    if "object_mappings" not in assembly_manifest:
        return {
            "reason": "correspondence_manifest_incomplete",
            "detail": "Assembly manifest missing object_mappings. Cannot verify correspondence without mappings."
        }
    
    mappings = assembly_manifest["object_mappings"]
    
    # Spot-check: verify some source objects appear in mappings
    sample_size = min(10, len(source_manifest.equations))
    sample_equations = source_manifest.equations[:sample_size]
    
    mapped_count = 0
    for eq in sample_equations:
        if eq.hash in mappings.get("equations", {}):
            mapped_count += 1
    
    if mapped_count < sample_size * 0.9:
        return {
            "reason": "correspondence_mapping_incomplete",
            "detail": f"Spot check: {mapped_count} of {sample_size} sample equations found in mappings. Correspondence manifest may be invalid."
        }
    
    return None
```

**Integration with release gate wiring:**

```python
# In run() function of release_command.py

# Replace existing protected_correspondence check:
correspondence_block = check_protected_manifest_correspondence(snapshot_dir)
if correspondence_block:
    blocks.append({
        "gate": "protected_correspondence",
        "never_except": True,
        "detail": correspondence_block
    })
    gate_results["protected_correspondence"] = "blocked"
else:
    gate_results["protected_correspondence"] = "pass"
```

**Deliverables:**
- Rewritten `check_protected_manifest_correspondence()`
- Unit tests for all 5 failure modes
- Integration test: release with missing manifest must block
- Integration test: release with 50% loss must block
- Integration test: release with 96% retention must pass

**Success metric:** All Phase 0 regression tests pass

### Phase 4: Assembly Correspondence Verification (Weeks 4-5)

**Purpose:** Verify assembly step doesn't lose objects that draft preserved.

**Current defect in assemble_command.py:**
- Assembly concatenates sections but doesn't verify object preservation
- No correspondence tracking from draft → assembled

**Remedy implementation:**

1. **Load draft manifests during assembly:**

```python
def _load_draft_manifests(runs_dir: Path) -> List[ProtectedManifest]:
    """Load all draft manifests to establish correspondence baseline"""
    manifest_paths = sorted(runs_dir.glob("*/draft_manifest.json"))
    
    manifests = []
    for path in manifest_paths:
        manifest_data = json.loads(path.read_text())
        manifests.append(ProtectedManifest.from_json(manifest_data))
    
    return manifests

def _merge_draft_manifests(manifests: List[ProtectedManifest]) -> ProtectedManifest:
    """Combine draft manifests into expected assembly baseline"""
    merged = ProtectedManifest(
        source_file=Path("merged_drafts"),
        snapshot_id=manifests[0].snapshot_id if manifests else "",
        extraction_timestamp=datetime.now().isoformat(),
        equations=[],
        labels=[],
        citations=[],
        displaymath=[],
        tables=[],
        total_count=0,
        extraction_method="merged_from_draft_manifests"
    )
    
    for manifest in manifests:
        merged.equations.extend(manifest.equations)
        merged.labels.extend(manifest.labels)
        merged.citations.extend(manifest.citations)
        merged.displaymath.extend(manifest.displaymath)
        merged.tables.extend(manifest.tables)
    
    merged.total_count = (
        len(merged.equations) + len(merged.labels) + len(merged.citations) +
        len(merged.displaymath) + len(merged.tables)
    )
    
    return merged
```

2. **Verify assembled document after generation:**

```python
def run(args):
    # ... existing assembly logic ...
    
    # After assembled document is written:
    assembled_path = output_dir / assembled_filename
    assembled_content = assembled_path.read_text()
    
    # Load expected baseline from draft manifests
    runs_dir = snapshot_dir / ".humanvoice" / "runs"
    draft_manifests = _load_draft_manifests(runs_dir)
    expected_baseline = _merge_draft_manifests(draft_manifests)
    
    # Extract protected objects from assembled document
    logger.info("Verifying correspondence in assembled document...")
    assembled_manifest = extract_protected_objects_from_text(
        content=assembled_content,
        source_file=assembled_path
    )
    
    # Compare assembled vs expected
    correspondence_report = _generate_correspondence_report(
        expected=expected_baseline,
        actual=assembled_manifest
    )
    
    # Write correspondence manifest
    correspondence_manifest_path = output_dir / "assembly_correspondence_manifest.json"
    correspondence_manifest_path.write_text(
        json.dumps(correspondence_report, indent=2)
    )
    
    # Check for assembly loss
    if correspondence_report["loss_percentage"] > 1.0:  # 1% threshold for assembly
        logger.error(f"Assembly correspondence check FAILED:")
        logger.error(f"  Expected: {correspondence_report['expected_total']} objects")
        logger.error(f"  Found: {correspondence_report['actual_total']} objects")
        logger.error(f"  Loss: {correspondence_report['loss_count']} ({correspondence_report['loss_percentage']:.1f}%)")
        logger.error(f"  Correspondence manifest: {correspondence_manifest_path}")
        
        # Block assembly completion
        raise ValueError(
            f"Assembly correspondence verification failed. "
            f"{correspondence_report['loss_count']} objects lost during assembly. "
            f"See {correspondence_manifest_path} for details."
        )
    
    logger.info(f"Assembly correspondence verified: {correspondence_report['actual_total']}/{correspondence_report['expected_total']} objects preserved")
    
    # ... rest of assembly logic ...
```

3. **Correspondence report structure:**

```python
def _generate_correspondence_report(
    expected: ProtectedManifest,
    actual: ProtectedManifest
) -> dict:
    """
    Compare expected vs actual protected objects.
    Returns detailed gap analysis.
    """
    
    # Build hash sets for efficient matching
    expected_eq_hashes = {eq.hash for eq in expected.equations}
    actual_eq_hashes = {eq.hash for eq in actual.equations}
    
    expected_label_hashes = {lb.hash for lb in expected.labels}
    actual_label_hashes = {lb.hash for lb in actual.labels}
    
    expected_cite_hashes = {ct.hash for ct in expected.citations}
    actual_cite_hashes = {ct.hash for ct in actual.citations}
    
    # Compute gaps
    missing_equations = expected_eq_hashes - actual_eq_hashes
    missing_labels = expected_label_hashes - actual_label_hashes
    missing_citations = expected_cite_hashes - actual_cite_hashes
    
    # Build object mappings (source hash → assembled location)
    object_mappings = {
        "equations": {},
        "labels": {},
        "citations": {}
    }
    
    for eq in actual.equations:
        if eq.hash in expected_eq_hashes:
            object_mappings["equations"][eq.hash] = {
                "content": eq.content,
                "line": eq.line_number,
                "status": "preserved"
            }
    
    for eq_hash in missing_equations:
        # Find original object to report what's missing
        original = next((eq for eq in expected.equations if eq.hash == eq_hash), None)
        if original:
            object_mappings["equations"][eq_hash] = {
                "content": original.content,
                "line": original.line_number,
                "status": "missing"
            }
    
    # Similar for labels, citations...
    
    total_expected = expected.total_count
    total_actual = actual.total_count
    loss_count = total_expected - total_actual
    loss_pct = (loss_count / total_expected * 100) if total_expected > 0 else 0
    
    return {
        "expected_total": total_expected,
        "actual_total": total_actual,
        "loss_count": max(0, loss_count),
        "loss_percentage": max(0, loss_pct),
        "gap_by_type": {
            "equations": {
                "expected": len(expected.equations),
                "actual": len(actual.equations),
                "missing": len(missing_equations)
            },
            "labels": {
                "expected": len(expected.labels),
                "actual": len(actual.labels),
                "missing": len(missing_labels)
            },
            "citations": {
                "expected": len(expected.citations),
                "actual": len(actual.citations),
                "missing": len(missing_citations)
            }
        },
        "object_mappings": object_mappings,
        "total_protected_objects": total_actual
    }
```

**Deliverables:**
- Assembly correspondence verification in `assemble_command.py`
- `assembly_correspondence_manifest.json` generation
- Assembly blocks when loss > 1% during concatenation
- Unit tests for assembly verification
- Integration test: assemble ZLB survey sections, verify manifest shows ≥104 equations

**Success metric:** Assembly of test fixture produces correspondence manifest showing <1% loss

### Phase 5: Repair Command (Weeks 5-6, Stretch Goal)

**Purpose:** When gaps detected, attempt targeted restoration before blocking release.

**Architecture:**

```python
# src/humanvoice/commands/repair_command.py

def run(args):
    """
    Repair correspondence gaps in drafted document.
    
    Usage: hv repair <snapshot> --gap-manifest <path> --budget <N>
    
    Reads gap manifest from correspondence check.
    For each missing object, attempts targeted re-draft with focused evidence.
    Counts only operations that reduce gap (substantive operations).
    Stops when gap < threshold, budget exhausted, or gap not reducing.
    """
    
    snapshot_dir = _resolve_snapshot(args.snapshot)
    gap_manifest_path = Path(args.gap_manifest)
    budget = args.budget or 10  # Default 10 repair iterations
    
    # Load gap analysis
    gap_manifest = json.loads(gap_manifest_path.read_text())
    missing_objects = _extract_missing_objects(gap_manifest)
    
    logger.info(f"Repair command starting:")
    logger.info(f"  Missing objects: {len(missing_objects)}")
    logger.info(f"  Repair budget: {budget} iterations")
    
    # Load source manifest for evidence routing
    source_manifest = _load_source_manifest(snapshot_dir)
    source_content = _load_source_content(snapshot_dir)
    
    # Repair loop
    operations_log = []
    gap_reduction_log = []
    
    for iteration in range(budget):
        if len(missing_objects) == 0:
            logger.info(f"All objects restored after {iteration} iterations")
            break
        
        # Select highest-priority missing object
        target_object = _select_repair_target(missing_objects)
        
        # Attempt targeted restoration
        logger.info(f"Iteration {iteration+1}: Restoring {target_object['type']} {target_object['hash'][:8]}...")
        
        repair_result = _attempt_repair(
            target_object=target_object,
            source_manifest=source_manifest,
            source_content=source_content,
            snapshot_dir=snapshot_dir
        )
        
        operations_log.append({
            "iteration": iteration + 1,
            "target": target_object,
            "result": repair_result["status"],
            "gap_before": len(missing_objects),
            "gap_after": repair_result["gap_after"]
        })
        
        # Update missing objects list
        if repair_result["status"] == "restored":
            missing_objects = [obj for obj in missing_objects if obj["hash"] != target_object["hash"]]
            gap_reduction_log.append(1)
        else:
            gap_reduction_log.append(0)
        
        # Check if gap is reducing
        if len(gap_reduction_log) >= 3:
            recent_reductions = sum(gap_reduction_log[-3:])
            if recent_reductions == 0:
                logger.warning("Gap not reducing in last 3 iterations. Stopping repair loop.")
                break
    
    # Write repair manifest
    repair_manifest = {
        "repair_timestamp": datetime.now().isoformat(),
        "initial_gap": len(_extract_missing_objects(gap_manifest)),
        "final_gap": len(missing_objects),
        "operations_attempted": len(operations_log),
        "operations_successful": sum(gap_reduction_log),
        "budget_used": len(operations_log),
        "budget_total": budget,
        "operations_log": operations_log
    }
    
    repair_manifest_path = snapshot_dir / ".humanvoice" / "repair" / f"repair_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    repair_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    repair_manifest_path.write_text(json.dumps(repair_manifest, indent=2))
    
    logger.info(f"Repair complete:")
    logger.info(f"  Operations attempted: {len(operations_log)}")
    logger.info(f"  Operations successful: {sum(gap_reduction_log)}")
    logger.info(f"  Remaining gap: {len(missing_objects)}")
    logger.info(f"  Repair manifest: {repair_manifest_path}")
    
    if len(missing_objects) > 0:
        logger.error(f"Repair failed to close gap. {len(missing_objects)} objects still missing.")
        logger.error("Manual intervention required or budget increase needed.")
        return 1  # Exit code: repair failed
    
    return 0  # Success

def _attempt_repair(
    target_object: dict,
    source_manifest: ProtectedManifest,
    source_content: str,
    snapshot_dir: Path
) -> dict:
    """
    Attempt to restore one missing protected object.
    
    Strategy:
    1. Find section where object should appear (from source line number)
    2. Re-draft that section with focused prompt emphasizing target object
    3. Verify target object appears in re-draft
    4. If successful, update section file; if not, log failure
    """
    # Implementation similar to draft command but targeted
    ...
    
    return {
        "status": "restored" | "failed",
        "gap_after": ...  # Count after this repair attempt
    }
```

**Deliverables:**
- `repair_command.py` with substantive operation counting
- Integration with CLI (`hv repair`)
- Repair manifest emission
- Integration test: introduce artificial gap, verify repair reduces it

**Success metric:** Repair command restores ≥80% of artificially introduced gaps within budget

### Phase 6: Documentation and Release (Weeks 6-8)

**Purpose:** User-facing documentation, release notes, migration guide.

**Deliverables:**

1. **User documentation:**
   - Updated README with correspondence verification explanation
   - New section: "How humanvoice verifies fidelity"
   - Manifest inspection guide for users

2. **Migration guide:**
   - Snapshots from v1.1 (pre-verification) won't have manifests
   - Users must re-init or manually create baseline manifests
   - Clear steps for migration

3. **Release notes:**
   ```markdown
   # Humanvoice v1.2 Release Notes
   
   ## Critical Fixes
   
   - **FIXED: Fail-open correspondence gate** (issue #29, 2026-08-29 pilot)
     - Previous: `protected_correspondence` could report pass with zero manifests
     - Now: Gate blocks when manifests missing or gap >5%
     - Evidence: Every release includes inspectable correspondence manifest
   
   - **FIXED: Evidence truncation in draft** (issue #29)
     - Previous: Draft used 3,000 of 169,097 chars (1.8% coverage)
     - Now: Targeted evidence routing per section with protected-object awareness
     - Result: Equation retention improved from 4/109 (3.7%) to ≥104/109 (≥95%)
   
   ## New Features
   
   - Protected-object extraction at init (equations, labels, citations, display math, tables)
   - Draft manifest emission per section
   - Assembly correspondence verification
   - Fail-closed correspondence gate with detailed gap reports
   - Repair command for gap restoration (experimental)
   
   ## Breaking Changes
   
   - Snapshots require source manifest (generated by `hv init`)
   - Release blocks when correspondence gap >5% (was silent pass)
   - Assembly blocks when loss >1% during concatenation (was silent continue)
   
   ## Upgrade Path
   
   Existing snapshots from v1.1 must be re-initialized to generate manifests:
   
   ```bash
   # Back up existing snapshot
   cp -r .humanvoice/snapshots/20260829_143022 ~/.humanvoice_backup/
   
   # Re-initialize (preserves source file)
   hv init paper.tex --brief "..." --force
   
   # Now manifests will be generated and gates will verify correspondence
   ```
   
   ## Verification
   
   All releases now include inspectable correspondence manifests:
   
   - `source_manifest.json` — Protected objects in source
   - `draft_manifest.json` — Per section (in runs/)
   - `assembly_correspondence_manifest.json` — Final verification
   
   Users can inspect these to verify fidelity.
   ```

4. **Regression test documentation:**
   - How to run test suite
   - How to add new adversarial fixtures
   - Continuous integration setup

5. **Known limitations:**
   - Protected-object extraction relies on pylatexenc + regex (may miss exotic LaTeX)
   - Section boundary detection is heuristic (user must provide in plan or defaults to full source)
   - Repair command is experimental (budget tuning needed)
   - Correspondence threshold (95%) is configurable but not yet exposed in CLI

**Success criteria for v1.2 release:**

| Gate | Test | Status Required |
|------|------|-----------------|
| Protected-object extraction | ZLB HMC survey (109 equations) | ≥104 found (≥95%) |
| Draft evidence routing | 7 sections drafted | Draft manifests show ≥104 total |
| Assembly verification | Sections assembled | Assembly manifest shows ≥104 |
| Fail-closed correspondence | Release with gap | BLOCKED (exit 1) |
| Fail-closed missing manifest | Release without manifests | BLOCKED (exit 1) |
| Regression suite | All Phase 0 tests | PASS |
| Documentation | User guide + API docs | Complete |

**Release approval:** All 7 criteria met, user review complete, external testing on ≥2 additional fixtures.

---

## Timeline and Resource Allocation

### Weekly Breakdown

**Week 1:**
- Phase 0: Test infrastructure (regression suite, baseline fixture)
- Phase 1 start: Protected-object extraction module

**Week 2:**
- Phase 1 complete: Extraction integrated with init command
- Phase 2 start: Evidence routing for draft

**Week 3:**
- Phase 2 complete: Draft emits manifests
- Phase 3 start: Fail-closed correspondence gate

**Week 4:**
- Phase 3 complete: Gates block on missing/gap
- Phase 4 start: Assembly correspondence verification

**Week 5:**
- Phase 4 complete: Assembly blocks on loss
- Phase 5 start: Repair command (stretch)

**Week 6:**
- Phase 5 complete: Repair capability working
- Phase 6 start: Documentation

**Week 7:**
- Documentation complete
- Integration testing on additional fixtures
- Bug fixes

**Week 8:**
- Final testing
- Release candidate
- External review
- v1.2 release

### Critical Path

```
Phase 0 (tests) → Phase 1 (extraction) → Phase 2 (routing) → Phase 3 (gates) → Phase 4 (assembly) → Phase 6 (docs) → Release
                                                                                   ↓
                                                                            Phase 5 (repair, parallel)
```

Phases 0-4 and 6 are critical path (6 weeks minimum).
Phase 5 (repair) is stretch goal, can proceed in parallel with Phase 6 if time permits.

### Risk Buffer

- 2 weeks buffer in 8-week timeline
- If Phases 1-4 take longer, Phase 5 can be deferred to v1.3
- Minimum viable v1.2: Phases 0-4 + 6 (correspondence verification without repair)

---

## Success Metrics and Acceptance Criteria

### Quantitative Metrics

1. **Extraction accuracy:** ≥95% of manually inventoried objects found
2. **Draft retention:** ≥95% of source objects appear in draft manifests
3. **Assembly preservation:** ≥99% of draft objects appear in assembled manifest
4. **Regression test pass rate:** 100% of Phase 0 tests pass
5. **False positive rate:** <1% (gates block when should pass)
6. **False negative rate:** 0% (gates never pass when should block)

### Qualitative Criteria

1. **Fail-closed by default:** All new gates block on ambiguity, never pass silently
2. **Evidence transparency:** User can inspect manifests and verify correspondence
3. **Clear gap reports:** When blocked, user sees exactly what's missing and where
4. **Actionable errors:** Error messages include next steps (re-init, repair, manual inspection)
5. **Non-regression:** All existing v1.1 functionality preserved (init, draft, assemble, preflight, repair, release)

### Acceptance Tests (External Review)

Before v1.2 release, external reviewer must verify:

1. **Install fresh:** `pip install humanvoice==1.2.0` on clean environment
2. **Run ZLB HMC fixture:** `hv init → draft → assemble → release`
3. **Verify manifests exist:** Check `.humanvoice/protected_objects/` for all manifests
4. **Inspect correspondence:** Review `assembly_correspondence_manifest.json`
5. **Verify retention:** Confirm ≥104/109 equations preserved
6. **Introduce artificial gap:** Delete equation from draft, verify assembly blocks
7. **Test repair:** Run `hv repair`, verify gap reduces
8. **Review documentation:** Confirm user guide explains correspondence verification

Acceptance: Reviewer confirms all 8 steps complete successfully.

---

## Rollback Plan

### If v1.2 Implementation Fails

**Criteria for rollback:**
- Regression test pass rate <90% by Week 4
- Extraction accuracy <80% on test fixtures
- Critical bug affecting existing v1.1 functionality
- Timeline extends beyond 10 weeks

**Rollback procedure:**
1. Revert to v1.1 codebase (tag `v1.1.0`)
2. Document failure mode in lessons-learned
3. Re-scope v1.2 to smaller increment (e.g., only Phase 1+2, defer gates)
4. Plan v1.2a (incremental) + v1.3 (full correspondence)

### If v1.2 Releases With Defects

**Post-release defect handling:**

1. **Severity 1 (fail-open regression):**
   - Immediate patch release (v1.2.1)
   - Rollback to v1.1 if patch requires >3 days
   - Post-mortem on how regression escaped testing

2. **Severity 2 (false positive blocks):**
   - Emergency override CLI flag (`--skip-correspondence-check`, logged and warned)
   - Patch release within 1 week
   - User communication: which scenarios trigger false positive

3. **Severity 3 (false negative passes):**
   - Patch release within 2 weeks
   - Add regression fixture for missed case
   - User advisory: how to manually verify correspondence

---

## Maintenance and Monitoring

### Post-Release Monitoring (First 3 Months)

1. **User reports:**
   - Track false positive/negative rates from GitHub issues
   - Monitor extraction accuracy across diverse LaTeX styles
   - Collect fixtures where correspondence verification fails

2. **Performance:**
   - Extraction time for various document sizes
   - Draft time overhead from evidence routing
   - Assembly verification time

3. **Usability:**
   - Frequency of manual overrides
   - Frequency of repair command usage
   - User confusion around manifests/correspondence concepts

### Maintenance Commitments

1. **Security updates:**
   - Monitor pylatexenc for vulnerabilities
   - Keep extraction dependencies up-to-date

2. **Compatibility:**
   - Test against new LaTeX packages
   - Test against exotic equation environments
   - Maintain compatibility with v1.1 snapshots

3. **Documentation:**
   - Add FAQ entries based on user questions
   - Update examples with real-world fixtures
   - Maintain migration guide for v1.1 → v1.2

---

## Lessons Applied From DynareMCP

This implementation plan directly addresses the DynareMCP failure patterns:

| DynareMCP Failure | Humanvoice Remedy |
|-------------------|-------------------|
| Document assembly outranked argument construction | Protected-object extraction before drafting (Phase 1) |
| Fail-open gates with missing evidence | Fail-closed by default (Phase 3) |
| Proxy compliance replaced objective measurement | Correspondence manifests measure actual objects, not file existence (Phases 2, 4) |
| Honest failure labels as escape hatches | Gates block on gaps, repair command attempts restoration (Phases 3, 5) |
| No adversarial regression tests | Phase 0 builds test suite before implementation |
| Prompt-level governance without runtime enforcement | External validators with veto power (Phases 3, 4) |
| Review target mismatch | Each gate states what it proves and doesn't prove (Phase 6 docs) |
| Workflow compliance without semantic delta | Correspondence report measures semantic preservation, not process completion (Phase 4) |
| Debugging symptoms sequentially | Comprehensive correspondence state machine designed upfront (this plan) |
| Reviewer availability fragility | No external API dependencies for critical path; pylatexenc local extraction (Phase 1) |

---

## Open Questions and Decisions Needed

### Technical Decisions

1. **Protected-object extraction accuracy goal:**
   - Proposed: ≥95%
   - Alternative: ≥99% (stricter) or ≥90% (more lenient)
   - Decision needed by: Week 1 (affects Phase 1 implementation)

2. **Correspondence gap threshold:**
   - Proposed: 5% for draft, 1% for assembly
   - Rationale: Draft may reasonably merge/split objects; assembly should preserve exactly
   - Decision needed by: Week 3 (affects Phase 3 gate logic)

3. **Repair budget default:**
   - Proposed: 10 iterations
   - Alternative: 5 (faster) or 20 (more thorough)
   - Decision needed by: Week 5 (affects Phase 5 implementation)

4. **Section boundary detection:**
   - Proposed: Heuristic from source line numbers in plan
   - Alternative: Full LaTeX parsing for section structure
   - Decision needed by: Week 2 (affects Phase 2 evidence routing)

### Process Decisions

5. **v1.2 scope:**
   - Proposed: Phases 0-4 + 6 mandatory, Phase 5 stretch
   - Alternative: All phases mandatory (8 weeks firm)
   - Alternative: Only Phases 0-3 (faster, less complete)
   - Decision needed by: End of Week 1 (affects timeline commitments)

6. **External testing:**
   - Proposed: ≥2 additional fixtures beyond ZLB HMC survey
   - What fixtures? (economics papers, CS papers, math textbook?)
   - Decision needed by: Week 6 (affects release testing)

7. **Backward compatibility:**
   - Proposed: v1.1 snapshots require re-init for manifests
   - Alternative: Attempt to generate manifests retroactively (risky)
   - Decision needed by: Week 6 (affects migration guide)

### Escalation

Questions 1-4: Technical lead decision  
Questions 5-7: Product owner + user review required  

---

## Conclusion

This plan implements fail-closed correspondence verification for humanvoice v1.2, directly addressing the 2026-08-29 pilot failure (protected_correspondence: pass, 0 manifests, 105 missing equations).

**Core architecture:** Extract protected objects before drafting → route evidence explicitly per section → verify correspondence at every boundary → block release when gaps detected.

**Timeline:** 6-8 weeks, with 2-week buffer for testing and documentation.

**Risk mitigation:** Adversarial regression tests before implementation, fail-closed by default, comprehensive state machine, external validators with veto power.

**Success criteria:** ZLB HMC survey retains ≥104/109 equations through draft/assemble/release pipeline, all regression tests pass, user can inspect correspondence manifests.

**Lessons applied:** 32 DynareMCP failure patterns directly addressed through machine-readable schemas, runtime enforcement, objective measurement, and adversarial testing.

The next action is user review of this plan, then Phase 0 implementation (test infrastructure).
