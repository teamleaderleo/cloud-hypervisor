# Proposed upstream contribution — API lifecycle shutdown events

Status: INTERNAL REVIEW PACKET ONLY
Canonical upstream contact: not authorized; none occurred
Intended issue: `cloud-hypervisor/cloud-hypervisor#8046`

## Proposed title

`tests: use shutdown events for API lifecycle gates`

## Proposed commit message

The API shutdown and delete tests currently treat loss of SSH as proof
that guest shutdown completed. sshd can stop while guest and VMM cleanup
is still in progress, but the tests immediately reuse the VM and disk.

Start these VMMs with `--no-shutdown` and an event monitor. Power the
guest off normally, wait for the exact shutdown event, and only then
perform the next API lifecycle transition.

Fixes: #8046

Signed-off-by: leo03164 <leo03164@gmail.com>

## Proposed pull-request description

### Problem

The shared API shutdown/delete wrappers halt the guest and use an
unresponsive SSH service as the synchronization point before reusing the
VMM and disk. SSH disappearance is a service-level observation, not a
completed VM shutdown transition.

Issue #8046 asks these tests to use `--no-shutdown`, normal guest poweroff,
and the event monitor instead.

### Change

For the shared shutdown and delete wrappers:

- launch the VMM with `--no-shutdown`;
- enable an event monitor scoped to the guest temporary directory;
- request `sudo poweroff` from the guest;
- wait for the exact latest `shutdown` event;
- only then boot again or delete/recreate/boot.

The wrappers are shared by HTTP and D-Bus tests, so one source change covers
both API surfaces.

### Why this event is the correct barrier

The guest-exit path invokes `vm_shutdown()` when `--no-shutdown` is active.
`vm_shutdown()` calls `vm.shutdown()` first and emits the `shutdown` event
only after that operation succeeds. The test therefore waits for a
VMM-owned completed transition rather than an early guest notification.

### Testing

Exact candidate binaries and the real integration harness were run under
KVM with the project-verified Jammy image and direct kernel.

Passed selectors:

- `common_parallel::test_api_http_shutdown` — 14.45s;
- `common_parallel::test_api_http_delete` — 14.51s;
- `dbus_api::test_api_dbus_shutdown` — 14.00s;
- `dbus_api::test_api_dbus_delete` — 14.18s.

Each test completed normal guest poweroff, observed the shutdown event, and
successfully performed the immediate next lifecycle transition.

Runtime receipt:

- workflow run/job: `30953976821` / `92176887306`;
- exact diagnostic head: `9cc08f007e785d3c513c4589fa7faa231dceb5cd`;
- artifact: `8915262953`;
- artifact digest:
  `sha256:eed3ebbca87dba9fa11801d12ea69a3cc57fa137f00a33dc4542dbbd9addec3b`.

## Intended source diff

One file only:

`cloud-hypervisor/tests/common/tests_wrappers.rs`

Expected source changes:

- two temporary event-monitor paths;
- two `--no-shutdown` arguments;
- two event-monitor arguments;
- replace `sync`, `shutdown -H`, SSH-unresponsive waits, and the extra API
  shutdown in the shutdown wrapper with normal poweroff plus exact shutdown
  event waits.

No production VMM behavior changes.

## Reviewer questions already considered

### Can the event arrive before shutdown completes?

No. Current VMM ordering emits it after `vm.shutdown()` returns success.

### Can the VMM exit before the API transition?

`--no-shutdown` keeps the process alive and converts guest exit into
`vm_shutdown()` rather than VMM termination. The four runtime tests proved
that immediate boot and delete/create operations succeed afterward.

### Can a stale event make the test pass?

Each wrapper creates a new guest temporary directory and event path. The test
waits for the exact latest event sequence after requesting poweroff.

### Does this affect confidential-VM tests?

The wrappers are also reused by confidential-VM HTTP variants. The change is
semantically appropriate there, but the pull request should mention the shared
surface so existing CVM CI is understood as additional coverage rather than an
unrelated change.

### Why remove the explicit `sync`?

Normal `poweroff` performs the guest shutdown path, including filesystem
shutdown. The old explicit sync existed because `shutdown -H` deliberately
halted without powering off. The real KVM matrix proved disk reuse and second
boot under the normal poweroff path.

## Packaging requirements before any upstream action

- use a branch based on current canonical `main`;
- one signed-off commit;
- one changed source file;
- no `linux-fieldwork/` files;
- no private workflow;
- no diagnostic commit history;
- rerun formatting and the four exact KVM selectors on the clean commit if
  its base or source differs from the runtime-proven candidate.
