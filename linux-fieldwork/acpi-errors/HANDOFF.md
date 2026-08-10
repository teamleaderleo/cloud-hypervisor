# Linux Fieldwork handoff — ACPI error propagation

Updated: 2026-08-10
State: STRONG CANDIDATE, HUMAN DESIGN REVIEW USEFUL
Branch base: canonical `383773a03d8105e3fa6e2a9364b2a8e8366626b0`
Validated candidate carrier head: `7ed7f9a3c90e8873f88a9b88c0416753272d48c8`
Current canonical source reviewed through: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Upstream issue: `cloud-hypervisor/cloud-hypervisor#8666`
Internal record: `teamleaderleo/linux-fieldwork#444`

## TL;DR

The candidate gives ACPI table construction a real error boundary and propagates address, mutex, guest-memory, and fw_cfg failures into the VM boot `Result`. Source review narrowed the patch so layout and validated-configuration invariants remain explicit assertions instead of becoming runtime fallback errors.

This is a small correctness fix rather than a public API redesign: `vmm::acpi` is a private crate module, and the changed ACPI entry-point signatures are used inside VMM. Canonical issue #8666 remains open with no discussion beyond the request that `create_acpi_tables` and its children propagate errors instead of panicking.

## Runtime failures propagated

- checked ACPI table-address additions;
- allocator mutex poisoning while constructing the FADT;
- aarch64 interrupt-controller mutex poisoning while reading the VGIC;
- missing fw_cfg at the crate-internal helper boundary and fw_cfg mutex poisoning;
- guest-memory writes of the RSDP and table bytes;
- `fw_cfg::add_acpi()` I/O failure.

The final error type is `acpi::Error`. Poisoned-lock errors retain the affected resource name (`allocator`, `interrupt controller`, or `fw_cfg`) because `PoisonError` itself carries no useful source detail. Direct-memory, fw_cfg, and TDX paths all feed one VM error variant: `vm::Error::CreatingAcpiTables`.

`MissingFwCfg` is defensive at the crate-internal helper boundary. Valid boot enables fw_cfg, populates it, and only then calls `create_acpi_tables_for_fw_cfg()`, but the helper no longer panics if that precondition is violated. This is consistent with nearby upstream work that removes `unwrap()` at an existing error boundary even when the current call graph normally makes the error unreachable.

## Invariants deliberately retained

- fixed ACPI structure sizes; the candidate moves the two size checks to compile-time `const` assertions, matching existing project practice;
- IORT header and alignment assertions;
- IORT PCI segment `< 256` assertion. `PlatformConfig::validate()` caps `num_pci_segments` at 96 and `DeviceManager::new()` creates IDs from `0..num_pci_segments`;
- aarch64 interrupt-controller presence. VM initialization installs it before boot reaches ACPI creation;
- aarch64 VGIC presence. `Gic::new()` stores `vgic: Some(...)` and `get_vgic()` returns that value;
- serial-device lookup consistency. ACPI checks and indexes the same immutable device-info map.

The complete production panic inventory in `vmm/src/acpi.rs` was reviewed. Each remaining panic is covered by one of these invariant decisions or lies in test-only code.

## Canonical candidate carrier

The carrier has one product representation:

- `linux-fieldwork/acpi-errors/candidate.patch` — exact reviewed and tested product patch;
- `linux-fieldwork/acpi-errors/run_candidate.py` — verifies exact upstream blob identities, runs `git apply --check`, applies the patch, and verifies rustfmt without mutating the product diff;
- `.github/workflows/linux-fieldwork-acpi-errors.yml` — focused evidence gate.

The older generated-source transform is gone. REUSE coverage for the internal Python and patch files is present.

Exact guarded upstream blobs:

- `vmm/src/acpi.rs`: `6ac7666ebdc49c67fbc6233c135e8645f7e64e0f`;
- `vmm/src/vm.rs`: `12a9fe0ad7068df7b26082b32de65d6f54b33d04`.

## Final focused evidence

