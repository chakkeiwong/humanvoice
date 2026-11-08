# Current-client qualification and ZLB campaign checkpoint

Qualification completed on November 8 at 04:16:45 Asia/Shanghai. All 212
provider calls completed, all 212 automatic evaluation checks passed, usage
was settled once and no allocations remain unresolved. The supervisor and
worker exited successfully with complete process cleanup. The selected client
and Astra/xhigh profile now have fresh regression evidence.

The recent failures were implementation and integration defects:

| Failure | Cause and repair |
| --- | --- |
| Repeated administrator password prompts | Each offline batch started a new `pkexec` helper. One authenticated helper now accepts up to eight fixed batches within an hour; actual preflight and conditional restart share one authenticated action. Three batches were verified under one authentication. |
| Client startup stalled | The isolated service needed private writable client runtime paths, and a new empty SQLite index waited for a backfill of read-only desktop history. A consistent SQLite online backup preserves the completed native index. |
| Archive evidence unavailable | Systemd's isolated home view hid the original receipt, and root could not traverse user FUSE mounts. The service uses verified SSD mappings and an exact-byte receipt copy, including inside spawned verification workers. |
| Worker pool could not start | The service's private `/dev/shm` was not writable by ubuntu. Its tmpfs now uses mode `1777`; the actual service preflight checks multiprocessing lock creation. |
| Budget replay rejected an older response | The additive grant reader copied its globals before historical dispatch was installed. The adapter now installs the native verifier for each sealed plan before copying the reader. A separate forwarding function prevents recursive alias replacement. |
| Next-phase source check rejected draft edits | The original campaign draft was part of the qualification's frozen source manifest. Those bytes were restored; all subsequent campaign changes live in a separate successor directory. |

The shared-memory and grant repairs pass 29 affected regression tests and the
actual systemd preflight. The prospective campaign continuation passes 17
tests. Ruff passes on the selected migration, qualification and campaign
sources. Original qualification source checksums still match the approved
manifest. Failed attempts and complete native evidence remain at their original
local paths; the accompanying JSON records checksums and compact results.

Here, a campaign means the resumable ZLB inventory computation: extract the
document's concepts, verify that the inventory covers the source, and verify
that the source's content can be reconstructed from it. Successful earlier
responses are retained. The native recovery controller handles transport
failures, bounded retries, oversized-request splits and permitted model
fallbacks while preserving cumulative call/token usage.

The prepared policy has 439 remaining normal requests and up to 96 recovery
calls: 32 diagnostics, 32 retries and 32 split allowances. The maximum planned
535 calls fits within the 599 calls remaining after qualification. These are
budget bounds, not a prediction that every allowance will be used. Offline
verification uses at most 16 workers; the retained provider execution policy is
sequential.

Current phase: verified migration activation has been published and offline
campaign preparation is running. Native ownership, historical settlement and
source migration checks have completed. This phase makes no provider calls.
Configuration derivation follows preparation; affected release checks and
exact host admission follow configuration. Inventory completion then feeds the
downstream rewriting, assembly and document checks. Full ZLB output and its
final human acceptance remain pending.

Both master programs refresh at native phase boundaries and on stops. The
renewed execution deadline remains November 9 at 01:29:40 Asia/Shanghai.
This commit checkpoints the migration/recovery sources, regression tests and
current program state; it does not replace the full retained local evidence
bundle or claim a completed deployment.
