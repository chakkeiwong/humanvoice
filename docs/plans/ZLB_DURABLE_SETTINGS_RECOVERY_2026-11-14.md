# ZLB recovery that survives an editor reload

## Observed failure and scope

The prior continuation was committed (3e1181d; progress checkpoint bd84be3)
and started successfully. A further editor reload killed its captured control
process. At November 14, 02:36:16 Shanghai the host verifier rejected that
process, stopping ZLB before a new paid allocation. All 110 retained responses,
135 used slots and 42 remaining slots are unchanged.

The replacement editor capture differs only in PID and start ticks. Same thread,
same 0.169 configuration-reader executable, same settings and credentials.
Production execution remains on the qualified pinned 0.164 executable.

## Repair plan and reviewed boundary

Decouple the interactive editor process lifetime from execution. The verifier
still reads the latest session context for this thread, resolves native effective
configuration with the same installed configuration reader and exact overrides,
and compares the model, effort, provider URL/options, configuration layers,
approval settings, environment hash and shared credential-file hash. Verify
the configuration reader and qualified execution binaries by exact SHA-256.
Read context/environment/credential hashes again to detect a concurrent edit.
A process ID is neither configuration nor a prerequisite for background work.

Do not adopt a foreign session or substitute a new client. Keep the current
captured binding as provenance; exclude only PID and process start ticks from
stable settings identity. A configuration/credential/client/thread change
still blocks before transmission. The existing user-session, gateway and
native allocation evidence remain unchanged. Add a durable-settings marker to
each new runtime, bound to the exact verified contract and prior session marker.
No approval, sandbox, source permission, STOP, deadline, reservation or known
negative judgment is waived.

The ordinary-user host verifier offers the same hash-only IPC operation to
the sandbox. Spawned workers install the same runtime scopes. Header/credential
values never enter logs or marker files. Editor exit is covered by an actual
native config check using the dead original PID as historical provenance.

The supervisor now publishes its host preflight phase and errors so it does
not silently leave stale status if startup fails before the child launches.
Its established 900-second provider, 1050-second scheduler and 15-minute
network-backoff policies remain. Semantic failure routing is unchanged.

## Verification and execution

Test exact settings drift rejection, native verification after editor exit,
runtime markers and tamper rejection, real native success/failure accounting,
old/new replay, restart reconciliation, worker serialization/scopes and
restoration. Reuse the unchanged source/evidence-bound full baseline and
qualified request commands; verify all retained bank/account bytes offline.
Before deployment, verify 16 actual host-to-sandbox clients and start the pinned
request client in the production namespace with networking disabled.

After passing tests, refresh both masters, commit focused paths, disable the
failed predecessor and install/start the ordinary-user successor in one grouped
host action. No sudo. Verify actual provider progress before describing it as
working. Keep the November 20, 17:03:49 Shanghai deadline and shared 177 slots.

## Remaining document phases

Five unit repairs and automatic independent reviews precede assembled
relationships/build/release checks, benchmark/regression, separately budgeted
reproduction and final human review. The assembled-semantic-rejection recovery
gap remains documented in ZLB_SESSION_BINDING_REPAIR_2026-11-13.md. This
operational recovery does not claim final ZLB acceptance.

## Verified readiness

All 20 tests pass in 54.69 seconds. The actual native configuration verifier
accepts the dead original editor binding while independently validating all
current settings and hashes. The offline retained-bank/account check passes in
1.35 seconds with zero model calls and accounting writes. Source-bound
predecessor evidence remains intact. Ruff passes; the execution review is READY.
Host/sandbox parity and isolated startup run before user-service installation.

## Actual service environment correction

The first durable-service launch failed before allocation because its manager
did not supply CODEX_INTERNAL_ORIGINATOR_OVERRIDE=codex_vscode. A comparison of
only key names and hashes established this as the sole differing environment
entry; credentials, proxies and homes match. The unit now sets this non-secret
client-identification value explicitly. Before production installation, a
transient ordinary-user service runs the full preflight under that same manager
environment. This closes the earlier shell-versus-service preflight gap.
The installed service may be replaced only if its bytes match the exact prior
reviewed unit or this updated unit. Failure evidence is retained separately;
the original 135 paid attempts remain unchanged.

The corrected implementation passes all 21 regressions in 52.94 seconds; the
retained-bank/account check passes again in 1.34 seconds with zero paid calls.
The configuration review and publication payload are refreshed for the actual
user-service preflight and bounded replacement of the previously installed unit.
