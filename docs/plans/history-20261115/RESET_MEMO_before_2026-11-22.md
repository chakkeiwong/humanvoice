# Start here after the November 14 VS Code crashes

Read [the complete November 14 reset memo](docs/RESET_MEMO_2026-11-14.md).
It supersedes earlier reboot/reset instructions and the stale running-state
checkpoint in the masters.

At 15:34 Shanghai on November 14, ZLB is **stopped at a consumer receipt-profile
validation failure**. All five latest writer answers are saved: 115 manuscript
bank entries, 144/177 calls allocated, 33 left. Execution authorization lasts
through November 20, 17:03:49 Shanghai. Final ZLB acceptance is pending.

Start a fresh conversation, preserve the old rollout/evidence, and read the memo
before launching anything. The launcher still binds the old conversation; a
tested explicit session transition is required alongside the replay repair.

Suggested prompt:

> Read `/home/ubuntu/workspace/humanvoice/RESET_MEMO.md` and its full linked memo.
> Recover the existing ZLB state, implement and test the control-session
> transition and consumer receipt-profile repair, review the plan, refresh the
> masters, and continue within existing authorization. Preserve paid answers,
> accounting and historical bindings. Keep tool output bounded.

