# Bounded schema replay repair — 28 October 2026

The recovered executor gate failed after 1800 seconds (11/12 cases finished).
The 90-second offline profile attributes 56.94 seconds to 261 JSON Schema
meta-validation calls, including 260 repeated active-session schema builds.
This is measured local work, not evidence of a provider outage or lock deadlock.
The oversized successor reached pass/seal; its repeat/accounting assertions
remain unproved. Production remains 166 retained / 439 unfinished.

## Repair and verification

1. Add prospective v3 operation-scoped reuse of successful schema-definition
   checks only. Rebuild the candidate schema and check its profile/base/template
   contracts every time. Key reuse by exact canonical schema bytes and current
   checker identity/definition; bound memory and discard state on outer exit.
2. Execute the unchanged historical schema builder in a private globals mapping.
   Do not edit frozen source, replace global jsonschema methods, cache record
   validity, or cache account/receipt acceptance. Restore shared bindings on
   normal and exceptional exits; nested operations share only their outer scope.
3. Compose this scope at v3 preparation, runtime and settlement boundaries so
   mixed-history replay receives the optimization without changing eligibility.
4. Test exact repeated schemas, changed bytes/profile/template/base bindings,
   invalid schemas/records, checker changes, nested scopes, exceptional unwind,
   bounded eviction and historical binding restoration. Measure avoided work
   with call counts; rerun the native oversized case and fixed executor suite.
5. Obtain one bounded findings-only review, fix findings and retest. Refresh
   master/checkpoint evidence. A changed source invalidates prior full-release
   receipts. Continue the reviewed ownership slice only after the executor gate.

No timeout increase, provider calls, production authority writes, deployment,
commit or push is part of this offline repair. The 1800-second executor bound
remains unchanged. TX3b–TX7 and downstream ZLB gates remain required.

## Execution checkpoint

The prospective helper is wired into v3 preparation, receipt replay, runtime,
settlement and execution. It retains no record/account acceptance and rebuilds
schemas before checking exact canonical bytes. It also binds checker identity,
meta-schema and selected validator/format-checker construction inputs.
24 dedicated cases plus adjacent native-runtime, floor-follow-up and runner
regressions pass: 104 total in 15.00 seconds with 16 workers. Ruff passes after
import-only cleanup. The fixed 12-case executor gate is running under its
original 1800-second bound at
`validation/c618909d2b9f9ac4a7a2/executor-b32b709d87c2`. Source/tests are frozen
for that receipt. One independent findings-only inspector is reviewing the
repair; no executor pass or review closure is claimed yet.

The preceding running status is superseded. Review reproduced R1–R4 (key
type ambiguity, type-checker drift, registry/resource drift and independent
context overlap). Executor run b32b709d87c2 was deliberately interrupted after
6 passes in 305.25 seconds before repair; its terminal failure receipt has
unchanged source/authority and successful cleanup. It is not acceptance.
Repairs add strict JSON-native reusable keys, effective registry/resource/anchor
and type-checker snapshots, and synchronized exclusive scope installation.
Unsupported representations/configurations use native checks. Regression
coverage includes native rejection oracles and both overlap exit orders with
normal/exceptional unwind. All 33 dedicated cases pass in 15.48 seconds; Ruff
passes. Affected integration tests and same-inspector residual review are
running before the next exact executor gate.

Affected integration validation now passes 113 cases in 14.77 seconds with
16 workers. The final-candidate exact executor rerun is running at
`validation/ad790b57f0228f286c11/executor-ff905888ca5f`. A diagnostic of unchanged
RuntimeManifest definitions measured native check 0.07918 seconds versus
warm reuse 0.002397 seconds (about 33x for this operation). This is not an
end-to-end speedup claim or an acceptance test. Residual review is pending.

Final review checkpoint supersedes the preceding running status: custom
positional legacy resolver defaults also require native fallback. Added that
guard and both legacy/keyword resolver regressions; the keyword test fixture
uses the actual meta-schema base URI. All 115 affected cases, including 35
dedicated cases, pass in 14.15 seconds. Ruff passes. Independent final review
closes R1–R4 with no remaining finding; inspector closed. The intermediate
ff905888ca5f gate was interrupted/failed before repair with unchanged source
and production authority; cleanup completed. The reviewed frozen-source gate
is now running at `validation/408012e9b655b2e389b1/executor-0a3e19afec9f`.
Do not edit source/tests until its terminal receipt.

Final executor gate now PASSES all 12 exact-member cases in 902.112 test
seconds (904.13 runner seconds), including the oversized split and all final
repeat/accounting assertions. Source and production authority are unchanged.
The original 1800-second bound is unchanged. Same-source exact floors gate
`408012e9b655b2e389b1/floors-5dd639f5fc1e` remains running; its source freeze
continues. Execution report has full membership/evidence hashes.
