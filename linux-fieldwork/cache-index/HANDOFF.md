# Linux Fieldwork handoff — AArch64 cacheinfo index portability

Updated: 2026-08-10
State: STRONG CANDIDATE / CURRENT BOUNDARY SATURATED
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Branch: `linux-fieldwork/cache-index-portability`
Canonical issue: none; internal portability correctness question
Internal record: `teamleaderleo/linux-fieldwork#541`
Prerequisites: exact validated #8666 ACPI candidate and exact validated #8097 cache-runtime-error candidate

## TL;DR

Cloud Hypervisor currently maps AArch64 cache sysfs indices as if the index encoded cache identity: `index0=L1D`, `index1=L1I`, `index2=L2`, `index3=L3`. Linux AArch64 enumerates cacheinfo entries by cache leaf, so unified or differently split levels can shift those indices.

A test-only baseline proved two concrete misidentifications on valid Linux cacheinfo layouts. The conservative one-file candidate now validates each leaf's exported `level` and `type` before filling the existing fixed guest model. The common split-L1/unified-L2/L3 layout is preserved. Valid layouts the current FDT/PPTT model cannot faithfully represent are omitted with one warning instead of being reported as the wrong cache identity.

## Reproduced baseline

Baseline head: `06f6343cbf3762095b8d808aa8b6a09a30537414`
Focused run/job: `31353310424` / `93348082267` — success
Artifact: `9049729478`
Artifact digest: `sha256:4e922bac17707e84b836e195d14b7a1253107e56b50b4451d2a6a2b5e2f28658`
Probe diff digest: `sha256:a9312f91ae131dab9a00b12fa492f2cc00549b7894948ee7a0fb17285b631365`

The test-only AArch64 probe executed under qemu-user and proved:

1. split L1 Data/Instruction + unified L2/L3 agrees with the current mapping;
2. unified L1 makes current `l1_i_cache_size` consume an L2 Unified leaf and current L2 consume L3 bytes;
3. split L2 makes current L3 consume the L2 Instruction leaf while the actual L3 sits at `index4`.

## Linux identity contract

Current Linux arm64 cacheinfo enumerates leaves in discovery order:

- a separate cache level contributes DATA then INST leaves;
- a unified/data-only/instruction-only level contributes one leaf;
- firmware-described external levels can add unified leaves.

Linux exports each leaf's `level` and `type`; the type strings are `Data`, `Instruction`, and `Unified`. Therefore `indexN` identifies the Nth cache leaf and does not itself encode architectural cache identity.

Historical Cloud Hypervisor PR #5505 showed an Ampere Altra host with `index0`, `index1`, and `index2`, consistent with the candidate's preserved happy path.

## Guest representation boundary

The current consumers model only:

- FDT: split L1 instruction/data plus unified L2/L3;
- PPTT: L1 Data, L1 Instruction, L2 Unified, L3 Unified.

A generic `(level,type)` lookup alone cannot faithfully encode unified L1, split L2, L4+, and similar valid host layouts. The candidate therefore treats representability as an explicit boundary.

## Exact candidate policy

`arch/src/aarch64/cache.rs` only:

1. no cache leaves -> preserve existing empty/default behavior;
2. require `index0 = L1 Data` and `index1 = L1 Instruction` for passthrough;
3. optional `index2` must be L2 Unified;
4. optional `index3` must be L3 Unified;
5. missing optional trailing levels remain supported;
6. gaps, identity mismatches, unified L1, split L2, or `index4+` -> one warning and `Ok(None)`;
7. malformed numeric identity/properties and real I/O failures retain the typed #8097 error path.

Both FDT and PPTT already consume `None` as cache-less behavior, so the product change requires no consumer edits.

## Exact product representation

Validated product carrier head: `7713a59e21c48262843da100087454dae3c0772d`
Stored patch: `linux-fieldwork/cache-index/candidate.patch`
Patch Git blob: `4550e55faba24d0c1ffc9f7be7a11596d5866b8a`
Stored/generated patch digest: `sha256:d54bf458a609eddaf5b7d6de350fb2c1d770b61e254d494df58c6dd43a8be074`

Final focused run/job: `31353819973` / `93349565675` — success
Artifact: `9049940543`
Artifact digest: `sha256:30312c669c81beac2c59cb4b3ce353d94a019934ac550e033095be432c412a00`

Product scope: one file, `arch/src/aarch64/cache.rs`, +177/-0. Most additions are identity helpers and fixtures.

## Final focused evidence

Passed on the exact stored candidate bytes after exact #8666/#8097 prerequisite application:

- canonical source blob guards;
- exact prerequisite patch identities;
- `git apply --check` for the stored candidate;
- exact one-file product scope and `git diff --check`;
- nightly rustfmt;
- all 11 AArch64 cache tests under qemu-user;
- immediate clean rerun;
- focused AArch64 Clippy with warnings denied;
- AArch64 KVM compile;
- AArch64 MSHV compile;
- x86_64 KVM regression compile;
- regenerated one-file diff;
- automatic `cmp` against stored `candidate.patch`;
- matching stored/generated SHA-256 receipt.

The canonical `main` cache/FDT/CPU blobs were refreshed after validation and remain identical to the guarded source generation.

## Review recommendation

Keep the conservative omission boundary for this patch. It fixes incorrect guest cache descriptions without widening FDT/PPTT into a generic cache hierarchy model.

A later generic model can be evaluated separately if faithful passthrough for unified-L1, split-L2, L4+, or heterogeneous cache layouts becomes a project goal.

Reopen these product bytes for a guarded source change, a canonical competing fix, a valid representable topology rejected by the recognizer, an unsupported layout that should be modeled rather than omitted, or a supported backend/boot counterexample.

## External-contact state

`false; none occurred`.
