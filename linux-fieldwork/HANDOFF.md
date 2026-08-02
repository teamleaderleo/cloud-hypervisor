# Linux Fieldwork handoff — API lifecycle shutdown events

Updated: 2026-08-02
State: PATCH READY, RUNTIME GATE PENDING
Branch: `linux-fieldwork/api-shutdown-events`
Base: fork `main` at `dcea656a722cab1b24c1d7c48fa2b12a7276f04c`
Upstream issue: `cloud-hypervisor/cloud-hypervisor#8046`

## Finding

The shared HTTP/D-Bus API wrapper tests `_test_api_shutdown` and `_test_api_delete` currently run `shutdown -H`, wait until SSH becomes unresponsive, and then perform the next API lifecycle operation.

The originating review correctly identified that loss of SSH only proves that sshd stopped. Other guest shutdown work can still be running. The tests therefore use a service-level symptom as a proxy for a VM lifecycle transition.

Merged PR #8025 added `--no-shutdown`. With that flag, guest ACPI poweroff calls `vm_shutdown()` and emits the VMM `shutdown` event while keeping the VMM process alive. This is the exact mechanism required by issue #8046.

## Candidate contract

For API shutdown/delete lifecycle tests:

1. start the VMM with `--no-shutdown` and an event monitor;
2. boot and validate the guest;
3. request normal guest `poweroff`;
4. wait for an exact latest `shutdown` event;
5. only then boot again or delete/recreate through the selected API.

Because `_test_api_shutdown` and `_test_api_delete` accept `TargetApi`, one source change covers the HTTP and D-Bus test variants.

## Branch contents

- `linux-fieldwork/0001-tests-use-shutdown-events-for-api-lifecycle.patch`
  - adds an event monitor and `--no-shutdown` to both wrappers;
  - replaces `shutdown -H` plus `wait_for_ssh_unresponsive()` with guest `poweroff` plus `wait_for_latest_events_exact()`;
  - leaves the subsequent boot or delete/create/boot assertions intact.

Source identities used:

- `cloud-hypervisor/tests/common/tests_wrappers.rs`: blob `046406d0b1371b0a28f13ba8242e34978def5f89`;
- event helper implementation observed in `cloud-hypervisor/tests/common/utils.rs`;
- `--no-shutdown` implementation and semantics confirmed through merged PR #8025 and current CLI source.

## Evidence

- Issue #8046 is open, unassigned, and has no comments.
- The originating review states that `shutdown -H` does not generate an event and that normal poweroff would ordinarily exit the VMM.
- PR #8025 documents that `--no-shutdown` converts guest-triggered poweroff into `vm_shutdown()` while retaining the VMM process.
- `wait_for_latest_events_exact(timeout, events, event_file)` already exists and is used by current integration tests.
- The retained patch passes `patch --dry-run -p1` against a fixture containing the exact current wrapper bodies.
- Search for pull requests matching issue 8046 and this change returned none.

## Tests not run

The integration tests require the Cloud Hypervisor workload images, KVM/hypervisor access, and the project test harness. Those resources were not present in this execution environment.

The source patch has not been applied to the large tracked Rust file through the connector; it is retained as an apply-ready artifact. This distinction matters: branch code remains current upstream code until the patch is applied in a normal checkout.

## Next technical step

Apply the retained patch in a full checkout, then run the narrow HTTP and D-Bus integration selectors that invoke `_test_api_shutdown` and `_test_api_delete`. At minimum, verify:

- `shutdown` event arrives within 20 seconds;
- VMM process remains alive after guest poweroff;
- boot-after-shutdown succeeds;
- delete/create/boot succeeds;
- event file from the first VM state does not cause a false positive after recreation;
- both HTTP and D-Bus variants pass.

Run formatting before retaining the source commit:

```text
cargo fmt --all -- --check
```

## Risk to check

`wait_for_latest_events_exact()` matches the most recent events. The delete/recreate flow should ensure the first shutdown event cannot satisfy a later lifecycle assertion accidentally. The current candidate has only one shutdown assertion before deletion, so no event-file reset is expected, but the live run must confirm the event order.

## External-contact state

`false; none occurred`. No upstream issue, pull request, comment, review, discussion, or email was created.
