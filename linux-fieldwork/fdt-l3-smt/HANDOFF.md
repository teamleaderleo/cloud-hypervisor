# Linux Fieldwork handoff — AArch64 FDT L3 package mapping with SMT

Updated: 2026-08-10
State: ACTIVE BASELINE PROBE
Tracker: `teamleaderleo/linux-fieldwork#546`
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
External contact: false; none occurred

## Question

Does AArch64 FDT select the package-level L3 cache handle with a divisor that ignores `threads_per_core`?

## Current canonical behavior

FDT computes:

- `cores_per_package = cores_per_die * dies_per_package`;
- `package_id = cpu_id / cores_per_package`;
- emits exactly `packages` L3 cache nodes.

The same FDT CPU map computes logical CPU IDs with `threads_per_core` included. PPTT also advances package CPU accounting by `cores_per_package * threads_per_core` and explicitly emits thread leaf nodes when SMT is configured.

## Discriminator

Topology `2:2:1:2` has 8 logical CPUs, 4 per package.

Expected package IDs: `0,0,0,0,1,1,1,1`.
Current FDT package selector: `0,0,1,1,2,2,3,3`.
Emitted package-L3 IDs: `0,1`.

The baseline probe stacks the exact validated cache prerequisite chain through #543, commits those bytes locally, then adds one test-only module to `arch/src/aarch64/fdt.rs`. A source discriminator separately guards the production formula, emitted L3 count, FDT cpu-map arithmetic, and PPTT thread-aware accounting.

## Promotion rule

A green baseline makes this a reproduced FDT topology bug. The smallest likely product correction is to divide `cpu_id` by `threads_per_core * cores_per_package` for package-level L3 selection, then test single-thread and SMT topologies and run AArch64/x86 compatibility gates before freezing exact bytes.
