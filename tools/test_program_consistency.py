"""Mutation tests for the v2 program-consistency checker.

The checker's job is to catch disagreement between the program, the change
record, the requirement register, the contract, the catalogue, and the fixture
and locator registries. Each test below breaks one of those agreements in a
throwaway copy and asserts the checker notices.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_program_consistency import validate_program

ROOT = Path(__file__).resolve().parents[1]

PROGRAM = "docs/plans/humanvoice_master_program_v2.md"
CHANGE_RECORD = "docs/plans/humanvoice_v2_contract_change_2026-09-11.md"

COPIED_FILES = (
    PROGRAM,
    CHANGE_RECORD,
    "docs/plans/templates/gate_decision_record.md",
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
    "security/inference_profile.json",
    "requirements-dev.txt",
)


class ProgramTreeTestCase(unittest.TestCase):
    def _copy_program_tree(self, destination: Path) -> None:
        for relative in COPIED_FILES:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        # Ready fixtures verify their own hashes, so every referenced artifact
        # has to come along or the copy fails for the wrong reason.
        manifest = json.loads(
            (ROOT / "fixtures/manifest.json").read_text(encoding="utf-8")
        )
        for row in manifest.get("fixtures", []):
            for field in ("source_path", "answer_key_path"):
                relative = row.get(field)
                if not relative:
                    continue
                source = ROOT / relative
                if not source.is_file():
                    continue
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copy2(source, target)
        for schema in (ROOT / "schemas").glob("*.schema.json"):
            target = destination / "schemas" / schema.name
            if not target.exists():
                shutil.copy2(schema, target)

    def _mutated_result(self, mutator):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._copy_program_tree(root)
            mutator(root)
            return validate_program(root, verify_external=False)

    def assertFails(self, result, fragment: str) -> None:
        self.assertFalse(result["program_consistent"], "mutation was not detected")
        self.assertTrue(
            any(fragment in error for error in result["errors"]),
            f"no error contained {fragment!r}; got {result['errors']}",
        )

    @staticmethod
    def _edit_json(path: Path, mutator) -> None:
        value = json.loads(path.read_text(encoding="utf-8"))
        mutator(value)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _edit_text(path: Path, mutator) -> None:
        path.write_text(mutator(path.read_text(encoding="utf-8")), encoding="utf-8")


class BaselineTests(ProgramTreeTestCase):
    def test_repository_program_is_consistent_and_g0_ready(self):
        result = validate_program()
        self.assertTrue(result["program_consistent"], result["errors"])
        self.assertTrue(result["g0_ready"], result["blockers"])

    def test_copied_tree_is_consistent_without_mutation(self):
        result = self._mutated_result(lambda root: None)
        self.assertTrue(result["program_consistent"], result["errors"])

    def test_missing_artifact_fails(self):
        def mutate(root: Path) -> None:
            (root / CHANGE_RECORD).unlink()

        self.assertFails(self._mutated_result(mutate), "artifact is missing")


class ProgramStructureTests(ProgramTreeTestCase):
    def test_dropped_work_package_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / PROGRAM,
                lambda text: text.replace("### WP-V2-4", "### Deferred work"),
            )

        self.assertFails(self._mutated_result(mutate), "omits work package WP-V2-4")

    def test_dropped_gate_criterion_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / PROGRAM, lambda text: text.replace("**V2-G3:**", "Eventually:")
            )

        self.assertFails(self._mutated_result(mutate), "exit criterion for V2-G3")

    def test_collapsed_evidence_state_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / PROGRAM,
                lambda text: text.replace("independently reproduced", "reproduced"),
            )

        self.assertFails(self._mutated_result(mutate), "evidence state")

    def test_dropped_retention_invariant_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / PROGRAM,
                lambda text: text.replace("exactly 1.0", "at least 0.95"),
            )

        self.assertFails(self._mutated_result(mutate), "retention invariant")

    def test_dropped_explanation_invariant_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / PROGRAM,
                lambda text: text.replace(
                    "Mention does not satisfy explanation",
                    "Concepts appear in the output",
                ),
            )

        self.assertFails(self._mutated_result(mutate), "explanation invariant")

    def test_dropped_repetition_invariant_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / PROGRAM,
                lambda text: text.replace("distinct teaching role", "different wording"),
            )

        self.assertFails(self._mutated_result(mutate), "useful-repetition invariant")

    def test_unearned_product_working_claim_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / PROGRAM,
                lambda text: text + "\nThe product works on the ZLB manuscript.\n",
            )

        self.assertFails(self._mutated_result(mutate), "product-working claim")

    def test_unearned_gate_pass_claim_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / PROGRAM, lambda text: text + "\nV2-G4 has now passed.\n"
            )

        self.assertFails(self._mutated_result(mutate), "unearned v2 gate pass")

    def test_release_authority_outside_g6_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / PROGRAM,
                lambda text: text.replace(
                    "Only V2-G6 can authorize", "Any passed gate can authorize"
                ),
            )

        self.assertFails(self._mutated_result(mutate), "reserve release authorization")

    def test_waivable_human_evidence_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / PROGRAM,
                lambda text: text.replace(
                    "Missing human evidence cannot be waived.",
                    "Missing human evidence may be waived by the owner.",
                ),
            )

        self.assertFails(self._mutated_result(mutate), "unwaivable")


class ChangeRecordTests(ProgramTreeTestCase):
    def test_missing_change_record_section_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / CHANGE_RECORD,
                lambda text: text.replace(
                    "## Required interpretation of retained requirements",
                    "## Notes",
                ),
            )

        self.assertFails(self._mutated_result(mutate), "change record omits")

    def test_missing_added_requirement_fails(self):
        def mutate(root: Path) -> None:
            def drop(text: str) -> str:
                lines = [
                    line for line in text.splitlines(keepends=True)
                    if not line.lstrip().startswith("- **R27")
                    and not line.lstrip().startswith("R27")
                ]
                return "".join(lines).replace("R27", "")

            self._edit_text(root / CHANGE_RECORD, drop)

        self.assertFails(self._mutated_result(mutate), "does not introduce R27")

    def test_missing_reinitialization_rule_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / CHANGE_RECORD,
                lambda text: text.replace(
                    "copied into a new v2 immutable snapshot",
                    "carried forward directly",
                ),
            )

        self.assertFails(self._mutated_result(mutate), "re-initialization rule")


class ContractAlignmentTests(ProgramTreeTestCase):
    def test_contract_gate_missing_from_program_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "schemas/implementation_contract.json",
                lambda contract: contract["gates"].append(
                    {"id": "V2-G7", "work_package": "WP-V2-6", "establishes": "human-evidenced"}
                ),
            )

        self.assertFails(self._mutated_result(mutate), "V2-G0 through V2-G6")

    def test_contract_claiming_implemented_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "schemas/implementation_contract.json",
                lambda contract: contract.__setitem__("status", "implemented"),
            )

        self.assertFails(self._mutated_result(mutate), "beyond specified")

    def test_contract_pointing_at_v1_program_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "schemas/implementation_contract.json",
                lambda contract: contract["authority"].__setitem__(
                    "program", "docs/plans/humanvoice_master_program_v1.1_2026-08-26.md"
                ),
            )

        self.assertFails(self._mutated_result(mutate), "v2 program as authority")

    def test_truncated_requirement_register_fails(self):
        def mutate(root: Path) -> None:
            def drop(requirements):
                requirements["requirements"] = requirements["requirements"][:24]
                requirements["requirement_count"] = 24

            self._edit_json(
                root / "docs/survey/humanvoice_product_requirements.json", drop
            )

        self.assertFails(self._mutated_result(mutate), "not exactly R1-R29")

    def test_register_without_change_record_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "docs/survey/humanvoice_product_requirements.json",
                lambda requirements: requirements.__setitem__("change_record", None),
            )

        self.assertFails(self._mutated_result(mutate), "cite the v2 change record")

    def test_invalid_phase_mapping_fails(self):
        def mutate(root: Path) -> None:
            def renumber(requirements):
                requirements["requirements"][0]["phase"] = "P9"

            self._edit_json(
                root / "docs/survey/humanvoice_product_requirements.json", renumber
            )

        self.assertFails(self._mutated_result(mutate), "invalid phase mapping")


class CatalogueTests(ProgramTreeTestCase):
    def test_wrong_contract_id_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "schemas/record_catalog.json",
                lambda catalog: catalog.__setitem__("contract_id", "HV-IC-2026-08-26"),
            )

        self.assertFails(self._mutated_result(mutate), "wrong contract")

    def test_legacy_record_without_audit_scope_fails(self):
        def mutate(root: Path) -> None:
            def promote(catalog):
                for row in catalog["records"]:
                    if row.get("schema_status") == "legacy_v1":
                        row["required_by"] = "V2-G1"
                        break

            self._edit_json(root / "schemas/record_catalog.json", promote)

        self.assertFails(self._mutated_result(mutate), "not marked audit-only")

    def test_dropped_current_record_fails(self):
        def mutate(root: Path) -> None:
            def drop(catalog):
                catalog["records"] = [
                    row
                    for row in catalog["records"]
                    if row.get("schema_status") != "present"
                ] + [
                    row
                    for row in catalog["records"]
                    if row.get("schema_status") == "present"
                ][:-1]

            self._edit_json(root / "schemas/record_catalog.json", drop)

        self.assertFails(self._mutated_result(mutate), "current records; expected 21")

    def test_catalogue_claiming_approved_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "schemas/record_catalog.json",
                lambda catalog: catalog.__setitem__("status", "approved"),
            )

        self.assertFails(self._mutated_result(mutate), "only specified at V2-G0")

    def test_permissive_catalogue_policy_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "schemas/record_catalog.json",
                lambda catalog: catalog["compatibility_policy"].__setitem__(
                    "unknown_top_level_fields", "allow"
                ),
            )

        self.assertFails(self._mutated_result(mutate), "reject unknown top-level fields")


class InferenceProfileTests(ProgramTreeTestCase):
    def test_profile_bound_to_v1_contract_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "security/inference_profile.json",
                lambda profile: profile.__setitem__("contract_version", "1.1.0"),
            )

        self.assertFails(self._mutated_result(mutate), "bound to contract 2.0.0")

    def test_profile_claiming_readiness_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "security/inference_profile.json",
                lambda profile: profile.__setitem__("profile_status", "ready"),
            )

        self.assertFails(self._mutated_result(mutate), "beyond specification")

    def test_reintroduced_v1_gate_readiness_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "security/inference_profile.json",
                lambda profile: profile.__setitem__("g2_readiness", "ready"),
            )

        self.assertFails(self._mutated_result(mutate), "v1 G2 readiness")

    def test_word_budget_in_profile_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "security/inference_profile.json",
                lambda profile: profile["budget"].__setitem__(
                    "max_output_words_per_unit", 2000
                ),
            )

        self.assertFails(self._mutated_result(mutate), "carries a word budget")

    def test_unlabelled_calibration_claim_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "security/inference_profile.json",
                lambda profile: profile.__setitem__("calibration", {"result": "good"}),
            )

        self.assertFails(self._mutated_result(mutate), "held-out set and critics")


class FixtureAndLocatorTests(ProgramTreeTestCase):
    def test_missing_catalogue_fixture_type_fails(self):
        def mutate(root: Path) -> None:
            def drop(manifest):
                manifest["fixtures"] = [
                    row
                    for row in manifest["fixtures"]
                    if row.get("fixture_type") != "equation"
                ]

            self._edit_json(root / "fixtures/manifest.json", drop)

        self.assertFails(self._mutated_result(mutate), "omits catalogue types")

    def test_missing_threat_fixture_type_fails(self):
        def mutate(root: Path) -> None:
            def drop(manifest):
                manifest["fixtures"] = [
                    row
                    for row in manifest["fixtures"]
                    if row.get("fixture_type") != "threat-T3"
                ]

            self._edit_json(root / "fixtures/manifest.json", drop)

        self.assertFails(self._mutated_result(mutate), "omits threat types")

    def test_ready_fixture_with_wrong_hash_fails(self):
        def mutate(root: Path) -> None:
            def corrupt(manifest):
                for row in manifest["fixtures"]:
                    if row.get("lifecycle") == "ready":
                        row["source_hash"] = "0" * 64
                        break

            self._edit_json(root / "fixtures/manifest.json", corrupt)

        self.assertFails(self._mutated_result(mutate), "wrong source_hash")

    def test_planned_fixture_with_placeholder_hash_fails(self):
        def mutate(root: Path) -> None:
            def fake(manifest):
                for row in manifest["fixtures"]:
                    if row.get("lifecycle") == "planned":
                        row["source_hash"] = "0" * 64
                        break

            self._edit_json(root / "fixtures/manifest.json", fake)

        self.assertFails(self._mutated_result(mutate), "placeholder path or hash")

    def test_fixture_naming_unknown_requirement_fails(self):
        def mutate(root: Path) -> None:
            def rename(manifest):
                manifest["fixtures"][0]["requirements"] = ["R99"]

            self._edit_json(root / "fixtures/manifest.json", rename)

        self.assertFails(self._mutated_result(mutate), "unknown requirements")

    def test_unavailable_source_with_locator_fails(self):
        def mutate(root: Path) -> None:
            def assert_locator(registry):
                for row in registry["sources"]:
                    if row.get("availability") == "unavailable":
                        row["sha256"] = "0" * 64
                        break

            self._edit_json(root / "fixtures/historical_sources.json", assert_locator)

        self.assertFails(self._mutated_result(mutate), "asserted locator")

    def test_replay_claim_without_ready_evidence_fails(self):
        def mutate(root: Path) -> None:
            def claim(registry):
                registry["sources"][0]["replay_status"] = "reproduced"

            self._edit_json(root / "fixtures/historical_sources.json", claim)

        self.assertFails(self._mutated_result(mutate), "claims replay without")


class RuntimeAndTemplateTests(ProgramTreeTestCase):
    def test_unsandboxed_fallback_fails(self):
        def mutate(root: Path) -> None:
            self._edit_json(
                root / "security/runtime_profile.json",
                lambda profile: profile["isolation"].__setitem__(
                    "unsandboxed_fallback", True
                ),
            )

        self.assertFails(self._mutated_result(mutate), "unsandboxed fallback")

    def test_gate_template_missing_field_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / "docs/plans/templates/gate_decision_record.md",
                lambda text: text.replace("## Authorized Scope", "## Scope"),
            )

        self.assertFails(self._mutated_result(mutate), "template omits")

    def test_unpinned_jsonschema_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / "requirements-dev.txt",
                lambda text: text.replace("jsonschema==4.26.0", "jsonschema>=4.26.0"),
            )

        self.assertFails(self._mutated_result(mutate), "pin jsonschema==4.26.0")

    def test_verification_ladder_missing_runner_fails(self):
        def mutate(root: Path) -> None:
            self._edit_text(
                root / PROGRAM,
                lambda text: text.replace("tools/run_regression_replay.py", ""),
            )

        self.assertFails(self._mutated_result(mutate), "verification ladder omits")


if __name__ == "__main__":
    unittest.main()
