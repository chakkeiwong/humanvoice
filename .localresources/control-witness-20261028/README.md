# Offline control witness and publication candidate

Current checkpoint: 28 October 2026, master 4.32 / ensemble 222.

This isolated candidate implements durable witness storage, authenticated
read-only socket transport, exact stop/resume semantics, witness-first local
publication and native RuntimeLeaf evidence integration. It is not imported by
the public runtime and does not install a service or authorize model calls.

The current frozen gate passes 156 exact cases with 16 workers in 2.702 test
seconds; Ruff passes. Separate collection and execution membership match.
The receipt retains equal before/after hashes for 921 source/test/config files
and the three production account/grant authorities. See candidate-status.json
and validation/projection-f752e96e5f7f/validation.json. The separate approval
policy regression previously passed 56 cases. Earlier receipts are historical.

Reproduce the fixed offline gate with:

    /home/ubuntu/miniforge3/bin/python /home/ubuntu/workspace/humanvoice/.localresources/control-witness-20261028/run_validation.py run

New protection checks reject unsafe projection parents and inodes; partial
initialization tests cover missing directories without bypassing path checks.
The production publisher still requires a fixed protected installer and an
authenticated human-approved action. Root UID alone is not that provenance.
Tests explicitly substitute ownership/peer fixtures and cannot prove installed
host isolation. Review is coordinator-only.

The existing workspace-bound stop roots and private projection files require
a protected namespace/native reader design before host installation. Do not
chown the workspace, rebind historical roots or claim unprivileged native
read access from these fixtures. Database bootstrap recovery, stale sockets,
supervisor diagnostics, public factory composition, TX4–TX7, native soak and
dependency-complete release remain open. Production is stopped: 166 retained,
439 unfinished requests, no new ZLB receipt.
