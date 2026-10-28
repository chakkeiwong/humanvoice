# Candidate boundary review — 28 October 2026

Coordinator review only; no independent closure or deployment claim.

The core prevents lost pending commands through a single database transaction,
compares both expected sequence and head, and recognizes exact old retries
without clearing a later pending event. Real process-death tests cover committed
and uncommitted prepare/commit states. Read transport authenticates a root peer
and a fresh challenge through the connected Unix stream. Responses cannot be
replayed with an old nonce; framing, length and elapsed-I/O bounds are enforced.
The public read handler cannot call any witness mutation. The service checks
protected paths and limits workers; malformed clients close only their request.

The following remain implementation requirements, not closed findings:

1. The host writer must authenticate exact approved actions and validate their
   root/contract/control semantics. The current Witness stores opaque JSON
   commands; it deliberately does not infer user approval or valid stop/resume
   semantics. Only trusted host code may call prepare or commit.
2. Witness-first workspace publication and recovery must be implemented. A
   pending witness veto must survive a crash before any local intent, and
   committing the witness must require exact durable projections. The current
   low-level commit method alone does not establish that condition.
3. RuntimeLeaf must compare two fresh authenticated witness observations around
   local evidence reads and pass the exact stop_authority evidence contract.
   The candidate snapshot API is not itself permission to dispatch.
4. Protected initialization, crash recovery after partial initialization,
   stale listener recovery and root-owned immutable dependency installation
   require fixed reviewed host actions. Existing/partial stores are never
   silently reinitialized. Offline tests cannot prove the live root boundary.
5. Full-history snapshots and database quick_check/replay are bounded by frame
   size but still grow with history. Measure this in TX7 and implement a pinned
   incremental/checkpoint protocol before declaring long-document readiness.
6. The service must surface operational storage/protection failures to the
   supervisor with durable diagnostics. It currently closes the read request
   and vetoes the client; no complete supervisor status integration exists.
7. Add complete application publication crash cuts, actual independent host
   permissions, storage/fsync failure injection and the public factory matrix
   before promotion into the source-bound release.

These constraints explain why 73 passing offline tests are component evidence,
not full TX3b closure. The implementation is retained for continuation on SSD;
production remains stopped with 166 retained and 439 unfinished requests.
