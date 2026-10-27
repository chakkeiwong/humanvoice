# Installed authority bounded review — 28 October 2026

Scope: prospective offline TX3 installed authority and handover, their two focused test modules, and the closure plan. Read /home/ubuntu/AGENTS.md and repository AGENTS.md. Only this report is written.

## P2 — Double-leading-slash alias bypasses repeated ownership-root rejection

Location: tools/inventory_recovery_v3/installed_authority.py:10–15, called by handover.py:52; string-only repeated-root checks at handover.py:29–30.

On this Linux host, Path('//home/ubuntu/workspace/humanvoice') preserves both leading slashes, is absolute, and refers to the same directory as /home/ubuntu/workspace/humanvoice. The canonical-path predicate accepts it because its string is unchanged and contains no dot-dot; the symlink check also passes. Native safe_path preserves this spelling.

Independent read-only reproduction: extracted the existing regular_path, canonical_path and safe_path function definitions with ast, executed only those definitions, and called them on the existing repository path with two leading slashes. Output: canonical_path_result='//home/ubuntu/workspace/humanvoice', safe_path_result='//home/ubuntu/workspace/humanvoice', same_inode=True, root_equality_guard=False, seen_membership_guard=False. No application imports, fixture creation, tests or filesystem writes were needed. These predicates remain unchanged in the final inspected source.

Precise causal path: keep installed predecessor/configuration/records intact, but supply replacement='/' + str(current_root), or the same alias of an earlier predecessor. proposal accepts that replacement through canonical_path and native.safe_path. native.proposal snapshots the predecessor and embeds the supplied replacement string. validate_chain compares root strings, so the same physical directory is not recognized as the current or an already-used predecessor root. Rebuilding the record repeats the same accepted alias. The offline proposal/validation boundary can therefore accept self-handover or return to historical storage despite its distinct-root invariant. This does not establish an executed overwrite, budget renewal or live admission.

Suggested repair: reject the POSIX double-slash anchor in the prospective canonical-path boundary, or enforce a single canonical root representation before comparison. Add cases for double-leading-slash paths and aliased current/older replacement roots. The existing alias parametrization covers internal repeated slashes, relative paths, dot-dot and trailing slashes, but omits this case.

## Other inspected behavior

No additional concrete defect established in this bounded slice. Installed root/configuration/adoption and stop membership are independently derived. Proposal comparison rejects caller omissions and an older current-root assertion. Restart replay includes retained pending intent and each transfer charge. Predecessor descriptor checks bind inode identity, held ownership and exact membership; the focused tests use a real isolated child. These are static conclusions, not reviewer-run integration certification.

Final observe() hashes and parses the same content bytes and explicitly rejects nonobject JSON with TypeError; the focused expectation matches that local parser. Final require_running() checks stop and resume paths for symlinks before native control, including dangling links. Earlier exception-expectation failures and the superseded double-read implementation are not current findings.

## Limitations and plan boundaries

- No pytest run, broad validation, paid/model call, service operation, live launch, production capture or source/history mutation was performed by this inspector. No end-to-end alias handover fixture was run; the direct reproduction and causal path establish the finding.
- Coordinator reports current source-bound 522 tests and actual read-only handover pass. Those results were not independently rerun or receipt-audited. The older 520 receipt is not asserted as validation of final source.
- Installed shared locks are acquisition-time quiescence probes. Continuous common ownership through public cold entrypoints remains acknowledged integration work, not an additional defect attributed to this offline component.
- Exact account/grant/stages/cursor byte equality suits bounded offline transfer. Runtime spending needs separately defined lawful-extension validation; that acknowledged missing composition is neither completed TX3 nor a new offline defect.
- Full release/admission binding, both public restart entrypoints, successful stale-unspent reprepare, receipt-only progress, replay cost bounds, native successors/fallback and combined crash/soak coverage remain open in the closure plan. No deployment approval is implied.
- Proposed future offline-preparation wiring was not reviewed as an implemented change. No separate classifier module or additional suite was reviewed.

## Final inspected identities

| File | SHA-256 |
| --- | --- |
| tools/inventory_recovery_v3/installed_authority.py | 59a74b355b6180328bffae469784041ab3f7b1e206a99973a6a2a4382d548538 |
| tools/inventory_recovery_v3/handover.py | f496b46cbbb53a585c4c64e2b390178ed687093fb05a2710d160cd81cc800a6d |
| tests/test_inventory_recovery_v3_installed_authority.py | 5158ec5bf078043ef53f2ebc4af7f4d45248d3ae4a1fe734ddbe2d1d1cfc927e |
| tests/test_inventory_recovery_v3_handover.py | 5196748962bfb01482446f3c117bbb166ee1b58208b3fc1cd3546b4ae40e3d96 |

Disposition: one concrete P2 finding remains in the inspected offline slice; no claim of full TX3 closure.

## Follow-up — alias finding closed in source, 28 October 2026

This follow-up supersedes the preceding open-P2 disposition for the alias finding only. Bounded reread confirms canonical_path now requires path.anchor == '/' at tools/inventory_recovery_v3/installed_authority.py:12. POSIX double-leading-slash paths have anchor '//', so they are rejected before proposal can accept an aliased replacement. The existing unchanged-string and dot-dot checks remain in place. This closes the reported causal path for both current and older predecessor aliases.

The direct canonical-path parametrization now includes '//tmp/b'. The new test_double_slash_alias_cannot_adopt_itself at tests/test_inventory_recovery_v3_handover.py:122 preserves valid installed records/root/configuration, supplies '/' + installed['root'] as replacement, and requires the canonical-path ValueError. Together these regressions target the original acceptance bug and the handover caller. No additional finding established in this fix-only reread.

Coordinator reports final focused validation: 524 passed, source and production authority unchanged, 14.25 seconds wall; receipt installed-authority-validation/f214ebd30caa. No tests were run by this inspector, and the receipt was not independently audited. Only this report was appended; source, tests, master and production evidence were not edited.

Follow-up SHA-256 identities:

| File | SHA-256 |
| --- | --- |
| tools/inventory_recovery_v3/installed_authority.py | 8a77f7c6abb86990e6f8eb4518d186db1dc0cf9d86e95f92f40df2ae62a9dcc6 |
| tests/test_inventory_recovery_v3_installed_authority.py | f070cc371ef62d1b372def9e3394d96d7bb07554fe5d1b03acc38545e82e8b2b |
| tests/test_inventory_recovery_v3_handover.py | babd48d4908dc2b60fb8826238a100d8c4281d2e8ef0326f677af4a25067918e |

Current disposition: the sole reported P2 alias finding is closed in the inspected offline slice. Full TX3 admission, runtime extension validation and public common ownership integration remain outside this closure.
