# Linux Fieldwork handoff — AArch64 cache topology vs vCPU affinity

Updated: 2026-08-10
State: STRONG / FROZEN INTERNAL CANDIDATE v2
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

## Frozen v2 candidate

The candidate changes exactly six product files:

- `arch/src/aarch64/cache.rs`
- `arch/src/aarch64/fdt.rs`
- `arch/src/aarch64/mod.rs`
- `vmm/src/cpu.rs`
- `vmm/src/vm.rs`
- `vmm/src/vm_config.rs`

Policy:

1. CpuManager derives eligible host CPUs from configured affinity plus the process scheduler affinity for unpinned vCPUs.
2. The scheduler affinity buffer grows on `EINVAL`, covering CPU IDs beyond libc `CPU_SETSIZE`.
3. Eligible CPUs are unioned/deduplicated across configured `max_vcpus`.
4. Each eligible `cpuN/cache` root is parsed through the validated identity-aware cache reader.
5. Cache passthrough proceeds only when every eligible CPU has one equal representable `CacheTopologyInfo`; otherwise the existing cache-less path is used.
6. FDT and PPTT consume the same selected execution set/common topology.
7. #542's shared-L2 omission policy remains intact.
8. AArch64 filesystem restrictions grant read-only access at `/sys/devices/system/cpu`, covering every dynamically selected `cpuN/cache` descendant.

The sixth-file v2 repair closes the integration gap left by v1: the affinity-aware cache reads occur after the VM's filesystem restrictions are applied, so a CPU0-only permission would deny reads for eligible CPUs elsewhere in sysfs.

## Exact bytes

Stored patch: `linux-fieldwork/cache-affinity/candidate.patch`
Git blob: `75601cb2fa2a7d8f8f85dcdd9c3724c41a18d947`
SHA-256: `b38cfe17b90a7cda804b8ad9bdcd921cab4891457d55674a0691b7f0da310498`
Product diff: 6 files, 243 additions / 10 deletions.

## Validation receipts

First full v2 matrix:

- run/job: `31360787893` / `93369120131`
- artifact: `9052332520`
- artifact digest: `sha256:d72897ed011ec80ec802ab31eff6a7e818c7e8d7f01b3c5dc63b943ebf866089`

Final exact-byte convergence:

- run/job: `31361292996` / `93370533814`
- artifact: `9052502842`
- artifact digest: `sha256:f89512a030fca8fec147a9836877d38100115d763a64a4f75d8aa0a1a22ccd8a`

The final read-only run verified exact prerequisite/source blobs, applied only the stored v2 candidate, passed six-file scope, selector/filesystem-access policy checks, common-topology and affinity tests including host CPU ID 1300, all AArch64 cache regressions, nightly formatting, AArch64 Clippy, AArch64 KVM/MSHV, x86_64 KVM, and literal stored/generated `cmp` plus SHA checks.

The former five-file v1 candidate remains historical evidence and is superseded.

## Reopen conditions

Reopen if relevant canonical bytes move materially, a supported-host counterexample invalidates the common-topology policy, the AArch64 filesystem-restriction lifecycle changes, or a competing affinity-aware cache representation appears upstream.
