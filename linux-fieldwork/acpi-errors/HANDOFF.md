# Linux Fieldwork handoff — ACPI error propagation

Updated: 2026-08-10
State: STRONG CANDIDATE, CURRENT BOUNDARY SATURATED
Branch base: canonical `383773a03d8105e3fa6e2a9364b2a8e8366626b0`
Validated candidate carrier head: `0a2f55acbd23b7f44899a69132a4236ef9240027`
Current canonical source reviewed through: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Upstream issue: `cloud-hypervisor/cloud-hypervisor#8666`
Internal record: `teamleaderleo/linux-fieldwork#444`

## TL;DR

The candidate gives ACPI table construction a real error boundary and propagates address, mutex, guest-memory, and fw_cfg failures into the VM boot `Result`. Review keeps layout and validated-configuration invariants explicit instead of turning every assertion or unwrap into runtime fallback.

The exact stored product patch now passes nightly rustfmt, focused Clippy, its deterministic address-overflow unit test, x86_64 KVM and MSHV compilation, fw_cfg and TDX compilation, and AArch64 KVM and MSHV cross-compilation. The focused workflow also generates the product diff and requires it to be byte-identical to the stored `candidate.patch`; both exact representations have SHA-256 `4d65cdbcb01a72eb09ae3b905a5d4e46b8e140c4cec8d3e1f00380ac5476628d`.

This remains a small correctness fix rather than a public API redesign: `vmm::acpi` is a private crate module, and the changed ACPI entry-point signatures are used inside VMM. Canonical issue #8666 remains open with no overlapping fix found in the latest review pass.

## Runtime failures propagated

- checked ACPI table-address additions;
- allocator mutex poisoning while constructing the FADT;
- aarch64 interrupt-controller mutex poisoning while reading the VGIC;
- missing fw_cfg at the crate-internal helper boundary and fw_cfg mutex poisoning;
- guest-memory writes of the RSDP and table bytes;
- `fw_cfg::add_acpi()` I/O failure.

The error type is `acpi::Error`. Poisoned-lock errors retain the affected resource name (`allocator`, `interrupt controller`, or `fw_cfg`) because `PoisonError` itself carries no useful source detail. Direct-memory, fw_cfg, and TDX paths all feed one VM error variant: `vm::Error::CreatingAcpiTables`.

`MissingFwCfg` is defensive at the crate-internal helper boundary. Valid boot enables and populates fw_cfg before calling `create_acpi_tables_for_fw_cfg()`, while the helper now returns an ordinary ACPI error if that precondition is violated.

The final Display strings follow the current project convention for concise sentence-style errors:

- `ACPI table delivery requires fw_cfg`;
- `Failed to write ACPI data to guest memory`;
- `Failed to add ACPI data to fw_cfg`.

## Invariants deliberately retained

- fixed ACPI structure sizes; the candidate moves the two size checks to compile-time `const` assertions, matching existing project practice;
- IORT header and alignment assertions;
- IORT PCI segment `< 256` assertion. `PlatformConfig::validate()` caps `num_pci_segments` at 96 and `DeviceManager::new()` creates IDs from `0..num_pci_segments`;
- aarch64 interrupt-controller presence. VM initialization installs it before boot reaches ACPI creation;
- aarch64 VGIC presence. Current `Gic::new()` stores `vgic: Some(...)`, and `get_vgic()` returns that stored value;
- serial-device lookup consistency. ACPI checks and indexes the same immutable device-info map;
- fw_cfg XSDT/FACP pointer bookkeeping. `create_acpi_tables_internal()` always emits FACP and MADT before returning, so the pointer list is non-empty; its offsets are generated from the same checked address chain used to build the tables.

The complete production panic inventory in `vmm/src/acpi.rs` was reviewed. Each remaining panic is covered by one of these invariant decisions or lies in test-only code. The separate AArch64 cache-topology runtime panic family remains a successor question under canonical issue #8097 and Linux Fieldwork #499; it has a natural future route through this ACPI `Result` boundary.

## Canonical candidate carrier

The carrier has one product representation:

- `linux-fieldwork/acpi-errors/candidate.patch` — exact reviewed and tested product patch;
- `linux-fieldwork/acpi-errors/run_candidate.py` — verifies exact upstream blob identities, runs `git apply --check`, applies the patch, and verifies the actual project nightly rustfmt rules without mutating the product diff;
- `.github/workflows/linux-fieldwork-acpi-errors.yml` — focused evidence gate.

Exact guarded upstream blobs:

- `vmm/src/acpi.rs`: `6ac7666ebdc49c67fbc6233c135e8645f7e64e0f`;
- `vmm/src/vm.rs`: `12a9fe0ad7068df7b26082b32de65d6f54b33d04`.

The guards are intentionally strict. Adjacent upstream work can continue freely; if either product source changes, the runner stops before applying the candidate and forces an explicit source review/restack.

## Final focused evidence

Validated carrier head: `0a2f55acbd23b7f44899a69132a4236ef9240027`
Focused workflow run: `31349013458`
Candidate job: `93336246241`
Artifact: `9048345416`
Artifact digest: `sha256:5335c66d23be38b9a988335061918adf8f7f44b4b4b564bf22a9c736d350e210`
Stored/generated product patch digest: `sha256:4d65cdbcb01a72eb09ae3b905a5d4e46b8e140c4cec8d3e1f00380ac5476628d`

