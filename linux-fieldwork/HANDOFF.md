# Linux Fieldwork handoff — API lifecycle shutdown events

Updated: 2026-08-05
State: RUNTIME-PROVEN, CLEAN CONTRIBUTION PACKAGING IN PROGRESS
Diagnostic branch: `linux-fieldwork/api-shutdown-events`
Runtime-proven head: `9cc08f007e785d3c513c4589fa7faa231dceb5cd`
Current canonical snapshot: `ae04fa80b2e0e52b7a9f4b3fd4239698df586673`
Clean candidate branch: `linux-fieldwork/api-shutdown-events-clean`
Internal diagnostic PR: `teamleaderleo/cloud-hypervisor#1`
Upstream issue: `cloud-hypervisor/cloud-hypervisor#8046`

## Finding

The shared HTTP/D-Bus API wrapper tests `_test_api_shutdown` and `_test_api_delete` used loss of SSH as proof that guest shutdown completed before immediately reusing the VMM and disk.

Loss of SSH only proves that sshd stopped. It is not a VMM-owned shutdown-completion barrier.

Merged `--no-shutdown` support provides the mechanism requested by issue #8046: normal guest poweroff invokes `vm_shutdown()`, emits the VMM `shutdown` event after `vm.shutdown()` succeeds, and leaves the VMM process alive.

## Candidate contract

For both API shutdown/delete wrappers:

1. start the VMM with `--no-shutdown` and an event monitor;
2. create, boot, and validate the guest;
3. request normal guest `poweroff`;
4. wait for the exact latest `shutdown` event;
5. only then boot again or delete/recreate through the selected API;
6. retain the existing second-boot validation.

The shared wrappers cover both HTTP and D-Bus variants.

## Runtime proof

Workflow run: `30953976821`
Runtime job: `92176887306`
Exact diagnostic head: `9cc08f007e785d3c513c4589fa7faa231dceb5cd`
Result: success

The job:

- applied the retained patch with zero fuzz;
- compiled exact candidate release binaries and the real integration harness;
- downloaded the project-verified Jammy QCOW2 and direct kernel;
- converted the QCOW2 to the raw filename required by regular x86 tests;
- verified raw SHA-1 `c1dfbe7abde400e675844568dbe9d3914222f6de`;
- ran the four affected tests serially under root-accessible KVM and TUN.

Passed selectors:

- `common_parallel::test_api_http_shutdown` — 14.45s;
- `common_parallel::test_api_http_delete` — 14.51s;
- `dbus_api::test_api_dbus_shutdown` — 14.00s;
- `dbus_api::test_api_dbus_delete` — 14.18s.

Each test launched with `--no-shutdown` and an event monitor, completed normal guest poweroff, crossed the shutdown-event barrier, and completed the next boot or delete/create/boot transition.

Runtime artifact:

- ID: `8915262953`;
- digest: `sha256:eed3ebbca87dba9fa11801d12ea69a3cc57fa137f00a33dc4542dbbd9addec3b`;
- four per-selector logs;
- expires `2026-11-02T21:49:55Z`.

## Review and overlap state

As of 2026-08-05:

- internal submitted reviews: 0;
- internal inline review threads: 0;
- upstream issue #8046 remains open, unassigned, and has zero comments;
- the issue was created and last updated on 2026-04-16;
- no matching upstream pull request or commit was found;
- canonical wrapper source still uses the SSH-unresponsive gate.

## Packaging boundary

Do not submit the diagnostic branch. It contains Linux Fieldwork workflow, retained patch, and handoff files.

The contribution should be one signed-off source commit based on current canonical commit `ae04fa80b2e0e52b7a9f4b3fd4239698df586673`, changing only:

`cloud-hypervisor/tests/common/tests_wrappers.rs`

Suggested commit title:

`tests: use shutdown events for API lifecycle gates`

Suggested trailer:

`Fixes: #8046`

## External-contact state

`false; none occurred`. No canonical upstream issue comment, pull request, review, reaction, email, or other interaction was created.
