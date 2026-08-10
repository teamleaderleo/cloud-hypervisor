# Linux Fieldwork handoff — AArch64 shared-L2 FDT/PPTT policy

Updated: 2026-08-10
State: ACTIVE BASELINE PROBE
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Branch: `linux-fieldwork/cache-sharing-pptt`
Internal record: `teamleaderleo/linux-fieldwork#542`
Prerequisites: exact validated #8666, #8097, and #541 candidates

## TL;DR

AArch64 FDT and ACPI PPTT currently consume the same host cache metadata differently when Linux reports L2 shared among multiple CPUs.

FDT checks `l2_cache_shared` and avoids emitting the ambiguous per-CPU L2 relationship. PPTT ignores that flag and retains its private-L2 hierarchy. Historical Cloud Hypervisor review already contains a real ARMv8 host with L2 `shared_cpu_list=0,4,8,12`, plus the explicit rationale that migratable vCPUs make host L2 sharing difficult to map honestly.

The first carrier is test-only. It proves the exact stacked cache reader returns the representable L1/L2/L3 identity layout with `l2_cache_shared=true`, while guarded source assertions verify FDT takes the omission branch and PPTT ignores the flag.

## Real-host evidence

Cloud Hypervisor PR #5621 review reported:

```text
/sys/devices/system/cpu/cpu0/cache/index2
shared_cpu_list: 0,4,8,12
level: 2
```

The response explains that without vCPU affinity, guest-to-host L2 sharing is unstable because a vCPU can migrate, so the FDT code avoids claiming the shared relationship.

Arm documentation also covers Armv8-A Cortex-A53/A57/A72-era cluster L2 designs, and GIC-500 supports those cores with GICv3. Cloud Hypervisor documents AArch64 servers or development boards with GICv3 as supported prerequisites.

## Current source divergence

FDT:

```text
l2_cache_size != 0 && !l2_cache_shared
```

is required before per-CPU L2 is emitted. Shared L2 also suppresses the later L3 block.

PPTT:

- ignores `l2_cache_shared` while destructuring `CacheTopologyInfo`;
- creates L2 whenever its size is nonzero;
- links L1 descriptors to that L2 descriptor;
- attaches L1 private resources to processor leaves.

ACPI descriptor reuse is valid compaction and is not the bug. The relevant semantic choice is that the L2 remains in the processor-private hierarchy even when source metadata says the host L2 is shared.

## Baseline plan

After exact #8666 -> #8097 -> #541 application:

1. inject one synthetic cache fixture with split L1, unified L2/L3, and L2 `shared_cpu_list=0,4,8,12`;
2. execute the fixture under AArch64 qemu-user and require `l2_cache_shared=true`;
3. guard exact FDT source showing shared L2 suppresses L2/L3;
4. guard exact PPTT source showing `l2_cache_shared` is ignored and the L1->L2 private-resource chain remains;
5. retain only the test diff and logs.

A green baseline proves the cross-boot-mode policy divergence. It is not a product fix.

## Candidate direction if reproduced

Prefer the historical migration-aware policy. The first candidate should avoid inventing a shared grouping from CPU0 host metadata.

The narrowest correction is likely PPTT-only: consume `l2_cache_shared` and omit L2/L3 when it is true, preserving L1 and matching FDT's current guest-visible caution. A shared cache-reader omission would also remove L1 and would be a broader behavior change.

A fuller shared-cache model needs stable vCPU affinity/group mapping and belongs in a separate design.

## External-contact state

`false; none occurred`.
