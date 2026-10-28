# Prospective control witness and publication candidate — 28 October 2026

This is an offline implementation candidate outside the frozen recovery source/test binding. It is not imported by the public runtime, supplies no production admission, and installs no service.

The slice contains durable witness storage, authenticated read-only transport, exact stop/resume semantics, crash-recoverable witness-first local publication, protected path handling, and native RuntimeLeaf evidence integration. Initialization is separately retained as a monotonic witness phase and is never recreated after completion.

The candidate is not an authenticated host writer. Its production-facing publisher currently checks the effective UID and protected database, but does not validate a human approval token or authenticate the privileged request source. In particular, it must not be exposed as a root CLI or service action until a fixed host broker/installer establishes that provenance. Protected SQLite bootstrap after a process crash also remains a separate installer/recovery problem.

The refreshed validation passes 147 cases with 16 workers and Ruff. Exact collection/execution membership is recorded in `candidate-status.json`; the approval-policy regression passes 56 tests.

Production remains stopped. Host installation, independent review, public factory wiring, supervisor diagnostics, long-history bounds, TX4–TX7, native soak, release admission, and live ZLB execution remain open.
