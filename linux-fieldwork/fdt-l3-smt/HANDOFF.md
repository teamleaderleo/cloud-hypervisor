# Linux Fieldwork handoff — AArch64 FDT L3 package mapping with SMT

Updated: 2026-08-10
State: STRONG / FROZEN INTERNAL CANDIDATE
Tracker: `teamleaderleo/linux-fieldwork#546`
Carrier: `teamleaderleo/cloud-hypervisor#11`
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Prerequisite: exact frozen cache stack through #543
External contact: false; none occurred

## Reproduced defect

AArch64 FDT selected package-level L3 cache handles with:

`package_id = cpu_id / cores_per_package`

while `cpu_id` counts logical vCPUs including threads. Logical CPUs per package are:

`threads_per_core * cores_per_package`.

For topology `2:2:1:2`, current FDT mapped CPU0..7 to `0,0,1,1,2,2,3,3` while it emitted only package-L3 nodes `0,1`. The thread-aware mapping is `0,0,0,0,1,1,1,1`.

The FDT cpu-map and PPTT package accounting already include `threads_per_core`, making the L3 selector the outlier.

Baseline run/job: `31359642015` / `93365791648` — success
Baseline artifact: `9051884020`
Baseline artifact digest: `sha256:afd39f113edea0244eb24d88cf55e4149ba99f1011695b3b68d062f02f72992e`

## Frozen candidate

Product scope: exactly `arch/src/aarch64/fdt.rs`.

The candidate adds `l3_package_id()` and computes logical CPUs per package as:

`threads_per_core * cores_per_package`.

Controls:

- single-thread grouping remains `0,0,1,1`;
- topology `2:2:1:2` yields `0,0,0,0,1,1,1,1`.

Exact stored patch:

- path: `linux-fieldwork/fdt-l3-smt/candidate.patch`
- Git blob: `239a2a7c9a7fe7031a594605f3801f2b06c53fa2`
- SHA-256: `146c6af0807ab5a7b8af98958a6b9836af9d44075711ef6d73e62621d14b3665`
- retained patch length: 46 lines

## Validation receipts

First fully-green product matrix:

- run/job: `31359943002` / `93366703731`
- artifact: `9052026525`
- artifact digest: `sha256:76e4cc63c68e01e49ff5174b60775db85fedd681709027dc1bfde22ad42f3d17`

Final exact-byte convergence:

- run/job: `31360196617` / `93367426980`
- artifact: `9052109789`
- artifact digest: `sha256:b1cbd705c4e789db12c122f5b482366cd0568ce6c65a086dfe9eef34e02b6db2`

The final read-only run applied only the exact stored candidate after the frozen #543 stack, passed one-file scope, policy guards, both AArch64 mapping tests, nightly formatting, AArch64 Clippy, AArch64 KVM/MSHV, x86_64 KVM, and literal stored/generated `cmp` plus both SHA-256 checks.

## Reopen conditions

Reopen if relevant canonical FDT topology/cache bytes move, guest topology semantics change, or a competing correction appears upstream.