All focused gates passed:

- install nightly rustfmt and use the repository's actual nightly-only import-grouping rules;
- exact source blob verification;
- `git apply --check` and candidate application;
- generated scope exactly `vmm/src/acpi.rs` and `vmm/src/vm.rs`;
- `git diff --check`;
- nightly `cargo fmt --all -- --check` both inside the exact-source runner and as an explicit workflow gate;
- exact unit test `acpi::tests::test_next_table_address`, with a passing-control addition and overflow error case plus explicit log proof that the named test executed;
- focused `cargo clippy -p vmm --all-targets --features kvm,fw_cfg,tdx -- -D warnings`;
- `cargo check -p vmm --features kvm`;
- `cargo check -p vmm --features mshv`;
- `cargo check -p vmm --features kvm,fw_cfg`;
- `cargo check -p vmm --features kvm,tdx`;
- AArch64 `cargo check -p vmm --features kvm --target aarch64-unknown-linux-gnu`;
- AArch64 `cargo check -p vmm --features mshv --target aarch64-unknown-linux-gnu`;
- retained generated candidate diff;
- automatic `cmp` proving the retained generated diff is byte-identical to stored `candidate.patch`;
- SHA-256 receipt for both exact patch paths and artifact upload.

The artifact's `candidate-sha256.txt` records the same `4d65c...` digest for the stored candidate and `/tmp/acpi-error-propagation.patch`. Review artifact, applied artifact, tested artifact, and retained generated artifact are therefore the same bytes.

Product scope remains two files: 98 insertions and 53 deletions (`vmm/src/acpi.rs`: +83/-41; `vmm/src/vm.rs`: +15/-12). Most of the diff is mechanical `Result` and error propagation.

## Failure ownership learned during refinement

Earlier red runs were kept separate from product behavior:

- one candidate transform broke the aarch64 cfg boundary;
- an early focused test lacked a hypervisor backend;
- an intermediate aarch64 transform modeled `Gic::get_vgic()` as `Option` even though it returns `Result`;
- the first real aarch64 cross-check lacked `aarch64-linux-gnu-gcc` on the hosted runner;
- one polished carrier run failed before Rust because `candidate.patch` lacked its final newline and `git apply` rejected it as corrupt;
- one carrier-cleanup attempt manually reconstructed a formatted patch from a partial artifact view and truncated it; the next revision restored literal retained artifact bytes;
- adding exact-patch Clippy found a real candidate-owned `clippy::absolute_paths` violation in the initial `std::result::Result` alias; importing `result` fixed it in project style;
- switching the evidence gate from stable rustfmt to nightly exposed that stable rustfmt had been ignoring the repository's nightly-only `group_imports` and `imports_granularity` settings; the candidate was reformatted to exact nightly output and the runner/workflow now use nightly explicitly;
- after semantic repairs, the new `cmp` gate intentionally rejected stale diff metadata until `candidate.patch` was rematerialized from the generated artifact; the final run proves automatic byte identity.

Each owner was repaired independently before downstream evidence was accepted.

## Broader evidence and adjacent review

Normal fork CI remains secondary carrier evidence because the research branch stores the product change as `candidate.patch`; ordinary carrier builds and Clippy do not apply those product bytes. The focused workflow is the authoritative product receipt because it applies the exact patch before every product gate.

The adjacent review sampled the direct-memory, fw_cfg, TDX, x86_64, AArch64, KVM, MSHV, GIC/VGIC, pointer-bookkeeping, and cache/PPTT boundaries. Active AArch64 GIC work upstream changes MPIDR handling but currently preserves the GIC/VGIC presence model; any future canonical change to `vmm/src/vm.rs` or `vmm/src/acpi.rs` will trip the exact blob guard and reopen source freshness explicitly.

## Source freshness and reopen triggers

Canonical `main` remains `a1fcb9f790616ac615f66de73be540b0b20844b1` at the latest refresh, with the guarded ACPI and VM blobs unchanged from the exact source used by the candidate.

Reopen the current decision if one of these occurs:

- either guarded product blob changes on canonical `main`;
- a canonical fix for #8666 appears;
- a remaining ACPI panic is shown to depend on runtime/host input inside the current call paths rather than a validated or programming invariant;
- a natural deterministic fixture exposes a second production failure path worth testing;
- a supported backend/architecture combination demonstrates a compile or behavior difference outside the current matrix.

AArch64 cache discovery under #8097 changes the failure source and caller chain enough to remain a distinct successor investigation instead of widening this candidate silently.

## Current review recommendation

- keep `acpi::Error` with one VM-level `CreatingAcpiTables` wrapper;
- keep defensive `MissingFwCfg` at the crate-internal helper boundary;
- keep the current address-helper unit test unless a natural second production failure fixture appears;
- keep the remaining validated/programming invariants explicit;
- treat the exact focused workflow as the candidate evidence source, with stored/generated patch equality enforced automatically.

Inside the current source generation and declared backend/architecture boundary, further product churn needs a concrete counterexample or new runtime failure. Adjacent successor questions can proceed independently.

## External-contact state

`false; none occurred`.
