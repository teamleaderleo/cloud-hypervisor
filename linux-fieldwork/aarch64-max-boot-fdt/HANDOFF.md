# Linux Fieldwork handoff — AArch64 FDT cpu-map vs boot/max vCPUs

Updated: 2026-08-10
State: STRONG / FROZEN INTERNAL CANDIDATE
Tracker: `teamleaderleo/linux-fieldwork#547`
Carrier: `teamleaderleo/cloud-hypervisor#12`
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Prerequisites: exact frozen #543 v2 and #546 candidates
External contact: false; none occurred

## Reproduced defect

AArch64 accepted `max_vcpus > boot_vcpus` when the explicit topology product equaled max vCPUs. Boot CPU creation and AArch64 firmware tables describe the boot set, while FDT cpu-map walked the full max-sized topology.

Concrete case:

- boot vCPUs: 2
- max vCPUs: 4
- topology: `1:4:1:1`

The real AArch64 config-validation path accepted it. FDT emitted CPU nodes for IDs `0,1`, while cpu-map referenced `0,1,2,3`; IDs `2,3` therefore had no CPU node. MADT and PPTT are boot-sized as well, and Cloud Hypervisor documents CPU device hotplug as x86-only.

Baseline run/job: `31362299029` / `93373412318` — success
Baseline artifact: `9052834792`
Baseline artifact digest: `sha256:d7a9de4e4eacc793e5d9511fb24e42b89648d73f853fd7c1e5309b4e55c360c7`

## Frozen candidate

Product scope: exactly `vmm/src/config.rs`.

The candidate preserves the existing max<boot diagnostic, then on AArch64 rejects any remaining `max_vcpus != boot_vcpus` with `Aarch64CpuHotplugUnsupported`. This aligns the accepted configuration space with AArch64's current CPU-hotplug capability and keeps FDT, MADT, and PPTT on one boot-sized CPU domain.

Controls:

- `boot=2,max=4,topology=1:4:1:1` is rejected on AArch64;
- `boot=max=4` with the same topology is accepted;
- x86 configuration validation remains green.

Exact stored patch:

- path: `linux-fieldwork/aarch64-max-boot-fdt/candidate.patch`
- Git blob: `c0fdacec33e6e2080118b568ed1668be5cea492f`
- SHA-256: `0378049238e3625690577f11168d98ee66a35084d4a68f486632dba33550e694`
- product diff: 37 additions / 0 deletions

## Validation receipts

First full product matrix:

- run/job: `31362645368` / `93374441572`
- artifact: `9053009494`
- artifact digest: `sha256:eb3d4c1f504957844061b87a8211c96e8d5aa0522a7c7f8399ecf6846601456f`

Final exact-byte convergence:

- run/job: `31363147511` / `93375931835`
- artifact: `9053207789`
- artifact digest: `sha256:d4983f9a1f921d121456b0da3b3298985a23d59df040f0979771c95a4f4a4672`

The final read-only run applied only the exact stored one-file candidate after exact #543 v2 and #546 prerequisites, passed AArch64 validation behavior, nightly formatting, AArch64 VMM Clippy, AArch64 KVM/MSHV, x86 config-validation regression, x86 KVM compile, and literal stored/generated `cmp` plus SHA checks.

## Reopen conditions

Reopen if AArch64 CPU hotplug becomes supported, firmware CPU enumeration changes, or relevant canonical validation bytes move.
