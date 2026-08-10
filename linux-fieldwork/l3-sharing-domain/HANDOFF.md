# Linux Fieldwork handoff — AArch64 L3 sharing-domain fidelity

Updated: 2026-08-10
State: STRONG / FROZEN INTERNAL CANDIDATE
Tracker: `teamleaderleo/linux-fieldwork#548`
Carrier: `teamleaderleo/cloud-hypervisor#13`
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Prerequisites: exact frozen #543 v2, #546, and #547 candidates
External contact: false; none occurred

## Reproduced defect

The common AArch64 cache selector compared `CacheTopologyInfo` equality, which carried L3 geometry and `l3_cache_shared` but no actual Linux L3 sharing-domain identity. Eligible CPUs from two distinct equal-geometry L3 domains could therefore be accepted as one common shared L3.

Synthetic discriminator:

- eligible CPUs 0..7;
- private L2 per CPU;
- identical L1/L2/L3 geometry;
- CPUs 0..3 L3 `shared_cpu_list=0-3`;
- CPUs 4..7 L3 `shared_cpu_list=4-7`.

The baseline returned a nonzero 2 MB shared L3 across all eight CPUs. A one-package guest would then expose one package-level L3 through FDT/PPTT.

Baseline run/job: `31363925142` / `93378191993` — success
Baseline artifact: `9053425721`
Baseline artifact digest: `sha256:be709614c72bc02833aa8d489f13d7f0c5b78b0bc21ea25c54fa40345ef438b0`

## Frozen candidate

Product scope: exactly `arch/src/aarch64/cache.rs`.

The candidate reads the Linux L3 `shared_cpu_list` for shared L3 roots. It preserves L3 when every eligible shared-L3 CPU reports one common domain. Differing or unavailable domain identity marks L3 unsafe; every CPU's geometry is still compared. On mismatch, common L1/L2 remain while L3 size/line/sets are zeroed and `l3_cache_shared=false`. FDT/PPTT consumer code stays unchanged and naturally omits zeroed L3.

Linux exposes `shared_cpu_list` from the cache leaf's kernel sharing cpumask, so the comparison follows Linux's cache-domain representation.

Exact stored patch:

- path: `linux-fieldwork/l3-sharing-domain/candidate.patch`
- Git blob: `c3ac26a31a302bfd01962aa0d33f6a44e58da908`
- SHA-256: `e9c8f5fb20be1ef7c4a63c95c8e098059fa92f3bd1b2bb0a87cedcf84aac067c`
- product diff: 83 additions / 0 deletions

## Validation receipts

First full product matrix:

- run/job: `31364340377` / `93379417208`
- artifact: `9053619564`
- artifact digest: `sha256:9e5d939c040fbd28c1a424aa3c199c88e9706e729bb6642293deb7909fa0219c`

Final exact-byte convergence:

- run/job: `31364741631` / `93380621688`
- artifact: `9053751736`
- artifact digest: `sha256:75755f5a9de79042d1273180a013b53565b3561d21187bc80c628610aabc274c`

The final read-only run applied only the exact stored candidate after exact frozen prerequisites, passed one-file scope, same-domain L3 preservation, cross-domain L3 omission with L1/L2 preservation, all AArch64 cache regressions, nightly formatting, AArch64 `arch` Clippy, KVM/MSHV, x86 KVM, and literal stored/generated `cmp` plus both SHA-256 checks.

## Reopen conditions

Reopen if Linux cache-domain sysfs semantics change, relevant canonical cache bytes move, or a richer guest-to-host cache-domain mapping appears upstream.
