# Linux Fieldwork handoff — ACPI error propagation

Updated: 2026-08-05
State: SOURCE TRACE COMPLETE, CANDIDATE DESIGN IN PROGRESS
Branch base: canonical `383773a03d8105e3fa6e2a9364b2a8e8366626b0`
Upstream issue: `cloud-hypervisor/cloud-hypervisor#8666`
Internal record: `teamleaderleo/linux-fieldwork#444`

## Finding

The ACPI creation pipeline is non-fallible at its core even though it performs fallible address arithmetic, resource lookup and guest-memory I/O.

Current signatures:

- `create_acpi_tables_internal(...) -> (Rsdp, Vec<u8>, Vec<u64>)`;
- `create_acpi_tables(...) -> GuestAddress`;
- `create_acpi_tables_tdx(...) -> Vec<Sdt>`;
- `create_acpi_tables_for_fw_cfg(...) -> Result<(), vm::Error>`.

The fw_cfg path has an I/O error boundary, but panics before reaching it when fw_cfg is absent or its mutex is poisoned. The direct-memory path panics on guest-memory writes and cannot propagate failures because the VM wrapper returns `Option<GuestAddress>`.

## Panic ownership map

Runtime/environment-sensitive:

- allocator mutex in FADT construction;
- aarch64 interrupt-controller presence, mutex and VGIC presence;
- aarch64 serial-device lookup;
- fw_cfg presence and mutex;
- RSDP and table writes into guest memory;
- checked ACPI table-address additions.

Programmer/layout invariants:

- fixed ACPI structure sizes;
- IORT alignment assumptions;
- IORT PCI segment limit.

The candidate should propagate the first group. The second group must remain explicit invariants or be converted to compile-time validation where possible, not silently ignored.

## Candidate contract

- introduce `acpi::Error`;
- make fallible table helpers and `create_acpi_tables_internal` return `Result`;
- centralize checked table-address advancement;
- make direct, fw_cfg and TDX entry points return `Result`;
- change the VM wrapper to `Result<Option<GuestAddress>, vm::Error>` and use `?` at boot call sites;
- use one VM error variant for ACPI creation across delivery modes;
- add deterministic unit coverage for address overflow and any pure resource-validation helpers.

## Required validation

- exact-current-source patch application;
- rustfmt and diff checks;
- default x86_64 compile;
- fw_cfg compile;
- aarch64 compile to cover interrupt controller, serial and IORT paths;
- TDX compile to cover HOB table creation;
- focused unit tests.

## External-contact state

`false; none occurred`.