Validated carrier head: `7ed7f9a3c90e8873f88a9b88c0416753272d48c8`
Focused workflow run: `31347216657`
Candidate job: `93331259891`
Artifact: `9047745419`
Artifact digest: `sha256:e96e8d0776b2c3c3bafa0c92d36ff23fb64232750d9428ef8617a1bceac153ab`
Stored and generated product patch digest: `sha256:18cbecacd94abc438999ace608cd45b17a9982b96b82af5da7496fad40e6d29d`

All focused gates passed:

- exact source blob verification;
- `git apply --check` and candidate application;
- rustfmt verification without modifying the applied patch;
- generated scope exactly `vmm/src/acpi.rs` and `vmm/src/vm.rs`;
- `git diff --check`;
- exact unit test `acpi::tests::test_next_table_address` with both a passing-control addition and the overflow error case;
- explicit log proof that the exact test executed successfully;
- `cargo check -p vmm --features kvm`;
- `cargo check -p vmm --features kvm,fw_cfg`;
- `cargo check -p vmm --features kvm,tdx`;
- aarch64 `cargo check -p vmm --features kvm --target aarch64-unknown-linux-gnu` with `gcc-aarch64-linux-gnu` installed;
- retained candidate diff and artifact upload.

The newly retained generated patch was compared byte-for-byte with the stored `candidate.patch`: they are identical and share the `18cbec...` SHA-256 digest. Review artifact, applied artifact, and tested artifact are now the same bytes.

The test step uses `set -o pipefail` and requires the exact `... test_next_table_address ... ok` output, preventing either a zero-test filter or `tee` from creating misleading green evidence.

## Failure ownership learned during refinement

Earlier red runs were kept separate from product behavior:

- one candidate transform broke the aarch64 cfg boundary;
- an early focused test lacked a hypervisor backend;
- an intermediate aarch64 transform modeled `Gic::get_vgic()` as `Option` even though it returns `Result`;
- the first real aarch64 cross-check lacked `aarch64-linux-gnu-gcc` on the hosted runner;
- one polished carrier run failed before Rust because `candidate.patch` lacked its final newline and `git apply` rejected it as corrupt;
- one carrier-cleanup attempt manually reconstructed a formatted patch from a partial artifact view and truncated it; the next revision restored the literal retained artifact bytes and the full focused matrix passed.

Each owner was repaired independently before downstream evidence was accepted.

## Broader evidence

Normal fork CI on the exploratory carrier is useful only as a secondary surface because gitlint/DCO describe research history rather than the generated product patch, and later carrier-only pushes can supersede long matrix jobs. Completed candidate-relevant build, formatting, REUSE, RISC-V, x86_64/aarch64 and Clippy steps across the recent carrier runs have been green; the focused exact-patch run above is the durable candidate receipt.

A future contribution branch can be rebuilt however convenient internally, but the eventual human-owned squashed/signed commit should be validated as its own immutable SHA before upstream submission.

## Source freshness and scope

Canonical `main` remains `a1fcb9f790616ac615f66de73be540b0b20844b1` at the latest refresh. It is 36 commits ahead of the original investigation base, with `vmm/src/acpi.rs` and `vmm/src/vm.rs` unchanged from the guarded source blobs.

The candidate product diff is two files: 98 insertions and 53 deletions (`vmm/src/acpi.rs`: +83/-41; `vmm/src/vm.rs`: +15/-12). Most of that is mechanical error plumbing and signature propagation rather than new behavior.

## Current review recommendation

- keep `acpi::Error` with one VM-level `CreatingAcpiTables` wrapper;
- keep defensive `MissingFwCfg`: the normal boot call graph establishes fw_cfg, but replacing the existing `expect()` is directly aligned with issue #8666 and does not alter an external API;
- keep the current address-helper unit test unless a natural second production failure fixture appears; a synthetic mutex-poison test would primarily test `std::sync::Mutex` rather than ACPI logic.

No further product-code change is currently justified by the source review. Further work should either challenge one of these boundary decisions or prepare additional evidence, rather than churn the patch for its own sake.

## External-contact state

`false; none occurred`.
