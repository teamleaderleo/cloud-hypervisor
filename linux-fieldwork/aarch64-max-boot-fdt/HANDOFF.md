# Linux Fieldwork handoff — AArch64 FDT cpu-map vs boot/max vCPUs

Updated: 2026-08-10
State: ACTIVE BASELINE PROBE
Tracker: `teamleaderleo/linux-fieldwork#547`
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Prerequisites: exact frozen #543 v2 and #546 candidates
External contact: false; none occurred

## Question

Can an accepted AArch64 configuration with `max_vcpus > boot_vcpus` cause FDT's full topology cpu-map to reference CPU phandles that have no boot-time CPU node?

## Concrete discriminator

Configuration:

- boot vCPUs: 2
- max vCPUs: 4
- topology: `1:4:1:1`

Generic validation accepts this relationship: max is at least boot, the topology parts are nonzero, AArch64 dies/package is 1, and the topology product equals max vCPUs.

At boot, CpuManager creates only boot vCPUs and `get_mpidrs()` reflects the existing vCPU vector. FDT emits CPU nodes from that MPIDR list, so IDs 0 and 1 exist. The FDT cpu-map walks every configured topology slot, so IDs 0 through 3 are referenced. IDs 2 and 3 therefore exceed the emitted CPU-node domain.

Cloud Hypervisor's hotplug documentation says CPU device hotplug is currently x86-only, so there is no documented AArch64 lifecycle that later makes those FDT references useful.

## Baseline method

The carrier stacks exact #543 v2 and #546 bytes as committed local prerequisites, then adds only two test-only changes:

- `vmm/src/config.rs`: AArch64-only assertion that `boot=2,max=4,topology=1:4:1:1` passes the existing validation path.
- `arch/src/aarch64/fdt.rs`: arithmetic discriminator proving a max-sized topology map outruns a boot-sized CPU-node domain.

A source-policy guard independently checks the production validation rules, boot-vCPU creation/MPIDR path, FDT CPU-node loop, full topology cpu-map loop, and documented x86-only CPU hotplug boundary.

## Decision after baseline

If reproduced, compare two candidate boundaries:

1. reject `max_vcpus != boot_vcpus` for AArch64 while CPU hotplug remains unsupported;
2. constrain FDT cpu-map emission to boot-present CPUs without dangling references.

Cross-check ACPI/MADT/PPTT behavior before selecting product scope.
