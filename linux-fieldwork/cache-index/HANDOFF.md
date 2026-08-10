# Linux Fieldwork handoff — AArch64 cacheinfo index portability

Updated: 2026-08-10
State: ACTIVE BASELINE PROBE
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Branch: `linux-fieldwork/cache-index-portability`
Canonical issue: none; internal portability question
Internal record: `teamleaderleo/linux-fieldwork#541`
Prerequisites: exact validated #8666 ACPI candidate and exact validated #8097 cache-runtime-error candidate

## TL;DR

Cloud Hypervisor currently maps AArch64 cache sysfs indices as if the index encoded the cache level/type: `index0=L1D`, `index1=L1I`, `index2=L2`, `index3=L3`.

Linux AArch64 enumerates cacheinfo indices by cache leaf instead. A separate cache level contributes DATA then INST leaves; a unified level contributes one leaf; firmware-described external levels can add more unified leaves. The fixed mapping therefore agrees with the common split-L1/unified-L2/L3 layout but can shift on other valid layouts.

The first probe is test-only. It stacks the exact #8666 and #8097 product candidates, commits those prerequisites locally, then injects synthetic cacheinfo identity fixtures into `arch/src/aarch64/cache.rs`. It does not change production code.

## First discriminators

1. Control: L1 Data at index0, L1 Instruction at index1, L2 Unified at index2, L3 Unified at index3. Current fixed mapping should agree with each sysfs `level`/`type` identity.
2. Unified-L1 counterexample: index0 L1 Unified, index1 L2 Unified, index2 L3 Unified. Current `l1_i_cache_size` should demonstrably receive the bytes of an entry whose sysfs identity says L2 Unified, while current `l2_cache_size` receives L3 Unified bytes.
3. Split-L2 counterexample: index0 L1 Data, index1 L1 Instruction, index2 L2 Data, index3 L2 Instruction, index4 L3 Unified. Current `l2_cache_size` treats L2 Data as a unified L2 and current `l3_cache_size` receives L2 Instruction bytes while the actual L3 sits at index4.

A passing counterexample test means the mismatch was observed and classified; it is not a candidate fix.

## Representation boundary

FDT currently emits separate L1 instruction/data nodes and unified L2/L3 nodes. PPTT likewise emits L1 Data, L1 Instruction, L2 Unified, and L3 Unified cache nodes. If the counterexamples hold, merely looking up indices by `level` and `type` is insufficient for topologies such as unified L1 or split L2.

The next design decision is therefore one of:

- introduce a cache-leaf representation that can express the host topology faithfully through both FDT and PPTT; or
- recognize only the currently representable split-L1/unified-L2/L3 pattern and omit passthrough with a warning for other valid host layouts instead of reporting incorrect cache identity.

Do not copy a unified L1 into both split-L1 fields without checking guest-visible FDT/PPTT semantics.

## Linux source evidence

Current `arch/arm64/kernel/cacheinfo.c` walks architectural levels and advances a cache-leaf index. `CACHE_TYPE_SEPARATE` contributes DATA then INST leaves; every other cache type contributes one leaf. External firmware-described levels can add unified leaves.

Historical Cloud Hypervisor PR #5505 included an Ampere Altra example with `index0`, `index1`, and `index2`, consistent with split L1 plus L2. That is a useful control topology, not a universal index contract.

## External-contact state

`false; none occurred`.
