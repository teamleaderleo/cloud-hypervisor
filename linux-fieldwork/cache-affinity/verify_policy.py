#!/usr/bin/env python3
from pathlib import Path

cache = Path("arch/src/aarch64/cache.rs").read_text()
cpu = Path("vmm/src/cpu.rs").read_text()
fdt = Path("arch/src/aarch64/fdt.rs").read_text()

if "/sys/devices/system/cpu/cpu0/cache" not in cache:
    raise RuntimeError("cache reader no longer has a cpu0 source root")
if "read_cache_topology_from(Path::new(CACHE_SYSFS_PATH))" not in cache:
    raise RuntimeError("cache reader selection path changed")
if "affinity: BTreeMap<u32, Box<[usize]>>" not in cpu:
    raise RuntimeError("CpuManager affinity ownership changed")
if "let cpuset = self.affinity.get(&vcpu_id).map(|host_cpus|" not in cpu:
    raise RuntimeError("vCPU affinity application path changed")
if "let cache_info = read_cache_topology()?;" not in fdt:
    raise RuntimeError("FDT cache selection path changed")

pptt_start = cpu.index("pub fn create_pptt(&self)")
pptt_end = cpu.index("#[cfg(all(target_arch = \"x86_64\", feature = \"guest_debug\"))]", pptt_start)
pptt = cpu[pptt_start:pptt_end]
if "let cache_info = read_cache_topology().map_err(Error::CacheTopology)?;" not in pptt:
    raise RuntimeError("PPTT cache selection path changed")

# A legal configured execution set can exclude host CPU0 entirely.
affinity = {0: (4, 5), 1: (4, 5)}
eligible = {host_cpu for host_cpus in affinity.values() for host_cpu in host_cpus}
if 0 in eligible:
    raise RuntimeError("baseline affinity unexpectedly includes CPU0")

print("cache-source-policy: cpu0-only")
print(f"vcpu-affinity-policy: eligible-host-cpus={sorted(eligible)}")
print("fdt-cache-policy: reads-global-cpu0-topology")
print("pptt-cache-policy: reads-global-cpu0-topology")
print("cache-affinity-baseline: cpu0-can-be-outside-vcpu-execution-set")
