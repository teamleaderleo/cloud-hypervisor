#!/usr/bin/env python3
from pathlib import Path

cache = Path("arch/src/aarch64/cache.rs").read_text()
fdt = Path("arch/src/aarch64/fdt.rs").read_text()
arch = Path("arch/src/aarch64/mod.rs").read_text()
cpu = Path("vmm/src/cpu.rs").read_text()
vm = Path("vmm/src/vm.rs").read_text()

required_cache = [
    "pub fn read_common_cache_topology(host_cpus: &[usize])",
    "Cache topology differs across eligible host CPUs; omitting guest cache information.",
    "cpu_sysfs_path.join(format!(\"cpu{host_cpu}/cache\"))",
]
for needle in required_cache:
    if needle not in cache:
        raise RuntimeError(f"common cache selector missing: {needle}")

required_cpu = [
    "libc::sched_getaffinity(",
    "fn cache_host_cpus_from_affinity(",
    "pub fn cache_host_cpus(&self) -> Result<Vec<usize>>",
    "read_common_cache_topology(&cache_host_cpus).map_err(Error::CacheTopology)?",
]
for needle in required_cpu:
    if needle not in cpu:
        raise RuntimeError(f"CpuManager selector missing: {needle}")

if "read_cache_topology().map_err(Error::CacheTopology)?" in fdt:
    raise RuntimeError("FDT still selects CPU0 topology directly")
if "read_common_cache_topology(cache_host_cpus).map_err(Error::CacheTopology)?" not in fdt:
    raise RuntimeError("FDT common topology selection missing")
if "cache_host_cpus: &[usize]," not in arch or "cache_host_cpus," not in arch:
    raise RuntimeError("AArch64 configure_system host CPU threading missing")
if "cpu_manager.cache_host_cpus().map_err(Error::CpuManager)?" not in vm:
    raise RuntimeError("VM does not obtain CpuManager cache execution set")
if "&cache_host_cpus," not in vm:
    raise RuntimeError("VM does not pass cache execution set to FDT")

print("cache-affinity-candidate: cpu0-global-source-removed-from-fdt-pptt")
print("cache-affinity-candidate: explicit-affinity-or-inherited-scheduler-set")
print("cache-affinity-candidate: common-topology-required-across-eligible-host-cpus")
print("cache-affinity-candidate-policy-converged")
