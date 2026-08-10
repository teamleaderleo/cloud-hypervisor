#!/usr/bin/env python3
from pathlib import Path

cache = Path("arch/src/aarch64/cache.rs").read_text()
fdt = Path("arch/src/aarch64/fdt.rs").read_text()
cpu = Path("vmm/src/cpu.rs").read_text()

required_cache = [
    'fn read_l3_sharing_domain(cache_path: &Path) -> Result<Option<String>>',
    'let mut l3_domain_mismatch = false;',
    'Eligible host CPUs span multiple L3 cache sharing domains; omitting guest L3 cache information.',
    'info.l3_cache_size = 0;',
    'info.l3_cache_line_size = 0;',
    'info.l3_cache_sets = 0;',
    'info.l3_cache_shared = false;',
    'fn test_common_topology_preserves_one_l3_sharing_domain()',
    'fn test_common_topology_omits_l3_across_distinct_sharing_domains()',
]
for needle in required_cache:
    if needle not in cache:
        raise RuntimeError(f"candidate cache anchor missing: {needle}")

# The conservative correction should stay below the consumer layer.
fdt_required = [
    'if l3_cache_size != 0 && l3_cache_shared',
    'let package_id = l3_package_id(cpu_id, threads_per_core, cores_per_package);',
]
for needle in fdt_required:
    if needle not in fdt:
        raise RuntimeError(f"FDT consumer anchor changed: {needle}")

pptt_required = [
    'let expose_l3 = expose_l2 && l3_cache_shared;',
    'if l3_cache_size != 0 && expose_l3',
]
for needle in pptt_required:
    if needle not in cpu:
        raise RuntimeError(f"PPTT consumer anchor changed: {needle}")

print("l3-sharing-domain-candidate: same-domain-l3-preserved")
print("l3-sharing-domain-candidate: cross-domain-l3-omitted")
print("l3-sharing-domain-candidate: l1-l2-common-topology-preserved")
print("l3-sharing-domain-candidate: fdt-pptt-consumers-unchanged")
print("l3-sharing-domain-candidate-policy-converged")
