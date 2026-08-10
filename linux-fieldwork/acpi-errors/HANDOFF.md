# Linux Fieldwork handoff — ACPI error propagation

Updated: 2026-08-10
State: CANDIDATE NARROWED, EXACT-HEAD CI PENDING
Branch base: canonical `383773a03d8105e3fa6e2a9364b2a8e8366626b0`
Candidate semantic head: `fd25b6848a7ebe676c86985533954e623db4b31e`
Current carrier head after handoff updates: `24924b4df76ef598fed1675310f45ed667d77adc`
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

The direct-memory path cannot propagate guest-memory failures because the VM wrapper returns `Option<GuestAddress>`. The fw_cfg path already has a VM error boundary but still unwraps fw_cfg presence and its mutex before reaching `add_acpi()`.

## Refined panic ownership map

Propagate as runtime construction failures:

- checked ACPI table-address additions;
- allocator mutex poisoning while constructing the FADT;
- aarch64 interrupt-controller mutex poisoning while reading the VGIC;
- fw_cfg absence at the helper boundary and fw_cfg mutex poisoning;
- guest-memory writes of the RSDP and table bytes;
- `fw_cfg::add_acpi()` I/O failure.

Keep as programmer or validated-configuration invariants:

- fixed ACPI structure sizes; move the two fixed-size checks to compile-time assertions;
- IORT header and alignment assertions;
- IORT PCI segment `< 256` assertion. `PlatformConfig::validate()` caps `num_pci_segments` at 96 and `DeviceManager::new()` creates IDs from `0..num_pci_segments`, so a valid VM cannot reach IORT with a segment ID >= 256;
- aarch64 interrupt-controller presence. VM initialization creates and installs the controller before boot reaches ACPI creation;
- aarch64 VGIC presence. `Gic::new()` always stores `vgic: Some(...)` and `get_vgic()` currently returns that value;
- serial-device lookup consistency. ACPI first tests the same immutable device-info map for the serial entry and then indexes it, so silently converting inconsistency into the serial-off fallback would hide a programmer error.

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

## Candidate repair history

The first focused CI run exposed two different owners:

1. the generated aarch64 VGIC rewrite expanded a single `#[cfg(target_arch = "aarch64")]` statement into multiple statements, leaving an x86_64 reference to `interrupt_controller` outside the cfg gate;
2. the focused test originally built VMM tests without a hypervisor backend, producing unrelated uninhabited-hypervisor/VFIO errors.

The workflow now runs the focused test with `--features kvm`. Source review then found a second aarch64 transform bug before execution: `Gic::get_vgic()` returns `Result<Arc<Mutex<dyn Vgic>>>`, while the candidate treated it as `Option`. The narrowed transform avoids adding a new VGIC error model and only propagates mutex poisoning on that path.

The transform runner has also been syntax-checked independently after the narrowing edit. Full candidate execution still requires the repository source and Cargo workspace through the hosted gate.

## Source freshness

Canonical `main` is 36 commits ahead of the original investigation base through `a1fcb9f790616ac615f66de73be540b0b20844b1`. That drift does not touch `vmm/src/acpi.rs` or `vmm/src/vm.rs`, so the exact-source transformation boundary remains applicable to the reviewed canonical source.

## Required validation

- exact-current-source patch application;
- `git diff --check` and exact changed-file scope;
- `cargo fmt --all -- --check`;
- `cargo test -p vmm --features kvm test_next_table_address_overflow`;
- `cargo check -p vmm --features kvm`;
- `cargo check -p vmm --features kvm,fw_cfg`;
- `cargo check -p vmm --features kvm,tdx`;
- aarch64 `cargo check -p vmm --features kvm --target aarch64-unknown-linux-gnu`;
- complete generated diff review after the exact-head run.

No green run from an older head validates the current candidate.

## External-contact state

`false; none occurred`.
