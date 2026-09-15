#!/usr/bin/env python3
"""
Smoke test with live model invocation.

This test runs the full pipeline on a tiny fixture (5 lines) with real model calls.
It's the most expensive test in the suite (~$0.01 per run) but catches integration
bugs that mock-only tests miss:
- ModelAdapter initialization issues
- API parameter mismatches
- Schema validation failures
- Profile/config compatibility

Run only when ANTHROPIC_API_KEY is set. Skip in CI unless explicitly enabled.
"""

import os
import unittest
import tempfile
import subprocess
import json
from pathlib import Path


@unittest.skipUnless(
    os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('RUN_LIVE_TESTS'),
    "Live model tests require ANTHROPIC_API_KEY or RUN_LIVE_TESTS=1"
)
class TestLiveModelSmoke(unittest.TestCase):
    """Single tiny fixture through full pipeline with live model."""

    def test_live_pipeline_equation_fixture(self):
        """Run full pipeline on equation/001.tex (22 lines) with live model."""
        
        # Use equation fixture - small but has equations, citations, real content
        fixture_dir = Path(__file__).parent.parent / "fixtures" / "synthetic" / "equation"
        source_file = fixture_dir / "001.tex"
        
        self.assertTrue(source_file.exists(), f"Fixture not found: {source_file}")
        
        with tempfile.TemporaryDirectory(prefix="hv-live-smoke-") as tmpdir:
            # Create brief file first - init will use it to populate snapshot
            brief_path = Path(tmpdir) / "brief.json"

            # Create brief with all required fields
            brief = {
                "record_type": "AuthoringBrief",
                "schema_version": "HV-SCHEMA-1.1",
                "reader": "Graduate student learning fundamental mathematical concepts",
                "reader_role": "Graduate student",
                "decision": "Understand and apply the concepts",
                "decision_type": "learning",
                "genre": "textbook",
                "time_available_minutes": 30,
                "prior_knowledge": "Calculus and linear algebra",
                "success_criteria": "Can state and apply the theorems presented",
                "known_vocabulary": ["equation", "theorem", "proof"],
                "exemplars": [],
                "evidence_boundary": ["001.tex"],
                "privacy_class": "public",
                "protected_objects": [],
                "unknowns": [],
                "remote_inference_authorized": True
            }
            brief_path.write_text(json.dumps(brief, indent=2))

            snapshot_dir = Path(tmpdir) / "snapshot"

            # Step 1: Init
            result = subprocess.run(
                ["python3", "-m", "humanvoice.cli", "init", 
                 str(source_file), 
                 "--brief", str(brief_path),
                 "--out", str(snapshot_dir)],
                capture_output=True,
                text=True,
                timeout=30
            )
            self.assertEqual(result.returncode, 0, 
                f"hv init failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")
            
            # Step 2: Inventory with --freeze (live model)
            # NOTE: Removing --mock flag to force live model invocation
            result = subprocess.run(
                ["python3", "-m", "humanvoice.cli", "inventory",
                 str(snapshot_dir),
                 "--freeze",
                 "--adjudicator", "test-live-smoke"],
                capture_output=True,
                text=True,
                timeout=120  # Live model calls take longer
            )
            self.assertEqual(result.returncode, 0,
                f"hv inventory --freeze failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")
            
            # Verify baseline was created
            baseline_dir = snapshot_dir / ".humanvoice" / "inventory"
            self.assertTrue((baseline_dir / "baseline.json").exists(),
                "baseline.json should be created after inventory --freeze")
            
            # Load and verify baseline has concepts
            baseline = json.loads((baseline_dir / "baseline.json").read_text())
            self.assertIn("concept_entries", baseline)
            self.assertGreater(len(baseline["concept_entries"]), 0,
                "Baseline should have at least one concept")
            
            # Verify all concepts have valid IDs
            for entry in baseline["concept_entries"]:
                self.assertIn("concept_id", entry)
                self.assertTrue(entry["concept_id"], "Concept ID should not be empty")
            
            # Check for duplicates
            concept_ids = [e["concept_id"] for e in baseline["concept_entries"]]
            self.assertEqual(len(concept_ids), len(set(concept_ids)),
                "All concept IDs should be unique (no duplicates)")
            
            print(f"\n✓ Live inventory created baseline with {len(concept_ids)} concepts")
            
            # Step 3: Plan (uses baseline)
            result = subprocess.run(
                ["python3", "-m", "humanvoice.cli", "plan",
                 str(snapshot_dir)],
                capture_output=True,
                text=True,
                timeout=30
            )
            self.assertEqual(result.returncode, 0,
                f"hv plan failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")

            # Verify plan was created
            plans_dir = snapshot_dir / ".humanvoice" / "plans"
            plan_files = list(plans_dir.glob("plan-*.json"))
            self.assertGreater(len(plan_files), 0, "Plan file should be created")
            
            plan = json.loads(plan_files[0].read_text())
            self.assertIn("units", plan)
            self.assertGreater(len(plan["units"]), 0, "Plan should have at least one unit")
            
            print(f"✓ Plan created with {len(plan['units'])} unit(s)")
            
            # For smoke test, we stop here - rewrite is covered by existing tests
            # The critical validation is that live model invocation works through inventory
            print("✓ Live model smoke test passed")


if __name__ == '__main__':
    unittest.main()
