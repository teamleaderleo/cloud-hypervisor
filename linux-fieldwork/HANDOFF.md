# Linux Fieldwork handoff — API lifecycle shutdown events

Updated: 2026-08-03
State: COMPILE-READY, KVM RUNTIME GATE PENDING
Branch: `linux-fieldwork/api-shutdown-events`
Current branch head: `e23378cfd564abc1ebf67a92107126582a9e45c3`
Fork base: `main` at `dcea656a722cab1b24c1d7c48fa2b12a7276f04c`
Internal review carrier: `teamleaderleo/cloud-hypervisor#1`
Upstream issue: `cloud-hypervisor/cloud-hypervisor#8046`

## Finding

The shared HTTP/D-Bus API wrapper tests `_test_api_shutdown` and `_test_api_delete` currently run `shutdown -H`, wait until SSH becomes unresponsive, and then perform the next lifecycle operation.

Loss of SSH proves that sshd stopped, not that guest shutdown reached the VMM-owned terminal state. These tests reuse the VMM and disk immediately, so a service-level proxy can allow a premature boot or delete/recreate transition.

Merged `--no-shutdown` support supplies the stronger mechanism requested by issue #8046: normal guest poweroff invokes `vm_shutdown()`, emits the VMM `shutdown` event, and leaves the VMM process alive.

## Candidate contract

For both API shutdown/delete wrappers:

1. start the VMM with `--no-shutdown` and an event monitor;
2. create, boot, and validate the guest;
3. request normal guest `poweroff`;
4. wait for an exact latest `shutdown` event;
5. only then boot again or delete/recreate through the selected API;
6. retain the existing second-boot validation.

Because the wrappers accept `TargetApi`, the same source correction covers HTTP and D-Bus variants.

## Branch contents

- `linux-fieldwork/0001-tests-use-shutdown-events-for-api-lifecycle.patch` — exact current-source patch;
- `.github/workflows/linux-fieldwork-api-shutdown.yml` — focused patch, contract, formatting, and compile gate;
- this handoff.

Source identities:

- `cloud-hypervisor/tests/common/tests_wrappers.rs`: blob `046406d0b1371b0a28f13ba8242e34978def5f89`;
- event helpers observed in current `cloud-hypervisor/tests/common/utils.rs`;
- `--no-shutdown` behavior confirmed in current source and merged PR #8025.

## Executed exact-source gate

Focused workflow:

- run: `30837304076`;
- job: `91765518101`;
- exact branch head: `e23378cfd564abc1ebf67a92107126582a9e45c3`;
- result: success.

Passed steps:

- apply the retained patch to the exact current wrapper source;
- verify two `--no-shutdown` uses and two event-monitor arguments;
- verify normal guest `poweroff` and exact shutdown-event waits;
- verify the target wrapper slice no longer uses SSH-unresponsive polling;
- `cargo fmt --all -- --check`;
- `cargo check -p cloud-hypervisor --tests --features dbus_api`, compiling the shared HTTP and D-Bus integration-test surface.

## Review-found carrier defects

Earlier focused attempts failed before product compilation and found two patch-packaging defects:

1. a final hunk count/location derived from a reduced fixture rather than the real full-file source;
2. an `index ...00000000` line that falsely declared the modified source file as deleted.

Both are corrected. The successful run above proves the current carrier applies to the exact source and compiles.

## First incomplete step

Run the narrow HTTP and D-Bus integration selectors with KVM and the project workload images. Required observations:

- the VMM remains alive after guest poweroff under `--no-shutdown`;
- the shutdown event arrives within the existing 20-second budget;
- boot-after-shutdown succeeds;
- delete/create/boot succeeds;
- the event file cannot produce a stale false positive;
- cloud-init and OS disk state survive immediate rerun;
- HTTP and D-Bus variants both pass.

Do not claim runtime correctness from compilation alone.

## Risk boundary

`wait_for_latest_events_exact()` matches the most recent event suffix. The current candidate makes one shutdown assertion before each next transition, so no event reset appears necessary, but live execution must verify that the event is emitted only after sufficient VM/device shutdown for disk reuse.

## External-contact state

`false; none occurred`. No canonical upstream issue comment, pull request, review, reaction, email, or other interaction was created.
