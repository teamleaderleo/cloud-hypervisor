# Linux Fieldwork handoff — AArch64 cache topology vs vCPU affinity

Updated: 2026-08-10
State: STRONG / FROZEN INTERNAL CANDIDATE v3
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Branch: `linux-fieldwork/cache-affinity-selection`
Internal record: `teamleaderleo/linux-fieldwork#543`
Carrier: `teamleaderleo/cloud-hypervisor#9`
External contact: false; none occurred

## Reproduced defect

Cloud Hypervisor's AArch64 cache discovery was sourced from host CPU0 while CpuManager can schedule vCPUs on arbitrary host CPU sets. The refreshed negative control proves on the final prerequisite chain that two legal host CPU cache roots can carry different representable private-cache geometry, so publishing CPU0 unconditionally can describe the wrong execution set.

Refreshed baseline:

- head: `d7d7ce4e686d1b8995c4acf6d1547d5f8fddfbf5`
- run/job: `31386883339` / `93449175645` — success
- artifact: `9062095139`
- artifact digest: `sha256:40c67563008483b72eee25e236283a0f466b4bb4173ebb65f1a3997f3d8d7140`

## Exact prerequisite chain

Canonical source starts at `a1fcb9f790616ac615f66de73be540b0b20844b1`, then applies:

1. submitted ACPI error boundary `e9c86bacee14a2fd6fe871dc678c6b3f1ac4012a`;
2. final cache-runtime-error carrier `a696e285eaece00335e106acdfb5a651ccb2261f`;
   - parser blob `64dc6a19b132aad66b1adaccf9aaa1853a734d7c`;
   - propagation blob `9e175e73a26530d8dd5584cb15ae3ab4b36df196`;
3. refreshed cache-identity carrier `8dfd55a96b0cbf3d6891c25735455b8b793133e9`;
   - candidate blob `b6e21517377995f35ff6984ffc29f06a21db06b7`;
4. refreshed PPTT-sharing carrier `32cde9c6849c9744e2945f6900c8e4035f7ccf03`;
   - candidate blob `e606e0559e7d82689eb2ec2f29ed485715d36900`;
5. this refreshed v3 candidate.

## Frozen v3 candidate

The candidate changes exactly six product files:

- `arch/src/aarch64/cache.rs`
- `arch/src/aarch64/fdt.rs`
- `arch/src/aarch64/mod.rs`
- `vmm/src/cpu.rs`
- `vmm/src/vm.rs`
- `vmm/src/vm_config.rs`

Policy:

1. CpuManager derives eligible host CPUs from configured affinity plus process scheduler affinity for unpinned vCPUs.
2. The scheduler-affinity buffer grows on `EINVAL`, covering CPU IDs beyond libc `CPU_SETSIZE`.
3. Eligible CPUs are unioned and deduplicated across configured `max_vcpus`, including hotpluggable vCPUs.
4. Each eligible `cpuN/cache` root is parsed through the validated identity-aware cache reader.
5. Cache passthrough proceeds only when every eligible CPU has one equal representable `CacheTopologyInfo`; otherwise the existing cache-less path is used.
6. FDT and PPTT consume the same selected execution set and common topology.
7. The shared-L2/private-L3 omission policy remains intact.
8. AArch64 filesystem restrictions grant read-only access at `/sys/devices/system/cpu`, covering every dynamically selected `cpuN/cache` descendant.

## Why v3 exists

Frozen v2 was authored over an earlier cache-identity prerequisite. After #541 was refreshed, its `arch/src/aarch64/cache.rs` implementation changed enough that the v2 cache hunk no longer applied textually.

The restack was evidence-driven:

1. Reconstruct the historical prerequisite tree in a temporary worktree and verify v2 against its original preimage.
2. Restore those transient preimage blobs to Git's object database and three-way apply v2 onto the final prerequisite chain.
3. Observe one source-level API drift only in the two v2 cache-root tests: final #541 split `write_identity(..., size)` into `write_identity(...)` plus `write_property(..., "size", ...)`.
4. Adapt exactly twelve fixture calls, preserving the same cache identities, sizes, and assertions.
5. Run the complete selector, policy, regression, formatting, quality, and backend matrix.
6. Freeze the mechanically restacked result as v3 and rerun through a simple direct-apply carrier to literal byte equality.

No selector, affinity, Landlock, FDT/PPTT, omission-policy, or production behavior was changed during the v2 -> v3 refresh.

## Exact v3 bytes

Stored patch: `linux-fieldwork/cache-affinity/candidate.patch`
Git blob: `c1d99cfc6166efaa7871b0648e119c0a434a157f`
SHA-256: `aec77fdcb31df5667bfbea0c688e00ea07a9750f5cdd1c9cdc9b1d67404939a0`
Stable patch ID: `e802917e7fb7320d5d99b05ec1902666e18b73f5`
Product diff: 6 files, 255 additions / 10 deletions.

## Authoritative candidate receipt

- validated candidate head: `9775f648653ee495aa1a44aacaf64f656720eb13`
- run/job: `31386771082` / `93448827517` — success
- artifact: `9062114230`
- artifact digest: `sha256:77e47ee076b4ef3d65f83b34be0233a065feb4d491a61eec6aab1eca7aa305fc`
- stored/generated SHA-256: `aec77fdcb31df5667bfbea0c688e00ea07a9750f5cdd1c9cdc9b1d67404939a0` / identical
- stored/generated stable patch ID: `e802917e7fb7320d5d99b05ec1902666e18b73f5` / identical

The candidate receipt passed:

- exact final prerequisite heads and blobs;
- direct v3 patch application;
- exact six-file product scope and `git diff --check`;
- selector and Landlock policy verification;
- nightly rustfmt;
- matching-root and differing-root common-cache tests;
- fully pinned, inherited-default, high-CPU-ID, and hotpluggable-vCPU affinity tests;
- full AArch64 cache regression;
- AArch64 `arch` and `vmm` Clippy with warnings denied;
- AArch64 KVM and MSHV compile;
- x86_64 KVM VMM compile;
- literal full-index stored/generated `cmp` equality;
- stable patch-ID equality.

## Boundary and stop condition

The candidate deliberately requires one common representable topology across every eligible host CPU. It does not invent per-vCPU guest cache domains or a migration model for heterogeneous cache groups.

The dependency chain now has a coherent end for this investigation:

```text
submitted ACPI boundary
  -> cache runtime errors (#499)
  -> cache leaf identity (#541)
  -> PPTT sharing parity (#542)
  -> affinity/common topology (#543)
```

Issue #544 is already closed as a duplicate of the PPTT-sharing work.

Reopen if relevant canonical bytes move materially, a supported-host counterexample invalidates the common-topology policy, the AArch64 filesystem-restriction lifecycle changes, or a competing affinity-aware cache representation appears upstream.
