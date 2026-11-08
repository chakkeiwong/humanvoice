# Qualification namespace repair and offline host request

The former bubblewrap user namespace could read the bound server PID and start
time, but `/proc/18780/exe` returned `EACCES`. Native session verification therefore
refused execution. The server had not exited. The failed observation and prior
sources are retained under `retained/namespace-attempt02`.

Use a systemd mount namespace with `User=ubuntu`, `Group=ubuntu`,
`PrivateUsers=no`, `ProtectSystem=strict`, `ProtectHome=tmpfs`,
`NoNewPrivileges=yes` and an empty capability bounding set. Keep all 29 original
archive paths bound read-only. Writable paths are exactly the qualification
directory, the existing account and grant parent directories, and `docs/plans`
for atomic master status refresh. The native inference command still selects
`on-request`, reviewer `user`, and its read-only sandbox.

The fixed offline host action is:

```text
/tmp/humanvoice-release-env-20261029/bin/python /home/ubuntu/workspace/humanvoice/.localresources/session-qualification-20261107/offline_host.py check-system
```

This action reuses the observed native migration and three-profile protocol
passes only while their exact source hashes, artifacts and cleanup still match.
It requests elevation once, through `pkexec`, for the fixed `system_probe.py`
helper. The helper creates three transient system services with unique names,
one each for environment validation, synthetic local client capture, and killed
child exit propagation. Each service runs as ubuntu, has `PrivateNetwork=yes`,
a 75-second runtime limit, and cleanup of its entire service process group.
Only the synthetic client probe overlays the normal credential file with a
read-only dummy file. All output is returned to the user process for retention.
The helper cannot select an arbitrary command or an input file outside its fixed
scratch path. No service is enabled at boot.

The November 7 mount-table investigation found Ubuntu's packaged
`UBUNTU-Revert-namespace-be-more-careful-when-handling-namespacin.patch`.
It makes `apply_mount_namespace` return success after `EACCES` or `EPERM`, even
when the requested namespace is only partly built. The retained process view
contains original FUSE archive mounts and partly constructed writable mounts,
but lacks the requested read-only protections. Adding explicit `ReadOnlyPaths`
or `RootDirectory=/` did not resolve the setup error. All probes refused that
view and their services were cleaned up.

The repaired builder uses `ProtectHome=tmpfs` to hide inherited home and desktop
FUSE mounts. It binds the workspace, client home, installed client tree and
Python tree read-only with `norbind`, then applies the 29 existing SSD archive
substitutions. All four existing write exceptions remain exact. The mount
changes exist only inside the transient service; host archive mounts remain
intact. Runtime checks still require the actual read-only workspace and client
home, every writable output directory, all 29 original-path SSD identities and
the host user namespace. Component tests exercise silent setup failure,
writable credentials/archives, wrong archive identity and missing write roots.
The actual environment, local protocol and killed-child checks must all pass
before live qualification can be proposed. This is a repair within the approved
three-probe offline scope; it adds no privilege, writable root or remote call.

The repaired mount view passed its actual permission checks. The next isolated
trace showed the installed client opening `state_5.sqlite`, `logs_2.sqlite`,
other runtime databases and `installation_id` with write flags, even for a
configuration read. Use its `CODEX_SQLITE_HOME` setting to place the databases in
`scratch/client-state/sqlite`. Map a private copy of `installation_id` and a
private `tmp` directory from that same scratch tree onto their client-home
paths. These are aliases to the already authorized output directory; the real
host client files remain untouched. The real `auth.json` and `config.toml`,
the client-home parent and all other client files remain read-only. Runtime
checks verify the database path, both alias identities and write flags, and
read-only credentials/configuration. Symlink substitution is rejected during
preparation. The affected component suite now passes 74 cases with 16 workers.
Actual isolated configuration and synthetic inference validation is in progress.

Validation: 181 migration/host component tests and 69 qualification/campaign
tests pass; Ruff passes. Native migration integration passed in 139.96 seconds.
All three isolated client profiles passed. The 69-test suite covers system
mount properties, namespace refusal, exact probe membership, preservation of
native/protocol evidence, service timeout cleanup, crash recovery, semantic
nonpass, authority drift and additive budget idempotence. Actual system namespace
validation is the remaining privileged offline check.

This request authorizes no provider calls, call extension or production start.
The later live request must explicitly approve the proposed 235-call addition
and the bounded qualification system service. Existing time and token authority
remain unchanged. The old `check` action cannot start these system services.

Current update: runtime write errors are resolved, but startup still times out.
The 94-test authentication/session repair and pending real validation supersede
the old per-attempt pkexec description above. See OFFLINE_SESSION_REVIEW.md.

Final observed validation: the third batch passed environment/configuration,
synthetic response capture and exact SIGKILL status. All nine services from three
batches cleaned up; one authentication was reused, and close-system explicitly
closed the helper (clean exit). The suite passes 98 tests. Native/private index
snapshot and the pinned local archive receipt fixed the two remaining startup
issues without changing service scope. Live qualification review is prepared,
with separate budget/launch approval still required.
