# Linux Fieldwork handoff — AArch64 shared-L2 FDT/PPTT policy

Updated: 2026-08-10
State: STRONG CANDIDATE / CURRENT BOUNDARY SATURATED
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Branch: `linux-fieldwork/cache-sharing-pptt`
Internal record: `teamleaderleo/linux-fieldwork#542`
Prerequisites: exact validated #8666, #8097, and #541 candidates

## TL;DR

AArch64 FDT and ACPI PPTT consumed the same host cache metadata differently when Linux reported L2 shared among multiple CPUs.

FDT checks `l2_cache_shared` and avoids emitting the ambiguous per-CPU L2 relationship. PPTT ignored that flag and retained its private-L2 hierarchy. Historical Cloud Hypervisor review already contains a real ARMv8 host with L2 `shared_cpu_list=0,4,8,12`, plus the explicit rationale that migratable vCPUs make host L2 sharing difficult to map honestly.

The exact one-file candidate makes PPTT follow the existing FDT caution: preserve L1, omit L2/L3 when host L2 is shared, and leave the cache reader/source metadata intact.

## Real-host and intent evidence

Cloud Hypervisor PR #5621 review reported:

```text
/sys/devices/system/cpu/cpu0/cache/index2
shared_cpu_list: 0,4,8,12
level: 2
```

The response explains that without vCPU affinity, guest-to-host L2 sharing is unstable because a vCPU can migrate, so the FDT code avoids claiming the shared relationship.

Arm documentation covers Armv8-A Cortex-A53/A57/A72-era cluster L2 designs, and GIC-500 supports those cores with GICv3. Cloud Hypervisor documents AArch64 servers or development boards with GICv3 as supported prerequisites.

The commit that added PPTT cache topology (`ec73733b2112d231f3ad8cf14d623002ad920cf7`) states its intended simplifying model as L2 unique per CPU and L3 shared. #542 handles the already-known host counterexample conservatively rather than inventing a guest sharing group from CPU0 metadata.

## Reproduced baseline

Baseline carrier head: `5984c730f13cc624aa4afc7c571cc1820b990286`
Focused run/job: `31354589117` / `93351815736` — success
Artifact: `9050195795`
Artifact digest: `sha256:6cde182b9d479b25b7d20de6fd969c4b65316584607b157f7e3806ad091e07a0`
Probe diff digest: `sha256:06cd0bcdbb93aacbb566194155e8bdbc692532c12bb4a63fac2c202296545171`

The AArch64 qemu-user fixture proves the exact stacked cache reader returns the split-L1/unified-L2/L3 identity layout with `l2_cache_shared=true` for `shared_cpu_list=0,4,8,12`.

The retained guarded policy log records:

```text
shared-l2-fdt-policy: omit-l2-and-l3
shared-l2-pptt-policy: ignores-sharing-flag-and-keeps-l2-private-chain
```

That is the reproduced cross-boot-mode divergence.

## Exact candidate policy

Product scope: `vmm/src/cpu.rs` only.

The candidate:

1. consumes `l2_cache_shared` from `CacheTopologyInfo`;
2. preserves all existing L1 cache description;
3. creates L2 only when L2 size is nonzero and host L2 is not shared;
4. creates L3 only when L3 size is nonzero and host L2 is not shared;
5. therefore matches FDT's current L1-only behavior for ambiguous shared-L2 hosts;
6. does not alter cache discovery, errors, fixed representable identity policy, or vCPU affinity.

A fuller shared-cache model remains a separate future design requiring stable vCPU-to-host grouping semantics.

## Exact product representation

Validated product carrier head: `b3c66237ed59f6d7ac521d821f2f9bf138868ead`
Stored patch: `linux-fieldwork/cache-sharing/candidate.patch`
Patch Git blob: `bb45c3741cdebecd183cd05b769dfd56da4f80ab`
Stored/generated patch digest: `sha256:f25ed351643d03097878b96a8899eaa0d92498adce6c1f37f3f1941f316ca1a4`

Final focused run/job: `31354957658` / `93352819836` — success
Artifact: `9050335649`
Artifact digest: `sha256:fda9508233172888806dd8cc24ebd48578c026723aebdfba2641ce8d58084577`

Product diff: `vmm/src/cpu.rs`, +8/-2.

## Final focused evidence

Passed on exact stored candidate bytes after exact #8666 -> #8097 -> #541 prerequisite application and a separately committed shared-L2 test fixture:

- canonical source blob guards;
- exact prerequisite identities/application;
- stored candidate blob identity and `git apply --check`;
- exact one-file product scope and `git diff --check`;
- guarded FDT/PPTT policy convergence;
- nightly rustfmt;
- all 12 AArch64 cache fixtures under qemu-user;
- immediate clean cache-test rerun;
- focused AArch64 VMM Clippy with warnings denied;
- AArch64 KVM compile;
- AArch64 MSHV compile;
- x86_64 KVM regression compile;
- regenerated one-file product diff;
- automatic `cmp` against stored `candidate.patch`;
- matching stored/generated SHA-256 values.

The final retained policy log says:

```text
shared-l2-fdt-policy: l1-only when host L2 is shared
shared-l2-pptt-policy: l1-only when host L2 is shared
shared-l2-candidate-policy-converged
```

## Review recommendation

Keep the PPTT-only correction. It restores parity with the existing migration-aware FDT behavior with a tiny product diff and preserves the richer cache metadata for future models.

Reopen these bytes for a guarded source change, canonical competing fix, a supported shared-L2 mapping backed by stable vCPU affinity, evidence that L3 should remain exposed across an omitted shared L2, or a boot/backend counterexample.

## External-contact state

`false; none occurred`.
