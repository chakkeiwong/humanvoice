"""Revalidate completed bootstrap ownership against its immutable journal."""

from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

from humanvoice import codex_runtime
from humanvoice.artifacts import digest, read_json
from tools import sol_inventory_program as original
from tools.inventory_recovery_v3 import accounting, campaign_history, probe, runtime
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.requests import NativeRequests
from tools.inventory_recovery_v3.reservations import RecoveryReservations, regular_path
from tools.inventory_recovery_v3.stage import receipt_replay


class RetainedJournal(RecoveryReservations):
    def __init__(self, root, policy, binding, record, check):
        super().__init__(root, policy, binding)
        self.retained = deepcopy(record)
        self.publication_check = check

    @contextmanager
    def locked(self, *, reconcile=True):
        self.check()
        yield
        self.check()

    def read(self):
        self.check()
        return deepcopy(self.retained)

    def save(self, record):
        self.check()
        if campaign_history.identified(record) != self.retained:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Prepared ownership requires missing journal membership")


def inspect(plan, output, transition, binding, check):
    document = plan[runtime.FIELD]["policy"]
    journal_descriptor = binding["recovery_journal"]
    journal = RetainedJournal(output.parent / "recovery-journal", document,
        journal_descriptor["binding"], binding["initial_journal"], check)
    with accounting.document_scope(transition), receipt_replay(plan, output,
            plan[original.adapter.FIELD]["predecessor"], codex_runtime.validate_codex_record) as checked, (
            runtime.runtime(plan, output, historical_validate=checked)):
        resolver = NativeRequests(plan, output, journal, SimpleNamespace(check=check))
        observations = probe.observations(SimpleNamespace(output=output, transition=transition),
            read_json(regular_path(output / "admission-probe.json")))
        resolver.import_history(observations)
        last = observations[-1]
        lineage, scope = resolver.extraction(last) if last["purpose"] == "concept_extraction" else (
            resolver.critic(last, observations))
        imported = journal.read()["inherited_recovery"]["sequences"]
        roots = Counter(row["root"] for row in imported.values())
        lineages = Counter(row["lineage"] for row in imported.values())
        resolver.import_history(observations)
        parent = plan[runtime.FIELD]["parent_failure"]
        diagnostic = resolver.diagnostic_handoff(parent)
        if (roots[lineage["root"]] >= document["root_sequences"]
                or lineages[lineage["identity"]] >= document["lineage_sequences"]
                or diagnostic is None or journal.read()["sequences"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Prepared ownership cannot admit its first recovery pair")
        journal.reserve(lineage=lineage["identity"], incident=digest(parent),
            request_hash=digest(last["request"]), profile_hash=digest(plan["profile"]),
            inherited_diagnostic=diagnostic, check_only=True)
    return {"historical_sequences": len(imported), "root_counts": dict(roots),
        "lineage_counts": dict(lineages), "unfinished_lineage": lineage["identity"],
        "unfinished_root": lineage["root"], "unfinished_scope": scope,
        "unfinished_root_sequences": roots[lineage["root"]],
        "unfinished_lineage_sequences": lineages[lineage["identity"]],
        "observations": len(observations), "new_reservations": 0, "import_idempotent": True}
