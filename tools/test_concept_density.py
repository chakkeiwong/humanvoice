import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from concept_density import added_assertions, analyze, compare_to_exemplars, first_use_audit


class ConceptDensityTests(unittest.TestCase):
    def write(self, directory: Path, name: str, text: str) -> Path:
        path = directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_metrics_and_exemplar_comparison_are_descriptive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = self.write(
                root,
                "target.tex",
                """A population-based method, BG-PBT, chooses candidates.

The method uses a trust region and a citation \citep{smith2024}.

BG-PBT returns a measured result after the trust region closes.
""",
            )
            exemplar = self.write(
                root,
                "exemplar.tex",
                """A method begins with an example and explains RidgeModel.

The method returns to RidgeModel before adding a second object.

The second object is worked through in a small RidgeModel case.
""",
            )
            result = analyze(target)
            reference = analyze(exemplar)
            comparison = compare_to_exemplars(result, [reference])
            self.assertGreater(result["words"], 0)
            self.assertGreaterEqual(result["concepts"], 1)
            self.assertEqual(comparison["exemplar_count"], 1)
            self.assertIn("bursts", result)

    def test_first_use_respects_whitelist_and_exemptions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = self.write(
                root,
                "order.tex",
                """PPO appears in this preview before the method is explained.

The reader already knows Bayesian inference and can use it here.

The method is a population-based approach, BG-PBT, introduced for the case.
""",
            )
            findings = first_use_audit(target, whitelist=["Bayesian inference"], exempt_ranges=[[1, 1]])
            terms = {finding.term for finding in findings}
            self.assertNotIn("ppo", terms)
            self.assertNotIn("bayesian inference", terms)
            self.assertNotIn("bg-pbt", terms)

    def test_added_assertion_requires_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = self.write(root, "parent.tex", "The package provides a sampler.\n")
            child = self.write(root, "child.tex", "The package provides the most widely adopted sampler.\n")
            additions = added_assertions(parent, child)
            self.assertEqual(len(additions), 1)
            self.assertIn("widely adopted", additions[0])

    def test_checked_in_hpo_fixture_keeps_claim_boundary(self):
        fixture = json.loads(
            (Path(__file__).resolve().parents[1] / "docs/survey/evidence/hpo_density_fixture.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(fixture["claim_class"], "internal-calibration-and-fixture")
        self.assertEqual(fixture["rounds"][2]["evidence"]["adjudicated_positive_violations"], 25)
        self.assertEqual(fixture["rounds"][2]["evidence"]["adjudicated_false_alarms"], 80)
        self.assertIn("one engagement", " ".join(fixture["prototype_limits"]))


if __name__ == "__main__":
    unittest.main()
