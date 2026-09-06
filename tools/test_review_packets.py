import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_review_packets import prepare


class ReviewPacketTests(unittest.TestCase):
    def test_templates_keep_release_fields_blank_and_preserve_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "run"
            output = root / "imports"
            run.mkdir()
            (run / "run_metadata.json").write_text("{}\n", encoding="utf-8")
            with (run / "screening_queue.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["screening_id", "title", "screening_decision", "screening_reason"])
                writer.writeheader()
                writer.writerow({"screening_id": "S-1", "title": "Study", "screening_decision": "manual-screen-required", "screening_reason": "inspect"})
            with (run / "critical_appraisal_queue.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "title", "study_design", "appraisal_tool", "finding", "implication", "load_bearing"])
                writer.writeheader()
                writer.writerow({"id": "E-1", "title": "Evidence", "study_design": "randomized", "appraisal_tool": "RoB2", "finding": "finding", "implication": "implication", "load_bearing": "yes"})
            result = prepare(run, output)
            self.assertEqual(result["status"], "prepared-blank-overlay")
            with (output / "screening_review.csv").open(encoding="utf-8", newline="") as handle:
                screening = next(csv.DictReader(handle))
            self.assertEqual(screening["generated_screening_decision"], "manual-screen-required")
            self.assertEqual(screening["reviewer_1"], "")
            with (output / "evidence_review.csv").open(encoding="utf-8", newline="") as handle:
                evidence = next(csv.DictReader(handle))
            self.assertEqual(evidence["generated_study_design"], "randomized")
            self.assertEqual(evidence["generated_appraisal_tool"], "RoB2")
            self.assertEqual(evidence["independent_verification"], "")
            manifest = json.loads((output / "review_packet_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["reviewer_decisions"], "none")

    def test_existing_packet_is_not_overwritten_without_force(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "run"
            output = root / "imports"
            run.mkdir()
            (run / "run_metadata.json").write_text("{}\n", encoding="utf-8")
            (run / "screening_queue.csv").write_text("screening_id\nS-1\n", encoding="utf-8")
            (run / "critical_appraisal_queue.csv").write_text("id\nE-1\n", encoding="utf-8")
            prepare(run, output)
            with self.assertRaises(ValueError):
                prepare(run, output)


if __name__ == "__main__":
    unittest.main()
