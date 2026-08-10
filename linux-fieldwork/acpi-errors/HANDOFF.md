# Linux Fieldwork handoff — ACPI error propagation

Updated: 2026-08-10
State: FOCUSED GATES GREEN, CLEANUP AND BROADER REVIEW REMAIN
Branch base: canonical `383773a03d8105e3fa6e2a9364b2a8e8366626b0`
Candidate semantic head: `fd25b6848a7ebe676c86985533954e623db4b31e`
Validated carrier head: `df48ecb3f7c0c23746ecbdf7efc8fbdc384147c0`
Current canonical source reviewed through: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Upstream issue: `cloud-hypervisor/cloud-hypervisor#8666`
Internal record: `teamleaderleo/linux-fieldwork#444`

## Finding

The ACPI creation pipeline is non-fallible at its core even though it performs fallible address arithmetic, mutex acquisition and guest-memory or fw_cfg I/O.

Current upstream signatures remain:

- `create_acpi_tables_internal(...) -> (Rsdp, Vec<u8>, Vec<u64>)`;
- `create_acpi_tables(...) -> GuestAddress`;
- `create_acpi_tables_tdx(...) -> Vec<Sdt>`;
- `create_acpi_tables_for_fw_cfg(...) -> Result<(), vm::Error>`.

The candidate introduces an ACPI-specific error boundary and carries actual construction failures through direct-memory, fw_cfg and TDX paths into `vm::Error::CreatingAcpiTables`.

## Refined panic ownership map

Propagate as runtime construction failures:

- checked ACPI table-address additions;
- allocator mutex poisoning while constructing the FADT;
- aarch64 interrupt-controller mutex poisoning while reading the VGIC;
- fw_cfg absence at the helper boundary and fw_cfg mutex poisoning;
- guest-memory writes of the RSDP and table bytes;
- `fw_cfg::add_acpi()` I/O failure.

Keep as programmer or validated-configuration invariants:

- fixed ACPI structure sizes; the candidate moves the two fixed-size checks to compile-time assertions;
- IORT header and alignment assertions;
- IORT PCI segment `< 256` assertion. `PlatformConfig::validate()` caps `num_pci_segments` at 96 and `DeviceManager::new()` creates IDs from `0..num_pci_segments`, so a valid VM cannot reach IORT with a segment ID >= 256;
- aarch64 interrupt-controller presence. VM initialization creates and installs the controller before boot reaches ACPI creation;
- aarch64 VGIC presence. `Gic::new()` always stores `vgic: Some(...)` and `get_vgic()` currently returns that value;
- serial-device lookup consistency. ACPI tests the same immutable device-info map before indexing the serial entry, so inconsistency remains an explicit programmer error instead of silently becoming the serial-off fallback.

## Candidate contract

- introduce one ACPI-specific error type for actual construction failures;
- make fallible table helpers and `create_acpi_tables_internal` return `Result`;
- centralize checked table-address advancement;
- propagate allocator/GIC/fw_cfg mutex poisoning;
- propagate guest-memory and fw_cfg I/O failures;
- make direct, fw_cfg and TDX entry points return `Result` where their children can fail;
- change the VM wrapper to `Result<Option<GuestAddress>, vm::Error>` and propagate failures at boot call sites;
- use one VM error variant for ACPI creation across delivery modes;
- retain programmer/layout assertions instead of converting them into runtime fallback errors;
- add deterministic unit coverage for address overflow.

## Repair history

The first focused CI attempt exposed separate candidate and harness failures. The generated aarch64 VGIC rewrite broke cfg scoping, and the focused test originally lacked a hypervisor backend. Source review then found that `Gic::get_vgic()` returns `Result<Arc<Mutex<dyn Vgic>>>`, while an intermediate candidate treated it as `Option`.

Those candidate transforms were repaired and narrowed. A later aarch64 cross-check stopped before Cloud Hypervisor source compilation because the hosted runner lacked `aarch64-linux-gnu-gcc`; installing `gcc-aarch64-linux-gnu` repaired that harness boundary without changing candidate semantics.

## Focused evidence

Focused workflow run: `31344505710`
Candidate job: `93323825124`
Validated carrier head: `df48ecb3f7c0c23746ecbdf7efc8fbdc384147c0`

All focused gates passed:

- exact-source candidate application;
- exact changed-file scope: only `vmm/src/acpi.rs` and `vmm/src/vm.rs`;
- `git diff --check`;
- `cargo fmt --all -- --check`;
- `cargo test -p vmm --features kvm test_next_table_address_overflow` — 1 passed;
- `cargo check -p vmm --features kvm`;
- `cargo check -p vmm --features kvm,fw_cfg`;
- `cargo check -p vmm --features kvm,tdx`;
- `cargo check -p vmm --features kvm --target aarch64-unknown-linux-gnu` with the cross compiler installed;
- retained candidate diff creation and artifact upload.

Retained artifact: `9046890513`
Artifact digest: `sha256:3749e5022ac5aad2cafd713e00a42a1813e04ca82d1c6e7246cb9103d5df676e`

The retained generated patch was reviewed in full. It changes only `vmm/src/acpi.rs` and `vmm/src/vm.rs`. The production panic inventory in `acpi.rs` is accounted for: runtime address, lock and I/O failures are propagated; serial/controller/VGIC presence and IORT layout checks remain the deliberate invariants described above.

The repository's normal CI run for the same carrier head, `31344505713`, is a separate broader evidence surface and was still in progress when this handoff was updated.

## Source freshness

Canonical `main` is 36 commits ahead of the original investigation base through `a1fcb9f790616ac615f66de73be540b0b20844b1`. That drift does not touch `vmm/src/acpi.rs` or `vmm/src/vm.rs`, so the exact-source transformation boundary remains applicable to the reviewed canonical source.

## Remaining work

1. Let the normal fork CI surface complete and classify any failure by owner.
2. Collapse the proven runner-side narrowing edits into `apply_candidate.py` so the carrier has one canonical transform instead of a transform plus repair layer.
3. Re-run the focused gates after that cleanup and review the new exact generated diff.
4. Decide whether a dedicated deterministic test for a second error path is worth the extra fixture cost; address overflow already proves the new `Result` boundary mechanically.
5. Keep the candidate internal until a human explicitly authorizes any upstream interaction.

## External-contact state

`false; none occurred`.
