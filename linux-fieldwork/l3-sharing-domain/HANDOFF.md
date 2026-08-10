# Linux Fieldwork handoff — AArch64 L3 sharing-domain fidelity

Updated: 2026-08-10
State: ACTIVE BASELINE PROBE
Tracker: `teamleaderleo/linux-fieldwork#548`
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Prerequisites: exact frozen #543 v2, #546, and #547 candidates
External contact: false; none occurred

## Question

Can the common cache selector mistake two distinct host L3 sharing domains for one common shared L3 when their geometry is identical?

## Concrete host class

Arm's Neoverse N1 Edge reference design has 8 N1 CPUs arranged as quad-core clusters with a 2 MB shared L3 per cluster and GIC-600. That is a concrete two-domain/equal-geometry host class inside Cloud Hypervisor's documented GICv3 AArch64 prerequisite envelope.

## Baseline discriminator

Synthetic eligible host CPUs 0..7:

- private L2 on each CPU;
- identical 2 MB L3 geometry everywhere;
- CPUs 0..3 L3 `shared_cpu_list=0-3`;
- CPUs 4..7 L3 `shared_cpu_list=4-7`.

The current common selector compares `CacheTopologyInfo` equality. That model carries L3 geometry and `l3_cache_shared`, but no shared-domain identity. The executable test asks whether CPUs from both host domains are therefore accepted as one common topology with nonzero shared L3.

The source guard separately verifies that explicit guest topology `1:8:1:1` creates one guest package and that frozen FDT/PPTT policy exposes one package-level L3 whenever the common topology reports a shared L3.

## Candidate direction if reproduced

Preserve common L1/L2 geometry and conservatively omit L3 when eligible host CPUs span multiple Linux L3 sharing domains. Preserve L3 when all eligible CPUs report one domain. A richer per-package host-domain mapping remains outside the first correction.
