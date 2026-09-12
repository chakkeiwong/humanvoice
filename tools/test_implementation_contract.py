"""Mutation tests for the v2 implementation-contract checker.

Each test breaks one contract invariant in a throwaway copy of the authority
tree and asserts that the checker reports it. A checker that passes a broken
tree is worse than no checker, so every guarantee the contract claims needs a
mutation here that proves the guarantee is actually enforced.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_implementation_contract import validate_contract

ROOT = Path(__file__).resolve().parents[1]

AUTHORITY_TEX = (
    "humanvoice_survey.tex",
    "proposal/00_orientation.tex",
    "proposal/03_product.tex",
    "proposal/06_design.tex",
    "proposal/16_architecture.tex",
    "proposal/21_implementation_contract.tex",
)


class ContractTreeTestCase(unittest.TestCase):
    """Copy the authority tree, mutate it, and re-run the checker."""

    def _copy_contract_tree(self, destination: Path) -> None:
        shutil.copytree(ROOT / "schemas", destination / "schemas")
        shutil.copy2(ROOT / "requirements-dev.txt", destination / "requirements-dev.txt")
        plans = destination / "docs/plans"
        plans.mkdir(parents=True)
        for name in (
            "humanvoice_master_program_v2.md",
            "humanvoice_v2_contract_change_2026-09-11.md",
        ):
            shutil.copy2(ROOT / "docs/plans" / name, plans / name)
        survey = destination / "docs/survey"
        (survey / "evidence").mkdir(parents=True)
        (survey / "proposal").mkdir(parents=True)
        shutil.copy2(
            ROOT / "docs/survey/humanvoice_product_requirements.json",
            survey / "humanvoice_product_requirements.json",
        )
        shutil.copy2(
            ROOT / "docs/survey/evidence/corpus_rights_manifest.json",
            survey / "evidence/corpus_rights_manifest.json",
        )
        for relative in AUTHORITY_TEX:
            shutil.copy2(ROOT / "docs/survey" / relative, survey / relative)

    def _mutated_result(self, mutator):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._copy_contract_tree(root)
            mutator(root)
            return validate_contract(root)

    def assertFails(self, result, fragment: str) -> None:
        self.assertFalse(result["contract_valid"], "mutation was not detected")
        self.assertTrue(
            any(fragment in error for error in result["errors"]),
            f"no error contained {fragment!r}; got {result['errors']}",
        )

    @staticmethod
    def _edit_json(root: Path, relative: str, mutate) -> None:
        path = root / relative
        value = json.loads(path.read_text(encoding="utf-8"))
        mutate(value)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def _edit_contract(cls, root: Path, mutate) -> None:
        cls._edit_json(root, "schemas/implementation_contract.json", mutate)

    @classmethod
    def _edit_catalogue(cls, root: Path, mutate) -> None:
        cls._edit_json(root, "schemas/record_catalog.json", mutate)

    @classmethod
    def _edit_schema(cls, root: Path, name: str, mutate) -> None:
        cls._edit_json(root, f"schemas/{name}", mutate)


class BaselineTests(ContractTreeTestCase):
    def test_repository_contract_is_valid(self):
        result = validate_contract()
        self.assertTrue(result["contract_valid"], result["errors"])

    def test_copied_tree_is_valid_without_mutation(self):
        # Guards the harness itself: if the copy is incomplete, every mutation
        # test below would "pass" for the wrong reason.
        result = self._mutated_result(lambda root: None)
        self.assertTrue(result["contract_valid"], result["errors"])

    def test_state_is_specified_only(self):
        result = validate_contract()
        self.assertEqual(result["evidence_state"], "specified")


class ProductOperationTests(ContractTreeTestCase):
    def test_length_objective_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root,
                lambda c: c["product_operation"].__setitem__("length_objective", 5000),
            )
        )
        self.assertFails(result, "prose length objective")

    def test_retention_below_one_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root,
                lambda c: c["product_operation"].__setitem__(
                    "required_concept_retention", 0.99
                ),
            )
        )
        self.assertFails(result, "concept retention is not exactly 1.0")

    def test_mutable_source_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root,
                lambda c: c["product_operation"].__setitem__("source", "mutable"),
            )
        )
        self.assertFails(result, "immutability contract")

    def test_greenfield_primary_operation_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root,
                lambda c: c["product_operation"].__setitem__(
                    "primary", "brief-to-draft authoring"
                ),
            )
        )
        self.assertFails(result, "finished-manuscript humanization")


class ConceptContractTests(ContractTreeTestCase):
    def test_permitted_omission_operation_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root,
                lambda c: c["concept_contract"].__setitem__(
                    "substantive_omission", "permitted"
                ),
            )
        )
        self.assertFails(result, "substantive omission is not forbidden")

    def test_omission_in_correspondence_schema_is_rejected(self):
        def mutate(root: Path) -> None:
            self._edit_schema(
                root,
                "concept-correspondence.schema.json",
                lambda schema: schema["properties"]["operation"]["enum"].append("omit"),
            )

        self.assertFails(self._mutated_result(mutate), "exposes an omission operation")

    def test_partial_credit_match_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root,
                lambda c: c["concept_contract"].__setitem__("uncertain_match", "partial"),
            )
        )
        self.assertFails(result, "uncertain semantic matches")

    def test_waivable_active_obligation_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root,
                lambda c: c["concept_contract"].__setitem__(
                    "active_obligation_exception", "permitted"
                ),
            )
        )
        self.assertFails(result, "active obligations can be exception-released")


class EvidenceStateTests(ContractTreeTestCase):
    def test_collapsed_evidence_states_are_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root,
                lambda c: c.__setitem__(
                    "evidence_states", ["specified", "implemented", "demonstrated"]
                ),
            )
        )
        self.assertFails(result, "evidence state vocabulary")

    def test_claiming_a_later_state_at_g0_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root, lambda c: c.__setitem__("status", "test-verified")
            )
        )
        self.assertFails(result, "only specified at G0")


class RecordBoundaryTests(ContractTreeTestCase):
    def test_legacy_record_promoted_to_current_is_rejected(self):
        def mutate(root: Path) -> None:
            def promote(catalogue):
                for row in catalogue["records"]:
                    if row.get("schema_status") == "legacy_v1":
                        row["schema_status"] = "present"
                        break

            self._edit_catalogue(root, promote)

        self.assertFails(self._mutated_result(mutate), "legacy_v1 catalogue boundary")

    def test_missing_semantic_record_is_rejected(self):
        def mutate(root: Path) -> None:
            self._edit_contract(
                root,
                lambda c: c["record_policy"]["semantic_record_types"].remove(
                    "ConceptBaseline"
                ),
            )

        self.assertFails(self._mutated_result(mutate), "semantic record family")

    def test_automatic_v1_conversion_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root,
                lambda c: c["migration"].__setitem__(
                    "semantic_record_conversion", "automatic"
                ),
            )
        )
        self.assertFails(result, "auto-converted")

    def test_resumed_v1_external_release_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root, lambda c: c["migration"].__setitem__("v1_external_release", "allowed")
            )
        )
        self.assertFails(result, "v1 external release is not suspended")


class ReleaseAuthorityTests(ContractTreeTestCase):
    def test_dropped_never_except_invariant_is_rejected(self):
        def mutate(root: Path) -> None:
            def drop(contract):
                terms = contract["release_authority"]["never_except"]
                contract["release_authority"]["never_except"] = [
                    term for term in terms if "obligation" not in term
                ]

            self._edit_contract(root, drop)

        self.assertFails(self._mutated_result(mutate), "never-except semantic invariants")

    def test_model_promotion_authority_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root,
                lambda c: c["release_authority"].__setitem__(
                    "promotion_authority", "semantic critic"
                ),
            )
        )
        self.assertFails(result, "promotion authority")

    def test_compression_from_resource_limit_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root,
                lambda c: c["operating_controls"].__setitem__(
                    "semantic_compression_from_limit", "permitted"
                ),
            )
        )
        self.assertFails(result, "permit semantic compression")


class TrustBoundaryTests(ContractTreeTestCase):
    def test_default_allow_remote_inference_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root, lambda c: c["trust_boundary"].__setitem__("remote_default", "allow")
            )
        )
        self.assertFails(result, "remote inference default")

    def test_missing_trust_control_is_rejected(self):
        def mutate(root: Path) -> None:
            self._edit_contract(
                root,
                lambda c: c["trust_boundary"]["controls"].pop(),
            )

        self.assertFails(self._mutated_result(mutate), "trust-boundary controls")

    def test_shell_escape_build_is_rejected(self):
        def mutate(root: Path) -> None:
            self._edit_contract(
                root,
                lambda c: c["runtime"]["build"]["required_flags"].remove("-no-shell-escape"),
            )

        self.assertFails(self._mutated_result(mutate), "-no-shell-escape")


class CliContractTests(ContractTreeTestCase):
    def test_missing_resumable_phase_is_rejected(self):
        def mutate(root: Path) -> None:
            self._edit_contract(
                root, lambda c: c["cli"]["resumable_phases"].remove("hv inventory")
            )

        self.assertFails(self._mutated_result(mutate), "resumable phase surface")

    def test_missing_legacy_namespace_is_rejected(self):
        result = self._mutated_result(
            lambda root: self._edit_contract(
                root, lambda c: c["cli"].__setitem__("legacy_namespace", None)
            )
        )
        self.assertFails(result, "legacy namespace")

    def test_unstable_stdout_field_is_rejected(self):
        def mutate(root: Path) -> None:
            self._edit_schema(
                root,
                "cli-result.schema.json",
                lambda schema: schema["required"].remove("contract_id"),
            )

        self.assertFails(self._mutated_result(mutate), "stable stdout fields")


class SchemaHygieneTests(ContractTreeTestCase):
    def test_permissive_top_level_schema_is_rejected(self):
        def mutate(root: Path) -> None:
            self._edit_schema(
                root,
                "source-concept.schema.json",
                lambda schema: schema.__setitem__("additionalProperties", True),
            )

        self.assertFails(self._mutated_result(mutate), "permits unknown top-level fields")

    def test_schema_open_to_a_future_major_is_rejected(self):
        def mutate(root: Path) -> None:
            self._edit_schema(
                root,
                "source-span.schema.json",
                lambda schema: schema["properties"]["schema_version"].__setitem__(
                    "pattern", r"^\d+\.\d+\.\d+$"
                ),
            )

        self.assertFails(self._mutated_result(mutate), "restricted to major v2")

    def test_catalogue_schema_removal_is_rejected(self):
        def mutate(root: Path) -> None:
            (root / "schemas/source-concept.schema.json").unlink()

        self.assertFails(self._mutated_result(mutate), "catalogue schema is missing")


class ExampleCoverageTests(ContractTreeTestCase):
    def test_negative_example_that_starts_validating_is_rejected(self):
        def mutate(root: Path) -> None:
            path = root / "schemas/examples/manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            target = next(
                row for row in manifest["examples"] if row["expected"] == "invalid"
            )
            valid = next(
                row
                for row in manifest["examples"]
                if row["expected"] == "valid" and row["schema"] == target["schema"]
            )
            shutil.copy2(
                root / "schemas/examples" / valid["instance"],
                root / "schemas/examples" / target["instance"],
            )

        self.assertFails(self._mutated_result(mutate), "unexpectedly passed")

    def test_missing_valid_example_is_rejected(self):
        def mutate(root: Path) -> None:
            def drop(manifest):
                manifest["examples"] = [
                    row
                    for row in manifest["examples"]
                    if not (
                        row["schema"] == "source-concept.schema.json"
                        and row["expected"] == "valid"
                    )
                ]

            self._edit_json(root, "schemas/examples/manifest.json", drop)

        self.assertFails(self._mutated_result(mutate), "no valid example for: SourceConcept")

    def test_missing_valid_bundle_is_rejected(self):
        def mutate(root: Path) -> None:
            def drop(manifest):
                manifest["bundles"] = [
                    row for row in manifest["bundles"] if row["expected"] != "valid"
                ][:1]

            self._edit_json(root, "schemas/examples/manifest.json", drop)

        self.assertFails(self._mutated_result(mutate), "baseline and a complete pipeline")

    def test_dropped_adversarial_bundle_is_rejected(self):
        def mutate(root: Path) -> None:
            def drop(manifest):
                manifest["bundles"] = [
                    row
                    for row in manifest["bundles"]
                    if "lack an accepted rewrite disposition"
                    not in row.get("expected_error_contains", "")
                ]

            self._edit_json(root, "schemas/examples/manifest.json", drop)

        self.assertFails(self._mutated_result(mutate), "adversarial bundle")

    def test_adversarial_bundle_that_starts_validating_is_rejected(self):
        def mutate(root: Path) -> None:
            path = root / "schemas/examples/bundle-unplanned-concept.invalid.json"
            valid = root / "schemas/examples/humanization-pipeline.bundle.valid.json"
            shutil.copy2(valid, path)

        self.assertFails(self._mutated_result(mutate), "unexpectedly passed")


class RequirementRegisterTests(ContractTreeTestCase):
    def test_truncated_register_is_rejected(self):
        def mutate(root: Path) -> None:
            def drop(requirements):
                requirements["requirements"] = requirements["requirements"][:24]
                requirements["requirement_count"] = 24

            self._edit_json(
                root, "docs/survey/humanvoice_product_requirements.json", drop
            )

        self.assertFails(self._mutated_result(mutate), "canonical R1-R29 register")

    def test_renumbered_historical_requirement_is_rejected(self):
        def mutate(root: Path) -> None:
            def renumber(requirements):
                requirements["requirements"][0]["id"] = "R0"

            self._edit_json(
                root, "docs/survey/humanvoice_product_requirements.json", renumber
            )

        self.assertFails(self._mutated_result(mutate), "canonical R1-R29 register")


class AuthorityLanguageTests(ContractTreeTestCase):
    def test_reintroduced_bounded_mvp_framing_is_rejected(self):
        def mutate(root: Path) -> None:
            path = root / "docs/survey/proposal/00_orientation.tex"
            path.write_text(
                path.read_text(encoding="utf-8")
                + "\nThis is a bounded MVP and does not fund deployment.\n",
                encoding="utf-8",
            )

        self.assertFails(self._mutated_result(mutate), "bounded-MVP framing")

    def test_reintroduced_blueprint_pipeline_is_rejected(self):
        def mutate(root: Path) -> None:
            path = root / "docs/survey/proposal/06_design.tex"
            path.write_text(
                path.read_text(encoding="utf-8")
                + "\nThe writer consumes an argument blueprint.\n",
                encoding="utf-8",
            )

        self.assertFails(self._mutated_result(mutate), "argument-blueprint pipeline")

    def test_reintroduced_word_budget_is_rejected(self):
        def mutate(root: Path) -> None:
            path = root / "docs/survey/proposal/16_architecture.tex"
            path.write_text(
                path.read_text(encoding="utf-8")
                + "\nOutput tokens per section are capped.\n",
                encoding="utf-8",
            )

        self.assertFails(self._mutated_result(mutate), "per-unit output budget")

    def test_missing_humanization_language_is_rejected(self):
        def mutate(root: Path) -> None:
            path = root / "docs/survey/proposal/03_product.tex"
            text = path.read_text(encoding="utf-8")
            text = text.replace("finished manuscript", "document")
            text = text.replace("finished-manuscript", "document")
            path.write_text(text, encoding="utf-8")

        self.assertFails(self._mutated_result(mutate), "finished-manuscript operation")

    def test_legacy_labelled_mention_is_allowed(self):
        # A superseded construct may be named when it is explicitly marked
        # legacy; the checker must not force the annex to erase its own history.
        def mutate(root: Path) -> None:
            path = root / "docs/survey/proposal/06_design.tex"
            path.write_text(
                path.read_text(encoding="utf-8")
                + "\nThe legacy v1 argument blueprint cannot satisfy a v2 gate.\n",
                encoding="utf-8",
            )

        result = self._mutated_result(mutate)
        self.assertTrue(result["contract_valid"], result["errors"])


class AuthorityStructureTests(ContractTreeTestCase):
    def test_missing_authority_document_is_rejected(self):
        def mutate(root: Path) -> None:
            (root / "docs/survey/proposal/03_product.tex").unlink()

        self.assertFails(self._mutated_result(mutate), "03_product.tex")

    def test_uncleared_corpus_item_is_rejected(self):
        def mutate(root: Path) -> None:
            def clear(manifest):
                manifest["items"][0]["redistribution_status"] = "unreviewed"

            self._edit_json(
                root, "docs/survey/evidence/corpus_rights_manifest.json", clear
            )

        self.assertFails(self._mutated_result(mutate), "has unknown status")

    def test_empty_rights_manifest_is_rejected(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root,
                "docs/survey/evidence/corpus_rights_manifest.json",
                lambda manifest: manifest.__setitem__("items", []),
            )

        self.assertFails(self._mutated_result(mutate), "rights manifest is empty")


if __name__ == "__main__":
    unittest.main()
