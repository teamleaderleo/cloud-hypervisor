# Linux Fieldwork handoff — AArch64 cache topology vs vCPU affinity

Updated: 2026-08-10
State: ACTIVE BASELINE PROBE
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Branch: `linux-fieldwork/cache-affinity-selection`
Internal record: `teamleaderleo/linux-fieldwork#543`
Prerequisites: exact validated #8666, #8097, #541, and #542 candidates

## TL;DR

Cloud Hypervisor reads AArch64 cache topology only from host CPU0, then publishes that one topology to every guest CPU in both FDT and PPTT. CpuManager independently supports arbitrary per-vCPU host CPU affinity, and by default vCPUs can run across the host CPU set.

On a heterogeneous Arm host, a legal affinity configuration can exclude CPU0 entirely while eligible host CPUs have different private cache geometry. The first carrier is test-only: prove two valid representable per-CPU cache roots can differ, then guard the exact current source paths showing cache publication still selects CPU0 while runtime affinity selects another CPU set.

## Supported-host evidence

Arm DynamIQ supports heterogeneous Cortex-A75 + Cortex-A55 combinations in one cluster with thread migration between core types. Cortex-A55 private L2 is configurable from 64KB to 256KB; Cortex-A75 also has configurable private L2. GIC-600 supports DynamIQ Armv8 cores with GICv3.

Cloud Hypervisor documents AArch64 servers or development boards with GICv3 as its AArch64 prerequisite. Its CPU documentation says vCPU affinity can select arbitrary host CPU sets and that, by default, a vCPU runs on the entire host CPU set.

## Exact current source

Cache reader:

```text
/sys/devices/system/cpu/cpu0/cache
```

is the single production source used by `read_cache_topology()`.

CpuManager owns:

```text
affinity: BTreeMap<u32, Box<[usize]>>
```

and converts the selected host CPUs into the actual `sched_setaffinity()` cpuset for each vCPU thread.

FDT calls `read_cache_topology()` once and applies the result across its CPU nodes. PPTT also calls `read_cache_topology()` once and uses the result across its processor hierarchy.

## Baseline discriminator

After exact #8666 -> #8097 -> #541 -> #542 application:

1. create synthetic `cpu0/cache` and `cpu4/cache` roots with the same representable split-L1/unified-L2/L3 identity but different private L1/L2 sizes;
2. execute both roots through the exact cache parser and prove both are valid yet different;
3. use a legal affinity example `{vcpu0: [4,5], vcpu1: [4,5]}` whose execution set excludes CPU0;
4. guard exact production source showing cache selection remains CPU0-only for both FDT and PPTT;
5. retain only the test diff and policy logs.

A green baseline proves the product can publish cache geometry from a host CPU outside the vCPU execution set. It is not a product fix.

## Candidate direction if reproduced

Compute one common representable topology from the host CPUs the guest can actually execute on.

Safe policy:

- if every relevant eligible host CPU has the same representable topology, publish that common topology;
- if eligible CPUs disagree, omit cache passthrough;
- for any vCPU without explicit affinity, treat the full online host CPU set as eligible;
- use the same selected topology for FDT and PPTT;
- keep #541's identity recognizer and #542's shared-L2 policy intact.

This is preferable to checking all host CPUs unconditionally because an explicitly pinned VM may use a homogeneous subset of a heterogeneous host.

A richer per-vCPU/per-cluster guest cache model remains a larger future design.

## External-contact state

`false; none occurred`.
