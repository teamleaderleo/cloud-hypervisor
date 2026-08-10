#!/usr/bin/env python3
from pathlib import Path

config = Path("vmm/src/config.rs").read_text()
cpu = Path("vmm/src/cpu.rs").read_text()
fdt = Path("arch/src/aarch64/fdt.rs").read_text()
hotplug = Path("docs/hotplug.md").read_text()

config_anchors = [
    "ValidationError::CpusMaxLowerThanBoot",
    "ValidationError::CpuTopologyCount",
    "still_valid_config.cpus.max_vcpus = 4;",
    "still_valid_config.cpus.boot_vcpus = 2;",
    "still_valid_config.validate().unwrap();",
]
for needle in config_anchors:
    if needle not in config:
        raise RuntimeError(f"config validation discriminator anchor missing: {needle}")

cpu_anchors = [
    "self.create_vcpus(self.boot_vcpus(), snapshot)",
    "pub fn get_mpidrs(&self) -> Vec<u64>",
    ".iter()\n            .map(|cpu| cpu.lock().unwrap().get_mpidr())",
]
for needle in cpu_anchors:
    if needle not in cpu:
        raise RuntimeError(f"CpuManager boot/MPIDR anchor missing: {needle}")

fdt_anchors = [
    "let num_cpus = vcpu_mpidr.len();",
    "let max_cpus: u32 =",
    "for (cpu_id, mpidr) in vcpu_mpidr.iter().enumerate().take(num_cpus)",
    "for package_idx in 0..packages",
    "for core_idx in 0..cores_per_package",
    "for thread_idx in 0..threads_per_core",
    "fdt.property_u32(\"cpu\", cpu_idx as u32 + FIRST_VCPU_PHANDLE)?;",
]
for needle in fdt_anchors:
    if needle not in fdt:
        raise RuntimeError(f"FDT CPU-map anchor missing: {needle}")

if "supports hot plugging of CPUs devices (x86 only)" not in hotplug:
    raise RuntimeError("documented CPU hotplug architecture boundary changed")

boot_vcpus = 2
max_vcpus = 4
cpu_nodes = list(range(boot_vcpus))
cpu_map = list(range(max_vcpus))
dangling = [cpu_id for cpu_id in cpu_map if cpu_id >= boot_vcpus]

if cpu_nodes != [0, 1]:
    raise RuntimeError(f"unexpected emitted CPU domain: {cpu_nodes}")
if cpu_map != [0, 1, 2, 3]:
    raise RuntimeError(f"unexpected topology CPU-map domain: {cpu_map}")
if dangling != [2, 3]:
    raise RuntimeError(f"unexpected dangling CPU-map IDs: {dangling}")

print("aarch64-max-boot: accepted-config=boot2-max4-topology1:4:1:1")
print("aarch64-max-boot: emitted-cpu-node-ids=0,1")
print("aarch64-max-boot: cpu-map-ids=0,1,2,3")
print("aarch64-max-boot: dangling-cpu-map-ids=2,3")
print("aarch64-max-boot: documented-cpu-hotplug=x86-only")
print("aarch64-max-boot-policy-mismatch-reproduced")
