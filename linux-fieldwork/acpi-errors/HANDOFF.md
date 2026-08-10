# Linux Fieldwork handoff — ACPI error propagation

Updated: 2026-08-10
State: STRONG CANDIDATE, HUMAN DESIGN REVIEW USEFUL
Branch base: canonical `383773a03d8105e3fa6e2a9364b2a8e8366626b0`
Validated candidate carrier head: `c8424a39bee350238ca5db747d90b3de14dd3ccf`
Current canonical source reviewed through: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Upstream issue: `cloud-hypervisor/cloud-hypervisor#8666`
Internal record: `teamleaderleo/linux-fieldwork#444`

## TL;DR

The candidate gives ACPI table construction a real error boundary and propagates address, mutex, guest-memory, and fw_cfg failures into the VM boot `Result`. Source review narrowed the patch so layout and validated-configuration invariants remain explicit assertions instead of becoming runtime fallback errors.

The final focused matrix is green on the exact reviewed candidate. The remaining decision is whether this error boundary is the right upstream design and whether the deterministic address helper test is sufficient focused unit coverage before preparing a clean production commit.

## Runtime failures propagated

- checked ACPI table-address additions;
- allocator mutex poisoning while constructing the FADT;
- aarch64 interrupt-controller mutex poisoning while reading the VGIC;
- missing fw_cfg at the public helper boundary and fw_cfg mutex poisoning;
- guest-memory writes of the RSDP and table bytes;
- `fw_cfg::add_acpi()` I/O failure.

The final error type is `acpi::Error`. Poisoned-lock errors retain the affected resource name (`allocator`, `interrupt controller`, or `fw_cfg`) because `PoisonError` itself carries no useful source detail. Direct-memory, fw_cfg, and TDX paths all feed one VM error variant: `vm::Error::CreatingAcpiTables`.

`MissingFwCfg` is defensive at the public helper boundary. Valid boot creates fw_cfg before calling `create_acpi_tables_for_fw_cfg()`, but the helper no longer panics if that precondition is violated. This matches nearby upstream practice of propagating failures at an existing caller boundary even when the current call graph normally makes the error unreachable.

## Invariants deliberately retained

- fixed ACPI structure sizes; the candidate moves the two size checks to compile-time `const` assertions, matching existing project practice;
- IORT header and alignment assertions;
- IORT PCI segment `< 256` assertion. `PlatformConfig::validate()` caps `num_pci_segments` at 96 and `DeviceManager::new()` creates IDs from `0..num_pci_segments`;
- aarch64 interrupt-controller presence. VM initialization installs it before boot reaches ACPI creation;
- aarch64 VGIC presence. `Gic::new()` stores `vgic: Some(...)` and `get_vgic()` returns that value;
- serial-device lookup consistency. ACPI checks and indexes the same immutable device-info map.

The complete production panic inventory in `vmm/src/acpi.rs` was reviewed. Each remaining panic is covered by one of these invariant decisions or lies in test-only code.

## Canonical candidate carrier

The carrier now has one candidate representation:

- `linux-fieldwork/acpi-errors/candidate.patch` — reviewed product patch;
- `linux-fieldwork/acpi-errors/run_candidate.py` — verifies exact upstream blob identities, runs `git apply --check`, applies the patch, and formats it;
- `.github/workflows/linux-fieldwork-acpi-errors.yml` — focused evidence gate.

The older generated-source transform was removed. REUSE coverage for the internal Python and patch files was added to `.reuse/dep5`.

Exact guarded upstream blobs:

- `vmm/src/acpi.rs`: `6ac7666ebdc49c67fbc6233c135e8645f7e64e0f`;
- `vmm/src/vm.rs`: `12a9fe0ad7068df7b26082b32de65d6f54b33d04`.

## Final focused evidence

Validated carrier head: `c8424a39bee350238ca5db747d90b3de14dd3ccf`
Focused workflow run: `31346100848`
Candidate job: `93328232200`
Artifact: `9047409416`
Artifact digest: `sha256:ab966495356c334f421050396dee368fbd1b2126e4dbff5b921bb7ce75b69c51`
Generated product patch digest: `sha256:18cbecacd94abc438999ace608cd45b17a9982b96b82af5da7496fad40e6d29d`

All focused gates passed:

- exact source blob verification;
- `git apply --check` and candidate application;
- generated scope exactly `vmm/src/acpi.rs` and `vmm/src/vm.rs`;
- `git diff --check`;
- `cargo fmt --all -- --check`;
- exact unit test `acpi::tests::test_next_table_address` with both a passing-control addition and the overflow error case;
- explicit log proof that the exact test executed successfully;
- `cargo check -p vmm --features kvm`;
- `cargo check -p vmm --features kvm,fw_cfg`;
- `cargo check -p vmm --features kvm,tdx`;
- aarch64 `cargo check -p vmm --features kvm --target aarch64-unknown-linux-gnu` with `gcc-aarch64-linux-gnu` installed;
- retained candidate diff and artifact upload.

The test step uses `set -o pipefail` and requires the exact `... test_next_table_address ... ok` output, preventing either a zero-test filter or `tee` from creating misleading green evidence.

The final retained generated diff was reviewed against the previously green candidate. The only semantic additions in the polish are the conventional `acpi::Error` name, contextual poisoned-lock diagnostics, and the passing control in the address helper test.

## Failure ownership learned during refinement

Earlier red runs were kept separate from product behavior:

- one candidate transform broke the aarch64 cfg boundary;
- an early focused test lacked a hypervisor backend;
- an intermediate aarch64 transform modeled `Gic::get_vgic()` as `Option` even though it returns `Result`;
- the first real aarch64 cross-check lacked `aarch64-linux-gnu-gcc` on the hosted runner;
- one polished carrier run failed before Rust because `candidate.patch` lacked its final newline and `git apply` rejected it as corrupt.

Each owner was repaired independently and the unchanged downstream gate was rerun.

## Broader CI

Final-head normal fork CI: `31346100835`.

At the latest checkpoint, preflight, formatting, REUSE, typos, link checks, shell checks, package consistency, and both stable/1.89.0 RISC-V builds are green. Build and Clippy matrices are progressing with their completed candidate-relevant steps green. `gitlint` and DCO remain red because the internal research branch contains historical exploratory commits that do not satisfy upstream production-commit hygiene; those failures do not describe the generated two-file candidate.

The immediately preceding cleaned carrier also completed broad build/quality surfaces successfully across stable/beta/nightly, x86_64/aarch64, KVM/MSHV, fw_cfg, IGVM, SEV-SNP, fuzz-build, formatting, and Clippy. A future upstream packet should materialize one clean signed production commit instead of reusing the exploratory carrier history.

## Source freshness

Canonical `main` remains `a1fcb9f790616ac615f66de73be540b0b20844b1` at the latest refresh. It is 36 commits ahead of the original investigation base, with `vmm/src/acpi.rs` and `vmm/src/vm.rs` unchanged from the guarded source blobs.

## Human decision

Review the boundary itself:

1. Is `acpi::Error` with one VM-level `CreatingAcpiTables` wrapper the preferred design?
2. Is retaining `MissingFwCfg` as a defensive public-helper error desirable even though valid boot establishes fw_cfg first?
3. Is the exact address helper test plus the compile/Clippy surfaces enough focused coverage, or should a production packet add a deterministic second failure-path fixture?

If accepted, the next repository action is to materialize a clean production commit from `candidate.patch` on current canonical source, run the same gates on that exact commit, and prepare an internal upstream packet. Canonical upstream contact still requires explicit human authorization.

## External-contact state

`false; none occurred`.
