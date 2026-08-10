# Linux Fieldwork handoff — AArch64 cache topology vs vCPU affinity

Updated: 2026-08-10
State: STRONG / FROZEN INTERNAL CANDIDATE
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Branch: `linux-fieldwork/cache-affinity-selection`
Internal record: `teamleaderleo/linux-fieldwork#543`
Carrier: `teamleaderleo/cloud-hypervisor#9`
Prerequisites: exact validated #8666, #8097, #541, and #542 candidates
External contact: false; none occurred

## Reproduced defect

Cloud Hypervisor's AArch64 cache discovery is sourced from host CPU0 while CpuManager can schedule vCPUs on arbitrary host CPU sets. The baseline proved a legal execution set can exclude CPU0 and contain a different representable private-cache geometry while FDT/PPTT still publish CPU0's cache values.

Baseline run/job: `31355717202` / `93354884981` — success
Baseline artifact: `9050559168`
Baseline artifact digest: `sha256:adb493d8311ddcededdcf5a74eee9550cce749e7664078f8c1370b8f4ddef2ae`

## Frozen candidate

The candidate changes exactly five product files:

- `arch/src/aarch64/cache.rs`
- `arch/src/aarch64/fdt.rs`
- `arch/src/aarch64/mod.rs`
- `vmm/src/cpu.rs`
- `vmm/src/vm.rs`

Policy:

1. CpuManager derives the eligible host CPUs for all configured `max_vcpus`, covering future CPU hotplug.
2. Explicitly pinned vCPUs contribute their configured host CPU sets.
3. Any vCPU without explicit affinity contributes the process scheduler affinity read through `sched_getaffinity()`.
4. The affinity mask grows dynamically on `EINVAL`, covering CPU IDs beyond libc `CPU_SETSIZE`.
5. Eligible CPUs are unioned/deduplicated.
6. Each eligible `cpuN/cache` root is parsed with the validated #8097/#541 identity-aware cache reader.
7. Cache passthrough proceeds only when all eligible CPUs have one equal representable `CacheTopologyInfo`; otherwise the existing cache-less path is used.
8. FDT and PPTT consume the same eligible CPU set/common topology.
9. #542's shared-L2 omission policy remains intact.

The candidate preserves cache publication for a homogeneous pinned execution set and avoids copying CPU0 onto heterogeneous or CPU0-excluding execution sets.

## Exact bytes

Stored patch: `linux-fieldwork/cache-affinity/candidate.patch`
Git blob: `57542277a76d84ed4bfca58aab871ef27f090beb`
SHA-256: `8d5338bfa915420f981802929dea8bf6aad11da77c75f7c602cd73e5aca6b19c`
Product diff: 5 files, 242 additions / 9 deletions.

## Validation receipts

First fully-green refined matrix:

- run/job: `31357210873` / `93359031429`
- artifact: `9051103464`
- artifact digest: `sha256:2bb96b20453fd0d4a8252fc268c5998cde9a5405fcd0bade18efbdc630afb758`

Final exact-byte convergence:

- run/job: `31359443184` / `93365235611`
- artifact: `9051848655`
- artifact digest: `sha256:eaaad0e37691f6ba54df32c5505802f2581c03b6b9b2728e872527f522cfe709`

The final read-only run verified exact prerequisite/source blobs, applied only the stored candidate, passed common-topology tests, pinned/mixed affinity tests, host CPU ID 1300, future hotplug eligibility, all AArch64 cache regressions, nightly formatting, Clippy, AArch64 KVM/MSHV, and x86_64 KVM. It regenerated the five-file product diff and passed literal stored/generated `cmp` plus both SHA-256 checks.

## Reopen conditions

Reopen if relevant canonical bytes move materially, a supported-host counterexample invalidates the common-topology policy, or a competing affinity-aware cache representation appears upstream.

A richer per-vCPU/per-cluster guest cache model remains outside this lane.
