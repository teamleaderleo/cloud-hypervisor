#!/usr/bin/env python3
from pathlib import Path

cache = Path("arch/src/aarch64/cache.rs").read_text()
fdt = Path("arch/src/aarch64/fdt.rs").read_text()
cpu = Path("vmm/src/cpu.rs").read_text()

cache_anchors = [
    "pub l3_cache_shared: bool,",
    "Some(expected) if expected == current => {}",
    "read_common_cache_topology_from",
]
for needle in cache_anchors:
    if needle not in cache:
        raise RuntimeError(f"cache common-topology anchor missing: {needle}")

# The common value has a sharing boolean, with no persisted L3 shared_cpu_list/domain identity.
if "l3_shared_cpu_list" in cache or "l3_cache_domain" in cache:
    raise RuntimeError("L3 sharing-domain identity unexpectedly exists in cache model")

fdt_anchors = [
    "if l3_cache_size != 0 && l3_cache_shared",
    "while i < packages.into()",
    "let package_id = l3_package_id(cpu_id, threads_per_core, cores_per_package);",
]
for needle in fdt_anchors:
    if needle not in fdt:
        raise RuntimeError(f"FDT L3 package anchor missing: {needle}")

pptt_anchors = [
    "let expose_l3 = expose_l2 && l3_cache_shared;",
    "if l3_cache_size != 0 && expose_l3",
    "cluster_hierarchy_node = cluster_hierarchy_node.add_cache(l3_cache_handle);",
]
for needle in pptt_anchors:
    if needle not in cpu:
        raise RuntimeError(f"PPTT L3 package anchor missing: {needle}")

# Explicit guest topology 1:8:1:1 is one package, so both interfaces expose one
# package-level L3 whenever the common topology says shared L3 is available.
threads_per_core = 1
cores_per_die = 8
dies_per_package = 1
packages = 1
logical_cpus = threads_per_core * cores_per_die * dies_per_package * packages
if logical_cpus != 8 or packages != 1:
    raise RuntimeError("unexpected guest topology arithmetic")

print("l3-sharing-domain: common-selector-compares-geometry-and-sharing-booleans")
print("l3-sharing-domain: no-l3-domain-identity-in-cache-topology")
print("l3-sharing-domain: guest-topology=1:8:1:1-one-package")
print("l3-sharing-domain: fdt-pptt-expose-one-package-shared-l3")
print("l3-sharing-domain-policy-gap-reproduced")
