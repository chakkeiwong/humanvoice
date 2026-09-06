import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_program_consistency import validate_program


class ProgramConsistencyTests(unittest.TestCase):
    def _copy_program_tree(self, destination: Path) -> None:
        source_root = Path(__file__).resolve().parents[1]
        for relative in (
            "docs/plans/humanvoice_master_program_v1.1_2026-08-26.md",
            "docs/plans/humanvoice_decisions_2026-08-26.md",
            "docs/plans/humanvoice_staffing_plan_2026-08-26.json",
            "docs/plans/templates/gate_decision_record.md",
            "docs/plans/gates/G0_decision_2026-08-26.md",
            "docs/survey/humanvoice_product_requirements.json",
            "docs/survey/humanvoice_survey.tex",
            "docs/survey/proposal/21_implementation_contract.tex",
            "docs/survey/evidence/corpus_rights_manifest.json",
            "fixtures/manifest.json",
            "fixtures/historical_sources.json",
            "fixtures/synthetic/register/001.tex",
            "fixtures/answer-keys/register-001.json",
            "schemas/implementation_contract.json",
            "schemas/record_catalog.json",
            "security/runtime_profile.json",
            "requirements-dev.txt",
        ):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_root / relative, target)

    def _mutated_result(self, mutator):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._copy_program_tree(root)
            mutator(root)
            return validate_program(root, verify_external=False)

    @staticmethod
    def _load_and_write(path: Path, mutator) -> None:
        value = json.loads(path.read_text(encoding="utf-8"))
        mutator(value)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def test_current_program_is_structurally_consistent_but_g0_blocked(self):
        result = validate_program()
        self.assertTrue(result["program_consistent"], result["errors"])
        self.assertFalse(result["g0_ready"])
        self.assertTrue(result["blockers"])

    def test_missing_catalogue_type_fails(self):
        def mutate(root: Path) -> None:
            path = root / "fixtures/manifest.json"
            self._load_and_write(
                path,
                lambda manifest: manifest["fixtures"].pop(0),
            )

        result = self._mutated_result(mutate)
        self.assertFalse(result["program_consistent"])
        self.assertTrue(
            any("fixture inventory omits catalogue types" in error for error in result["errors"]),
            result["errors"],
        )

    def test_planned_fixture_cannot_carry_placeholder_hash(self):
        def mutate(root: Path) -> None:
            path = root / "fixtures/manifest.json"

            def add_hash(manifest):
                manifest["fixtures"][0]["source_hash"] = "placeholder"

            self._load_and_write(path, add_hash)

        result = self._mutated_result(mutate)
        self.assertFalse(result["program_consistent"])
        self.assertTrue(
            any("placeholder path or hash" in error for error in result["errors"]),
            result["errors"],
        )

    def test_ready_fixture_hash_mismatch_fails(self):
        def mutate(root: Path) -> None:
            path = root / "fixtures/synthetic/register/001.tex"
            path.write_text(path.read_text(encoding="utf-8") + "\n% mutation\n", encoding="utf-8")

        result = self._mutated_result(mutate)
        self.assertFalse(result["program_consistent"])
        self.assertTrue(
            any("wrong source_hash" in error for error in result["errors"]),
            result["errors"],
        )

    def test_missing_gate_owner_fails(self):
        def mutate(root: Path) -> None:
            path = root / "docs/plans/humanvoice_master_program_v1.1_2026-08-26.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                "**Decision owners:** sponsor or project owner, with technical-owner and security-\nowner concurrence.",
                "",
                1,
            )
            path.write_text(text, encoding="utf-8")

        result = self._mutated_result(mutate)
        self.assertFalse(result["program_consistent"])
        self.assertTrue(
            any("decision owners for G0" in error for error in result["errors"]),
            result["errors"],
        )

    def test_unavailable_historical_source_cannot_assert_locator(self):
        def mutate(root: Path) -> None:
            path = root / "fixtures/historical_sources.json"

            def add_locator(registry):
                row = registry["sources"][1]
                row["repository_relative_path"] = "missing.jsonl"

            self._load_and_write(path, add_locator)

        result = self._mutated_result(mutate)
        self.assertFalse(result["program_consistent"])
        self.assertTrue(
            any("unavailable historical source" in error for error in result["errors"]),
            result["errors"],
        )

    def test_g0_pass_cannot_override_blockers(self):
        def mutate(root: Path) -> None:
            path = root / "docs/plans/gates/G0_decision_2026-08-26.md"
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace(
                    "**Decision:** pending (WP0-only authorization)",
                    "**Decision:** pass",
                    1,
                ),
                encoding="utf-8",
            )

        result = self._mutated_result(mutate)
        self.assertFalse(result["program_consistent"])
        self.assertTrue(
            any("G0 decision record claims pass" in error for error in result["errors"]),
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
