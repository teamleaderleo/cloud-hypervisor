# Linux Fieldwork handoff — AArch64 cacheinfo index portability

Updated: 2026-08-10
State: STRONG EXACT CANDIDATE / CURRENT BOUNDARY SATURATED
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Branch: `linux-fieldwork/cache-index-portability`
Canonical issue: none; internal portability correctness question
Internal record: `teamleaderleo/linux-fieldwork#541`
Prerequisites: exact validated #8666 ACPI candidate and repaired exact #8097 cache-runtime-error candidate

## TL;DR

Canonical Cloud Hypervisor assigns fixed AArch64 cache meanings to sysfs positions (`index0=L1D`, `index1=L1I`, `index2=L2`, `index3=L3`). Linux arm64 enumerates cacheinfo entries by cache leaf instead, so unified or split levels can shift those positions.

The test-only baseline proved two concrete semantic misidentifications. The final one-file candidate discovers numeric `indexN` leaves, reads each leaf's `level` and `type`, and fills only the cache identities the current guest FDT/PPTT model can represent. Valid but unrepresentable layouts are omitted rather than mislabeled. Higher cache levels are parsed and ignored, so L4+ cannot shift L1-L3.

## Reproduced baseline

Baseline head: `06f6343cbf3762095b8d808aa8b6a09a30537414`
Focused run/job: `31353310424` / `93348082267` — success
Artifact: `9049729478`
Artifact digest: `sha256:4e922bac17707e84b836e195d14b7a1253107e56b50b4451d2a6a2b5e2f28658`
Probe diff digest: `sha256:a9312f91ae131dab9a00b12fa492f2cc00549b7894948ee7a0fb17285b631365`

The AArch64 qemu-user probe proved:

1. split L1 Data/Instruction + unified L2/L3 agrees with the current mapping;
2. unified L1 makes the current L1I field consume an L2 Unified leaf and current L2 consume L3 bytes;
3. split L2 makes current L3 consume the L2 Instruction leaf while the actual L3 sits at `index4`.

## Linux identity contract

Linux arm64 advances cacheinfo index per cache leaf: a separate cache level contributes Data then Instruction leaves; a unified/data-only/instruction-only level contributes one leaf; firmware-described external levels can add more leaves. Linux exports identity separately as `level` and `type` (`Data`, `Instruction`, `Unified`). Therefore `indexN` is discovery position, not architectural cache identity.

## Final candidate policy

`arch/src/aarch64/cache.rs` only:

1. enumerate all directory entries named `index<digits>`;
2. require and parse `level` and `type` identity for every present leaf;
3. map L1 Data, L1 Instruction, L2 Unified, and L3 Unified independent of sysfs index number;
4. ignore valid levels above L3 after parsing identity;
5. valid <=L3 layouts the current guest model cannot represent — unified L1, split L2, duplicate identities, incomplete split L1, or L3 without L2 — warn and return `Ok(None)`;
6. missing/malformed identity on a present leaf is a typed error, because identity is required to know what the leaf means;
7. preserve repaired #8097 scalar policy: absent size/line/sets/shared properties use existing zero/false defaults; malformed-present values, non-`NotFound` I/O, and overflow return errors.

The existing public cache getter functions remain exported to avoid unrelated API churn. They now resolve semantic identity before reading their requested scalar. `read_cache_topology()` resolves the leaf map once for the full topology read.

## Exact prerequisite chain

The exact runner starts from guarded canonical blobs and applies:

- #8666 carrier `0a2f55acbd23b7f44899a69132a4236ef9240027`, patch blob `034cebd92cf31e3b415cdd3d205035b96cd9c1fb`;
- repaired #8097 carrier `23c8d996457eb8f489f5cfb1bf7f33c9e506e44e`, parser blob `f381a777ea3343c33d2dd0bdbde067a2a91cc692`, propagation blob `cbfe0675d08f3b4bc1871d3825b9c67d8d5ac71c`;
- exact stored #541 candidate patch.

`run_candidate.py` is now an exact applicator. It does not generate Rust source.

## Exact product representation

Validated carrier head: `0cffc6c8f8d79dddb95bce305976a101d8b90a9e`
Stored patch: `linux-fieldwork/cache-index/candidate.patch`
Patch Git blob: `b6e21517377995f35ff6984ffc29f06a21db06b7`
Stored/generated patch digest: `sha256:c3c0b19e8025fa8b1f90d9b2378165676f877fe2572c52b62e3ab1871e13e1e9`

Final focused run/job: `31355462839` / `93354194042` — success
Artifact: `9050489516`
Artifact digest: `sha256:c4e80cb61966b3be3ea8a83d60650c20c7ff109a91ed5e307d48ae4017e06107`

Product scope: one file, `arch/src/aarch64/cache.rs`, approximately +454/-78. Most growth is identity classification and deterministic fixtures.

## Final focused evidence

Passed on the exact stored candidate bytes:

- guarded canonical source blobs;
- exact #8666 and repaired #8097 prerequisite identities;
- candidate blob verification and `git apply --check`;
- exact one-file product scope and `git diff --check`;
- nightly rustfmt;
- all 17 AArch64 cache tests under qemu-user;
- immediate clean rerun;
- AArch64 `arch` Clippy with warnings denied;
- AArch64 KVM compile;
- AArch64 MSHV compile;
- x86_64 KVM VMM Clippy with warnings denied;
- regenerated one-file product diff;
- `cmp` equality against stored `candidate.patch`;
- matching `c3c0b19e...` SHA-256 receipt.

The temporary generator and one-shot freeze workflow were removed. Review artifact, applied artifact, tested artifact, and retained artifact are the same product bytes.

## Separate follow-ups

- Fieldwork #543: cache topology is always sourced from host CPU0 even when guest vCPUs are pinned elsewhere; heterogeneous-host truthfulness remains under investigation.
- Fieldwork #544: PPTT discards host L2/L3 sharing metadata even though the FDT path uses it; a separate conservative one-file experiment is in progress.

## Review recommendation

Prefer this identity-discovery candidate over the earlier guarded fixed-index recognizer. It removes the false semantic mapping while keeping unsupported guest cache models out of scope.

Reopen these product bytes only for guarded source change, a canonical competing fix, a valid representable topology rejected by the classifier, a project decision to model a currently omitted layout, or a supported backend/boot counterexample.

## External-contact state

`false; none occurred`.
