import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from survey_audit import (
    AuditFailure,
    CANONICAL_PROPOSAL_ARTIFACTS,
    DEFAULT_PROTOCOL,
    DEFAULT_SEEDS,
    DOSSIER_ARTIFACTS,
    EVIDENCE_PUBLICATION_NAMES,
    LEGACY_DOSSIER_ARTIFACTS,
    ROOT,
    candidate_identity,
    known_item_audit,
    make_corpus,
    parse_bibtex,
    integrity_checks,
    verify_artifact_manifest,
    write_artifact_manifest,
    audit_evidence_identities,
    audit_bibliography_identities,
    dossier_artifacts,
    evidence_publication_pairs,
    gate_rows,
    package_selection_record,
    prepare_output_directory,
    select_screening_queue,
    title_similarity,
    validate_inputs,
    write_review_flow,
    overlay_review_file,
    read_manual_imports,
)


class SurveyAuditTests(unittest.TestCase):
    def test_audit_publication_cannot_target_authored_proposal(self):
        destinations = {destination for _, destination in evidence_publication_pairs(DOSSIER_ARTIFACTS)}
        self.assertTrue(destinations)
        self.assertTrue(destinations <= EVIDENCE_PUBLICATION_NAMES)
        self.assertFalse(destinations & CANONICAL_PROPOSAL_ARTIFACTS)
        self.assertFalse(EVIDENCE_PUBLICATION_NAMES & CANONICAL_PROPOSAL_ARTIFACTS)
        self.assertNotIn("humanvoice_implementation_dossier.md", destinations)
        self.assertNotIn("humanvoice_implementation_dossier.tex", destinations)
        self.assertNotIn("humanvoice_implementation_dossier.pdf", destinations)
        self.assertNotIn("humanvoice_product_proposal_audit.md", destinations)

    def test_legacy_dossier_names_remain_valid_for_preserved_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            for key in ("markdown", "tex", "render"):
                (run_dir / LEGACY_DOSSIER_ARTIFACTS[key]).write_text("legacy\n", encoding="utf-8")
            self.assertEqual(dossier_artifacts(run_dir), LEGACY_DOSSIER_ARTIFACTS)

    def test_bibliography_is_parsed_without_external_dependency(self):
        records = parse_bibtex(ROOT / "docs/survey/humanvoice_survey.bib")
        self.assertGreaterEqual(len(records), 35)
        self.assertEqual(records[0]["key"], "kobak2025delving")
        self.assertTrue(records[0]["title"])

    def test_arxiv_identifier_is_not_reported_as_doi(self):
        records = parse_bibtex(ROOT / "docs/survey/humanvoice_survey.bib")
        kobak = next(row for row in records if row["key"] == "kobak2025delving")
        self.assertEqual(kobak["doi"], "")
        self.assertEqual(kobak["identifier"], "arXiv:2406.07016")
        self.assertEqual(kobak["url"], "https://arxiv.org/abs/2406.07016")
        doshi = next(row for row in records if row["key"] == "doshi2024generative")
        self.assertEqual(doshi["doi"], "10.1126/sciadv.adn5290")

    def test_software_protocol_uses_current_ltex_successor(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
        candidates = protocol["software"]["adoption_candidates"]
        seeds = {row["name"]: row for row in protocol["software"]["registry_seeds"]}
        self.assertIn("LTeX+ LS", candidates)
        self.assertNotIn("ltex-ls", candidates)
        self.assertNotIn("proselint", candidates)
        self.assertEqual(seeds["LTeX+ LS"]["repository"], "https://github.com/ltex-plus/ltex-ls-plus")

    def test_frozen_inputs_and_requirement_links_are_valid(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
        seeds = json.loads(DEFAULT_SEEDS.read_text(encoding="utf-8"))
        result = validate_inputs(protocol, seeds)
        self.assertEqual(result["status"], "pass", result["errors"])
        self.assertEqual(result["counts"]["product_requirements"], 24)

    def test_input_validation_rejects_duplicate_evidence_and_unknown_requirement_link(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
        seeds = json.loads(DEFAULT_SEEDS.read_text(encoding="utf-8"))
        seeds.append(dict(seeds[0]))
        protocol["product_requirements"][0]["evidence_ids"].append("E-NOT-REAL")
        result = validate_inputs(protocol, seeds)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("evidence IDs contains duplicates" in error for error in result["errors"]))
        self.assertTrue(any("unknown evidence" in error for error in result["errors"]))

    def test_requirement_export_matches_protocol_without_leaking_ids_into_narrative(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
        exported = json.loads(
            (ROOT / "docs/survey/humanvoice_product_requirements.json").read_text(
                encoding="utf-8"
            )
        )
        survey = (ROOT / "docs/survey/part5_proposal.tex").read_text(encoding="utf-8")
        expected = [
            (row["id"], row["title"], row["statement"], row["acceptance_test"])
            for row in protocol["product_requirements"]
        ]
        actual = [
            (row["id"], row["title"], row["statement"], row["acceptance_test"])
            for row in exported["requirements"]
        ]
        self.assertEqual(actual, expected)
        self.assertNotRegex(survey, r"\bR(?:[1-9]|1[0-9])\b")

    def test_nonempty_output_requires_explicit_recoverable_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            output.mkdir()
            (output / "marker.txt").write_text("old\n", encoding="utf-8")
            with self.assertRaises(AuditFailure):
                prepare_output_directory(output)
            backup = prepare_output_directory(output, replace=True)
            self.assertIsNotNone(backup)
            self.assertTrue((backup / "marker.txt").is_file())
            self.assertTrue(output.is_dir())
            self.assertEqual(list(output.iterdir()), [])

    def test_title_identity_prefers_doi(self):
        self.assertEqual(candidate_identity({"doi": "10.1234/ABC", "title": "One"}), "doi:10 1234 abc")
        self.assertEqual(candidate_identity({"identifier": "arXiv:2406.07016", "title": "One"}), "identifier:arxiv 2406 07016")
        self.assertTrue(candidate_identity({"title": "A useful study"}).startswith("title:"))

    def test_title_similarity_is_order_insensitive(self):
        self.assertGreater(title_similarity("A Study of Human AI Writing", "Human-AI writing: a study"), 0.7)
        self.assertGreater(title_similarity("Coh-{M}etrix: analysis of text", "Coh-Metrix: Analysis of text"), 0.9)
        self.assertEqual(title_similarity("", "something"), 0.0)

    def test_gate_uses_actual_doi_shape_for_load_bearing_identity(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
        known = {"offline": False, "recall": 1.0, "challenge_recall": 1.0, "search_retrieved": 1, "challenge_retrieved": 1, "total": 1}
        evidence = [{"id": "E-1", "source_type": "primary-study", "load_bearing": True, "doi": "arXiv:2406.07016", "identity_status": "verified"}]
        with tempfile.TemporaryDirectory() as directory:
            gates = {item["gate"]: item for item in gate_rows(protocol, True, known, [], evidence, [], [], {"literature_records": 1, "literature_provenance_records": 1}, Path(directory))}
            self.assertEqual(gates["bibliographic-identity"]["status"], "fail")

    def test_known_item_seed_is_not_counted_as_search_recall(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
        candidates = {"x": {"title": protocol["literature"]["known_items"][0]["title"], "provenance": [{"source": "known-item-seed"}]}}
        result = known_item_audit(protocol, candidates, [], online=False)
        self.assertEqual(result["search_retrieved"], 0)
        self.assertTrue(result["offline"])

    def test_known_item_doi_matching_is_not_substring_matching(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
        protocol["literature"]["known_items"] = [{"id": "K", "title": "Target study", "doi": "10.1234/abc"}]
        candidates = {
            "x": {
                "title": "Unrelated title",
                "doi": "10.1234/abc-extra",
                "provenance": [{"source": "crossref", "search_mode": "broad"}],
            }
        }
        result = known_item_audit(protocol, candidates, [], online=True)
        self.assertEqual(result["search_retrieved"], 0)
        self.assertEqual(result["rows"][0]["status"], "missing")

    def test_corpus_is_locked_and_manifested(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            corpus = make_corpus(run_dir)
            manifest = json.loads((run_dir / "corpus/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(corpus), 4)
            self.assertEqual(len(manifest), 4)
            self.assertTrue((run_dir / "corpus/C-002.txt").is_file())

    def test_screening_queue_is_stable_and_includes_known_items(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
        protocol["screening"]["manual_review_sample_size"] = 3
        rows = [
            {"screening_id": "S-known", "candidate_identity": "known", "screening_decision": "known-item-manual-screen-required", "known_item": "yes"},
            *[
                {"screening_id": f"S-{i}", "candidate_identity": f"candidate-{i}", "screening_decision": "manual-screen-required", "known_item": "no"}
                for i in range(10)
            ],
        ]
        first = [row.copy() for row in rows]
        second = [row.copy() for row in rows]
        select_screening_queue(first, protocol)
        select_screening_queue(second, protocol)
        self.assertEqual(first, second)
        self.assertEqual(sum(row["selected_for_manual_review"] == "yes" for row in first), 3)
        self.assertEqual(first[0]["selected_for_manual_review"], "yes")

    def test_integrity_check_detects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            raw = run_dir / "raw.json"
            raw.write_text("{}", encoding="utf-8")
            result = integrity_checks(
                run_dir,
                [{"raw_response": "raw.json", "raw_sha256": "wrong"}],
                [{"candidate_id": "C-1", "candidate_identity": "title:x", "provenance": [{"source": "test"}]}],
                [],
                [{"id": "E-1", "source_provenance": "test"}],
                [{"name": "tool", "provenance_status": "remote-only"}],
            )
            self.assertEqual(result["status"], "fail")
            self.assertFalse(result["checks"]["raw_responses_hash"])

    def test_artifact_manifest_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "a.txt").write_text("stable\n", encoding="utf-8")
            write_artifact_manifest(run_dir)
            self.assertEqual(verify_artifact_manifest(run_dir)["status"], "pass")
            (run_dir / "a.txt").write_text("changed\n", encoding="utf-8")
            self.assertEqual(verify_artifact_manifest(run_dir)["status"], "fail")

    def test_artifact_manifest_detects_unrecorded_file(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "a.txt").write_text("stable\n", encoding="utf-8")
            write_artifact_manifest(run_dir)
            (run_dir / "late.txt").write_text("not manifested\n", encoding="utf-8")
            result = verify_artifact_manifest(run_dir)
            self.assertEqual(result["status"], "fail")
            self.assertIn("unrecorded:late.txt", result["mismatches"])

    def test_evidence_identity_audit_is_explicit_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "raw").mkdir()
            evidence = [{"id": "E-1", "title": "A Study", "year": 2024, "doi": "10.1234/example"}]
            events = []
            summary = audit_evidence_identities(evidence, run_dir, events, online=False)
            self.assertEqual(summary["doi_rows"], 1)
            self.assertEqual(summary["verified"], 0)
            self.assertEqual(evidence[0]["identity_status"], "not-run-offline")
            self.assertEqual(events[0]["mode"], "bibliographic-identity")
            self.assertTrue((run_dir / "evidence_identity_audit.csv").is_file())

    def test_bibliography_identity_audit_separates_dois_and_identifiers(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "raw").mkdir()
            bibliography = [
                {"key": "doi-row", "title": "A Study", "year": "2024", "doi": "10.1234/example", "identifier": "",},
                {"key": "arxiv-row", "title": "A Preprint", "year": "2024", "doi": "", "identifier": "arXiv:2406.07016",},
                {"key": "plain-row", "title": "A Note", "year": "2024", "doi": "", "identifier": "",},
            ]
            events = []
            summary = audit_bibliography_identities(bibliography, run_dir, events, online=False)
            self.assertEqual(summary["doi_rows"], 1)
            self.assertEqual(summary["verified"], 0)
            self.assertEqual(summary["identifier_only"], 1)
            statuses = {row["bib_key"]: row["status"] for row in summary["rows"]}
            self.assertEqual(statuses["doi-row"], "not-run-offline")
            self.assertEqual(statuses["arxiv-row"], "identifier-only")
            self.assertEqual(statuses["plain-row"], "not-applicable-no-doi")
            self.assertTrue((run_dir / "bibliography_identity_audit.csv").is_file())
            self.assertTrue((run_dir / "bibliography_identity_summary.json").is_file())

    def test_review_flow_does_not_count_unadjudicated_rows_as_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [
                {"selected_for_manual_review": "yes", "screening_decision": "manual-screen-required", "adjudication": "include"},
                {"selected_for_manual_review": "yes", "screening_decision": "manual-screen-required", "adjudication": ""},
            ]
            flow = write_review_flow(Path(directory), [{}, {}], rows)
            self.assertEqual(flow["records_dual_reviewed_and_adjudicated"], 1)
            self.assertEqual(flow["records_awaiting_dual_review"], 1)
            self.assertEqual(flow["status"], "screening-pending")

    def test_blank_overlay_is_not_counted_as_human_update(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "screening_review.csv"
            path.write_text("screening_id,reviewer_1,adjudication\nS-1,,\n", encoding="utf-8")
            rows = [{"screening_id": "S-1", "reviewer_1": "", "adjudication": ""}]
            self.assertEqual(overlay_review_file(path, rows, "screening_id", ["reviewer_1", "adjudication"]), 0)

    def test_generated_evidence_metadata_is_not_a_review_update(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence_review.csv"
            path.write_text("id,load_bearing\nE-1,True\n", encoding="utf-8")
            rows = [{"id": "E-1", "load_bearing": True}]
            self.assertEqual(overlay_review_file(path, rows, "id", ["inspection", "claim_anchor"]), 0)

    def test_review_overlays_and_sidecars_are_not_literature_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            import_dir = Path(directory)
            (import_dir / "source.csv").write_text(
                "title,authors,year,url\nA source,An Author,2025,https://example.test/source\n",
                encoding="utf-8",
            )
            import hashlib
            source_hash = hashlib.sha256((import_dir / "source.csv").read_bytes()).hexdigest()
            (import_dir / "source.meta.json").write_text(
                json.dumps({
                    "database": "RePEc/IDEAS",
                    "source_url": "https://example.test/export",
                    "retrieved_at": "2026-08-24T00:00:00Z",
                    "sha256": source_hash,
                    "query_or_filter": "test",
                }),
                encoding="utf-8",
            )
            (import_dir / "screening_review.csv").write_text("screening_id,reviewer_1\nS-1,\n", encoding="utf-8")
            (import_dir / "evidence_review.csv").write_text("id,claim_anchor\nE-1,\n", encoding="utf-8")
            (import_dir / "review_packet_manifest.json").write_text("{}\n", encoding="utf-8")
            events, candidates, software = [], {}, {}
            summary = read_manual_imports({"manual_import_dir": str(import_dir)}, events, candidates, software)
            self.assertEqual(summary["literature_records"], 1)
            self.assertEqual(summary["literature_provenance_records"], 1)
            self.assertEqual(summary["literature_files"], 1)

    def test_generic_smoke_pass_cannot_promote_package(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
        protocol["software"]["adoption_candidates"] = ["example"]
        inventory = [{"name": "example", "repository": "https://example.test/repo", "source": "protocol-seed", "provenance_status": "remote-only"}]
        generic = package_selection_record(protocol, inventory, [{"package": "example", "status": "pass"}])
        effective = package_selection_record(protocol, inventory, [{"package": "example", "status": "effectiveness-pass"}])
        self.assertEqual(generic["records"][0]["decision"], "hold-pending-held-out-benchmark")
        self.assertEqual(effective["records"][0]["decision"], "adopt-pending-independent-review")

    def test_excluded_screening_record_requires_frozen_reason_code(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
        row = {
            "selected_for_manual_review": "yes",
            "reviewer_1": "exclude",
            "reviewer_2": "exclude",
            "adjudication": "exclude",
            "exclusion_code": "",
        }
        with tempfile.TemporaryDirectory() as directory:
            args = (protocol, True, {"offline": False, "recall": 1.0, "challenge_recall": 1.0, "search_retrieved": 1, "challenge_retrieved": 1, "total": 1}, [row], [], [], [], {"literature_records": 1, "literature_provenance_records": 1}, Path(directory))
            before = {item["gate"]: item for item in gate_rows(*args)}
            self.assertEqual(before["manual-independent-screening"]["status"], "fail")
            row["exclusion_code"] = "NOT-A-FROZEN-CODE"
            invalid = {item["gate"]: item for item in gate_rows(*args)}
            self.assertEqual(invalid["manual-independent-screening"]["status"], "fail")
            row["exclusion_code"] = "E1"
            after = {item["gate"]: item for item in gate_rows(*args)}
            self.assertEqual(after["manual-independent-screening"]["status"], "pass")

    def test_full_text_gate_accepts_protocol_hyphenated_value(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
        known = {"offline": False, "recall": 1.0, "challenge_recall": 1.0, "search_retrieved": 1, "challenge_retrieved": 1, "total": 1}
        evidence = [{
            "id": "E-1",
            "source_type": "primary-study",
            "load_bearing": True,
            "inspection": "full-text methods and results",
            "independent_verification": "verified",
            "appraisal_status": "completed-low-concern",
            "claim_anchor": "p. 4, Table 1",
            "limitations": "single setting",
        }]
        with tempfile.TemporaryDirectory() as directory:
            gates = gate_rows(protocol, True, known, [], evidence, [], [], {"literature_records": 1, "literature_provenance_records": 1}, Path(directory))
            by_name = {item["gate"]: item for item in gates}
            self.assertEqual(by_name["full-text-load-bearing-evidence"]["status"], "pass")

    def test_public_slice_does_not_satisfy_specialist_domain_gate(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
        known = {"offline": False, "recall": 1.0, "challenge_recall": 1.0, "search_retrieved": 1, "challenge_retrieved": 1, "total": 1}
        args = (protocol, True, known, [], [], [], [], {"literature_records": 1, "literature_provenance_records": 1, "databases": ["NBER generative AI workplace"]}, Path(tempfile.mkdtemp()))
        public_only = {item["gate"]: item for item in gate_rows(*args)}
        self.assertEqual(public_only["domain-database-imports"]["status"], "pass")
        self.assertEqual(public_only["specialist-domain-coverage"]["status"], "fail")
        args = (protocol, True, known, [], [], [], [], {"literature_records": 1, "literature_provenance_records": 1, "databases": ["EconLit licensed export"]}, args[-1])
        specialist = {item["gate"]: item for item in gate_rows(*args)}
        self.assertEqual(specialist["specialist-domain-coverage"]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
