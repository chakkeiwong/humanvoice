"""Derive punctuation ownership from supported concepts without altering receipts."""

from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from humanvoice.artifacts import digest, load_spans, read_json, validate_snapshot
from humanvoice.model_extraction import CoverageVerdict
from tools.inventory_transport_continuation import immutable

ROOT = Path(__file__).resolve().parents[1]
VERSION = "inventory-grounded-punctuation-v1"
MARKER = ".humanvoice/inventory/punctuation-policy.json"
FILES = ("tools/inventory_punctuation.py",)
PUNCTUATION = {":", ";", ",", "."}
ACTIVE_DERIVATIONS = None


@dataclass
class OwnedPunctuation(CoverageVerdict):
    punctuation_ownership: dict = field(default_factory=dict)


def policy(snapshot):
    manifest = validate_snapshot(Path(snapshot))
    return {"version": VERSION, "manifest_sha256": digest(manifest),
            "source_hash": manifest["source_hash"], "punctuation": sorted(PUNCTUATION),
            "rule": "unique-supported-concept-owns-both-adjacent-math-spans",
            "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
            "provider_verdicts_unchanged": True, "source_bytes_unchanged": True}


def enable(snapshot):
    immutable(Path(snapshot) / MARKER, policy(snapshot))


def span_basis(span):
    return {key: span[key] for key in ("record_id", "source_file", "byte_start", "byte_end",
                                      "span_kind", "reader_facing", "exact_text")}


def derive(spans, concepts, verdicts, window, reconstruction):
    wanted = {span["record_id"] for span in spans}
    local = {concept.concept_id: concept for concept in concepts}
    rows = {span["record_id"]: span for span in window}
    recon = {row.concept_id: row for row in reconstruction}
    if (len(wanted) != len(spans) or len(rows) != len(window) or len(local) != len(concepts)
            or len(verdicts) != len(wanted) or {row.span_id for row in verdicts} != wanted
            or len(recon) != len(reconstruction) or set(recon) != set(local)
            or not wanted <= rows.keys()
            or any(span_basis(rows[span["record_id"]]) != span_basis(span) for span in spans)
            or any(row.verdict != "supported" or not row.reconstruction or not row.comparison
                   or not row.evidence_span_ids or not set(row.evidence_span_ids) <= rows.keys()
                   for row in reconstruction)
            or any(row.verdict != "covered" or not row.explanation
                   or not set(row.mapped_concept_ids) <= local.keys() for row in verdicts)):
        raise ValueError("Punctuation ownership requires complete positive source-grounded judgments")
    ordered = sorted(window, key=lambda span: (span["source_file"], span["byte_start"]))
    positions = {span["record_id"]: index for index, span in enumerate(ordered)}
    result = []
    for verdict in verdicts:
        if verdict.mapped_concept_ids:
            result.append(verdict)
            continue
        span = rows[verdict.span_id]
        position = positions[verdict.span_id]
        if (span["span_kind"] != "prose" or not span["reader_facing"]
                or span["exact_text"].strip(" \t\r\n") not in PUNCTUATION
                or not 0 < position < len(ordered) - 1):
            raise ValueError("Unmapped coverage is not eligible standalone punctuation")
        left, right = ordered[position - 1], ordered[position + 1]
        if (left["source_file"] != span["source_file"] or right["source_file"] != span["source_file"]
                or left["byte_end"] != span["byte_start"] or span["byte_end"] != right["byte_start"]
                or any(row["span_kind"] != "math" or not row["reader_facing"] for row in (left, right))):
            raise ValueError("Punctuation lacks contiguous reader-facing math boundaries")
        anchors = {left["record_id"], right["record_id"]}
        owners = [concept for concept in concepts
                  if anchors <= set(concept.source_span_ids + concept.supporting_spans)
                  and anchors <= set(recon[concept.concept_id].evidence_span_ids)
                  and set(concept.source_span_ids + concept.supporting_spans) <= rows.keys()
                  and any(rows[identifier]["span_kind"] == "prose"
                          and any(character.isalnum() for character in rows[identifier]["exact_text"])
                          for identifier in concept.source_span_ids)]
        if len(owners) != 1:
            raise ValueError("Punctuation requires one unambiguous supported owner")
        owner = owners[0]
        proof = {"version": VERSION, "raw_coverage": asdict(verdict),
                 "owner_concept_id": owner.concept_id, "owner_sha256": digest(asdict(owner)),
                 "reconstruction_sha256": digest(asdict(recon[owner.concept_id])),
                 "context": [span_basis(row) for row in (left, span, right)]}
        result.append(OwnedPunctuation(span_id=verdict.span_id, verdict=verdict.verdict,
            explanation=verdict.explanation, mapped_concept_ids=[owner.concept_id], punctuation_ownership=proof))
    return result


def model_snapshot(model):
    snapshot = getattr(model, "snapshot", None)
    if snapshot is None:
        snapshot = getattr(getattr(model, "model", model), "snapshot_dir", None)
    return Path(snapshot).resolve() if snapshot is not None else None


@contextmanager
def runtime():
    global ACTIVE_DERIVATIONS
    from humanvoice import baseline_evidence, model_extraction
    from humanvoice.commands import inventory_command

    if ACTIVE_DERIVATIONS is not None:
        yield ACTIVE_DERIVATIONS
        return
    native_reconstruction = model_extraction.verify_reconstruction
    native_coverage = model_extraction.verify_coverage
    contexts, derivations = {}, []

    def reconstruct(concepts, spans, model, macro_display=None):
        result = native_reconstruction(concepts, spans, model, macro_display)
        contexts[id(model)] = (concepts, spans, result)
        return result

    def cover(spans, concepts, model, macro_display=None):
        verdicts = native_coverage(spans, concepts, model, macro_display)
        snapshot = model_snapshot(model)
        if snapshot is None or not (snapshot / MARKER).exists():
            return verdicts
        if read_json(snapshot / MARKER) != policy(snapshot):
            raise ValueError("Frozen punctuation policy or source changed")
        extracted, window, reconstruction = contexts.pop(id(model), (None, None, None))
        if extracted != concepts:
            raise ValueError("Punctuation coverage lost its independent reconstruction")
        source = load_spans(snapshot)
        if any(span_basis(span) != span_basis(source[span["record_id"]]) for span in window):
            raise ValueError("Punctuation context differs from immutable source")
        result = derive(spans, concepts, verdicts, window, reconstruction)
        derivations.extend(asdict(row) for row in result if isinstance(row, OwnedPunctuation))
        return result

    with ExitStack() as bindings:
        for module in (model_extraction, inventory_command, baseline_evidence):
            for name, value in (("verify_reconstruction", reconstruct), ("verify_coverage", cover)):
                bindings.callback(setattr, module, name, getattr(module, name))
                setattr(module, name, value)
        ACTIVE_DERIVATIONS = derivations
        try:
            yield derivations
        finally:
            ACTIVE_DERIVATIONS = None
