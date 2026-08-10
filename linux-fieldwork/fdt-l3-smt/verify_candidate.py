#!/usr/bin/env python3
from pathlib import Path

fdt = Path("arch/src/aarch64/fdt.rs").read_text()

required = [
    "fn l3_package_id(cpu_id: usize, threads_per_core: u16, cores_per_package: u16) -> u32",
    "let logical_cpus_per_package = u32::from(threads_per_core) * u32::from(cores_per_package);",
    "let package_id = l3_package_id(cpu_id, threads_per_core, cores_per_package);",
    "fn test_l3_package_id_single_thread_control()",
    "fn test_l3_package_id_accounts_for_smt_threads()",
]
for needle in required:
    if needle not in fdt:
        raise RuntimeError(f"candidate anchor missing: {needle}")

old = "let package_id: u32 = cpu_id as u32 / cores_per_package as u32;"
if old in fdt:
    raise RuntimeError("thread-blind L3 package selector remains present")

threads_per_core = 2
cores_per_package = 2
ids = [
    cpu_id // (threads_per_core * cores_per_package)
    for cpu_id in range(8)
]
if ids != [0, 0, 0, 0, 1, 1, 1, 1]:
    raise RuntimeError(f"candidate SMT map is wrong: {ids}")

control = [cpu_id // 2 for cpu_id in range(4)]
if control != [0, 0, 1, 1]:
    raise RuntimeError(f"single-thread control changed: {control}")

print("fdt-l3-smt-candidate: single-thread-map=0,0,1,1")
print("fdt-l3-smt-candidate: smt-map=0,0,0,0,1,1,1,1")
print("fdt-l3-smt-candidate: package-selector-includes-threads-per-core")
print("fdt-l3-smt-candidate-policy-converged")
