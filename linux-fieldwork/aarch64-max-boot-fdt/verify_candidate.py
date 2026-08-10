#!/usr/bin/env python3
from pathlib import Path

config = Path("vmm/src/config.rs").read_text()
fdt = Path("arch/src/aarch64/fdt.rs").read_text()

required = [
    'Aarch64CpuHotplugUnsupported,',
    '#[error("CPU hotplug is not supported on AArch64")]',
    'if self.cpus.max_vcpus != self.cpus.boot_vcpus {',
    'return Err(ValidationError::Aarch64CpuHotplugUnsupported);',
    'Err(ValidationError::Aarch64CpuHotplugUnsupported)',
    'still_valid_config.cpus.max_vcpus = 4;',
    'still_valid_config.cpus.boot_vcpus = 4;',
]
for needle in required:
    if needle not in config:
        raise RuntimeError(f"candidate validation anchor missing: {needle}")

# Existing lower-than-boot diagnostic stays first and keeps its historical meaning.
lower = config.index('if self.cpus.max_vcpus < self.cpus.boot_vcpus {')
aarch64 = config.index('if self.cpus.max_vcpus != self.cpus.boot_vcpus {')
if lower >= aarch64:
    raise RuntimeError("AArch64 hotplug rejection precedes the existing max<boot diagnostic")

# Product boundary should resolve the accepted-config failure before FDT needs
# any special partial-topology behavior.
if 'max_boot_cpu_map_tests' in fdt:
    raise RuntimeError("test-only FDT baseline probe leaked into product candidate")

print("aarch64-max-boot-candidate: max-lower-than-boot-diagnostic-preserved")
print("aarch64-max-boot-candidate: max-greater-than-boot-rejected-on-aarch64")
print("aarch64-max-boot-candidate: boot-equals-max-topology-control-preserved")
print("aarch64-max-boot-candidate: no-fdt-partial-topology-special-case")
print("aarch64-max-boot-candidate-policy-converged")
