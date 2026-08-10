# Linux Fieldwork handoff — AArch64 PPTT cache sharing

Updated: 2026-08-10
State: STRONG EXACT CANDIDATE / CURRENT BOUNDARY SATURATED
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Branch: `linux-fieldwork/cache-sharing-pptt`
Internal record: `teamleaderleo/linux-fieldwork#542`
Internal PR: `teamleaderleo/cloud-hypervisor#8`
Prerequisites: exact validated #8666, repaired #8097, and exact identity-aware #541 candidates

## TL;DR

AArch64 FDT and ACPI PPTT consumed the same host cache metadata differently. FDT already uses `l2_cache_shared` and `l3_cache_shared` to avoid cache relationships it cannot represent honestly. PPTT historically discarded those fields and assumed L2 private-per-CPU and L3 package-shared.

The original shared-L2 discrepancy is real-host-backed: Cloud Hypervisor review recorded an ARMv8 host with L2 `shared_cpu_list=0,4,8,12` and the explicit migration-aware rationale for avoiding a guessed guest sharing relationship. Independent review also found a reachable private-L3 discrepancy: FDT omits a non-shared L3, while PPTT previously attached every nonzero L3 at package level.

The final exact one-file candidate consolidates both cases. Duplicate Fieldwork #544 is superseded by this owning lane.

## Real-host and intent evidence

Cloud Hypervisor PR #5621 review reported:

```text
/sys/devices/system/cpu/cpu0/cache/index2
shared_cpu_list: 0,4,8,12
level: 2
```

The review response explains that without stable vCPU affinity, guest-to-host L2 sharing is unstable because a vCPU can migrate, so FDT avoids claiming the shared relationship.

The commit that added PPTT cache topology (`ec73733b2112d231f3ad8cf14d623002ad920cf7`) explicitly describes its simplifying assumption as L2 unique per CPU and L3 shared. This candidate corrects the known counterexamples conservatively rather than inventing a sharing group from CPU0 metadata.

Linux's PPTT consumer also confirms why an unrepresentable shared L2 must suppress L3: cache level is inferred by walking cache `next_level` links and then processor-parent hierarchy. Keeping package L3 after dropping L2 would shift that physical L3 into the next guest cache level.

## Reproduced baseline

Baseline carrier head: `5984c730f13cc624aa4afc7c571cc1820b990286`
Focused run/job: `31354589117` / `93351815736` — success
Artifact: `9050195795`
Artifact digest: `sha256:6cde182b9d479b25b7d20de6fd969c4b65316584607b157f7e3806ad091e07a0`
Probe diff digest: `sha256:06cd0bcdbb93aacbb566194155e8bdbc692532c12bb4a63fac2c202296545171`

The qemu-user fixture proves the exact stacked cache reader can return a normal split-L1/unified-L2/L3 identity layout with `l2_cache_shared=true` for `shared_cpu_list=0,4,8,12`.

## Final policy

- private nonzero L2 -> expose L2;
- shared L2 -> omit L2 and L3;
- shared nonzero L3 -> expose only when the L2 chain is representable;
- private/non-shared L3 -> omit rather than falsely attach at package level;
- L1 remains unchanged.

The duplicate #544 experiment also tested L3-without-L2. That case is intentionally absent from the final product boundary because exact #541 already rejects that cache identity layout before PPTT construction.

## Exact prerequisite chain

The runner begins from guarded canonical blobs and applies:

1. #8666 carrier `0a2f55acbd23b7f44899a69132a4236ef9240027`;
2. repaired #8097 carrier `23c8d996457eb8f489f5cfb1bf7f33c9e506e44e`;
3. exact #541 identity-discovery carrier `0cffc6c8f8d79dddb95bce305976a101d8b90a9e`;
4. carrier-only shared-L2 and private-L3 fixtures;
5. exact stored #542 product patch.

## Exact product representation

Validated carrier head: `e9ffa839ac4a713cf87f7e55f96e5e2d4a07f4b1`
Stored patch: `linux-fieldwork/cache-sharing/candidate.patch`
Patch Git blob: `e606e0559e7d82689eb2ec2f29ed485715d36900`
Stored/generated SHA-256: `8729ff3d3c106768b536fbfb674f6cdbb0771d133c62e3d2c05de47012eed014`
Product scope: `vmm/src/cpu.rs`, +9/-2.

Final focused run/job: `31356875709` / `93358100708` — success
Artifact: `9050978935`
Artifact digest: `sha256:cc3a6aefb1712c3085c0c48f94ae243a76d183c619e6a2c4b6dddf8d1701c25a`

## Final evidence

Passed on exact stored bytes:

- guarded canonical source and exact prerequisite identities;
- candidate blob verification and `git apply --check`;
- exact one-file product scope and `git diff --check`;
- FDT/PPTT policy convergence for both shared-L2 and private-L3 inputs;
- nightly rustfmt;
- all 19 AArch64 cache fixtures under qemu-user;
- immediate clean cache-test rerun;
- AArch64 VMM Clippy with warnings denied;
- AArch64 KVM compile;
- AArch64 MSHV compile;
- x86_64 KVM VMM Clippy with warnings denied;
- regenerated one-file diff;
- `cmp` equality against stored `candidate.patch`;
- matching `8729ff3d...` SHA-256 receipt.

## Review recommendation

Keep this tiny PPTT-only correction. It restores parity with established FDT caution while preserving source metadata for future topology work.

A fuller sharing model requires stable vCPU-to-host topology semantics and exact cache-domain identity. Fieldwork #543 owns that separate CPU0/affinity/cache-domain mapping problem.

Reopen these bytes for guarded source change, a canonical competing fix, a valid sharing layout these rules misclassify, or a supported boot/backend counterexample.

## External-contact state

`false; none occurred`.
