#!/usr/bin/env python3
from pathlib import Path

fdt = Path("arch/src/aarch64/fdt.rs").read_text()
cpu = Path("vmm/src/cpu.rs").read_text()

required_fdt = [
    "let cores_per_package = cores_per_die * dies_per_package;",
    "let package_id: u32 = cpu_id as u32 / cores_per_package as u32;",
    "while i < packages.into()",
    "threads_per_core * cores_per_package * package_idx",
    "+ threads_per_core * core_idx",
    "+ thread_idx;",
]
for needle in required_fdt:
    if needle not in fdt:
        raise RuntimeError(f"FDT discriminator anchor missing: {needle}")

required_pptt = [
    "if threads_per_core > 1",
    "for _thread_idx in 0..threads_per_core",
    "cpus += (cores_per_package * threads_per_core) as usize;",
]
for needle in required_pptt:
    if needle not in cpu:
        raise RuntimeError(f"PPTT discriminator anchor missing: {needle}")

threads_per_core = 2
cores_per_package = 2
packages = 2
logical_cpus = threads_per_core * cores_per_package * packages
current = [cpu_id // cores_per_package for cpu_id in range(logical_cpus)]
expected = [
    cpu_id // (threads_per_core * cores_per_package)
    for cpu_id in range(logical_cpus)
]

if current != [0, 0, 1, 1, 2, 2, 3, 3]:
    raise RuntimeError(f"unexpected current package map: {current}")
if expected != [0, 0, 0, 0, 1, 1, 1, 1]:
    raise RuntimeError(f"unexpected thread-aware package map: {expected}")
if not any(package_id >= packages for package_id in current):
    raise RuntimeError("current selector unexpectedly remains inside emitted package-L3 domain")

print("fdt-l3-smt: current-package-map=0,0,1,1,2,2,3,3")
print("fdt-l3-smt: expected-package-map=0,0,0,0,1,1,1,1")
print("fdt-l3-smt: emitted-l3-package-ids=0,1")
print("fdt-l3-smt: pptt-and-cpu-map-account-for-threads")
print("fdt-l3-smt-policy-mismatch-reproduced")
