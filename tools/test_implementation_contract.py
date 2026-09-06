import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_implementation_contract import validate_contract


class ImplementationContractTests(unittest.TestCase):
    def test_contract_is_complete(self):
        result = validate_contract()
        self.assertTrue(result["contract_valid"], result["errors"])

    def _copy_contract_tree(self, destination: Path) -> None:
        root = Path(__file__).resolve().parents[1]
        shutil.copytree(root / "schemas", destination / "schemas")
        shutil.copy2(root / "requirements-dev.txt", destination / "requirements-dev.txt")
        survey = destination / "docs/survey"
        (survey / "evidence").mkdir(parents=True)
        (survey / "proposal").mkdir(parents=True)
        for relative in (
            "humanvoice_product_requirements.json",
            "humanvoice_survey.tex",
        ):
            shutil.copy2(root / "docs/survey" / relative, survey / relative)
        shutil.copy2(
            root / "docs/survey/evidence/corpus_rights_manifest.json",
            survey / "evidence/corpus_rights_manifest.json",
        )
        shutil.copy2(
            root / "docs/survey/proposal/21_implementation_contract.tex",
            survey / "proposal/21_implementation_contract.tex",
        )

    def _mutated_result(self, mutator):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._copy_contract_tree(root)
            mutator(root)
            return validate_contract(root)

    @staticmethod
    def _mutate_schema(root: Path, name: str, mutate) -> None:
        path = root / "schemas" / name
        value = json.loads(path.read_text(encoding="utf-8"))
        mutate(value)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def test_mutation_missing_cli_stable_field_fails(self):
        result = self._mutated_result(
            lambda root: self._mutate_schema(
                root,
                "cli-result.schema.json",
                lambda schema: schema["required"].remove("source_hash"),
            )
        )
        self.assertFalse(result["contract_valid"])
        self.assertTrue(
            any("cli-result schema omits stable stdout fields" in error for error in result["errors"]),
            result["errors"],
        )

    def test_mutation_missing_consent_date_fails(self):
        result = self._mutated_result(
            lambda root: self._mutate_schema(
                root,
                "corpus-item.schema.json",
                lambda schema: schema["required"].remove("consent_date"),
            )
        )
        self.assertFalse(result["contract_valid"])
        self.assertTrue(
            any("corpus-item schema omits contract rights fields" in error for error in result["errors"]),
            result["errors"],
        )

    def test_mutation_missing_runtime_provenance_fails(self):
        result = self._mutated_result(
            lambda root: self._mutate_schema(
                root,
                "runtime-manifest.schema.json",
                lambda schema: schema["required"].remove("model_version_string"),
            )
        )
        self.assertFalse(result["contract_valid"])
        self.assertTrue(
            any("runtime-manifest schema omits provenance fields" in error for error in result["errors"]),
            result["errors"],
        )

    def test_mutation_missing_brief_boundary_field_fails(self):
        result = self._mutated_result(
            lambda root: self._mutate_schema(
                root,
                "authoring-brief.schema.json",
                lambda schema: schema["required"].remove("known_vocabulary"),
            )
        )
        self.assertFalse(result["contract_valid"])
        self.assertTrue(
            any("AuthoringBrief schema omits contract record fields" in error for error in result["errors"]),
            result["errors"],
        )

    def test_mutation_permissive_top_level_fails(self):
        result = self._mutated_result(
            lambda root: self._mutate_schema(
                root,
                "finding.schema.json",
                lambda schema: schema.__setitem__("additionalProperties", True),
            )
        )
        self.assertFalse(result["contract_valid"])
        self.assertTrue(
            any("finding.schema.json permits unknown top-level fields" in error for error in result["errors"]),
            result["errors"],
        )

    def test_mutation_that_makes_negative_example_valid_fails(self):
        def mutate(root: Path) -> None:
            path = root / "schemas/examples/cli-result-missing-source-hash.invalid.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["source_hash"] = "a" * 64
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

        result = self._mutated_result(mutate)
        self.assertFalse(result["contract_valid"])
        self.assertTrue(
            any("unexpectedly passed" in error for error in result["errors"]),
            result["errors"],
        )

    def test_mutation_removing_valid_example_fails(self):
        def mutate(root: Path) -> None:
            path = root / "schemas/examples/manifest.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["examples"] = [
                row
                for row in value["examples"]
                if row["schema"] != "finding.schema.json" or row["expected"] != "valid"
            ]
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

        result = self._mutated_result(mutate)
        self.assertFalse(result["contract_valid"])
        self.assertTrue(
            any("lacks valid instances" in error for error in result["errors"]),
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
