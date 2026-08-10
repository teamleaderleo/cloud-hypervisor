#!/usr/bin/env python3
from pathlib import Path

fdt = Path("arch/src/aarch64/fdt.rs").read_text()
cpu = Path("vmm/src/cpu.rs").read_text()

if "if l2_cache_size != 0 && !l2_cache_shared {" not in fdt:
    raise RuntimeError("FDT L2 shared-cache policy changed")
if "if cache_exist && l3_cache_size != 0 && !l2_cache_shared && l3_cache_shared {" not in fdt:
    raise RuntimeError("FDT L3 shared-cache policy changed")

start = cpu.index("pub fn create_pptt(&self)")
end = cpu.index("#[cfg(all(target_arch = \"x86_64\", feature = \"guest_debug\"))]", start)
pptt = cpu[start:end]

required = [
    "l2_cache_shared,",
    "let expose_l2_l3 = !l2_cache_shared;",
    "let l3_cache_handle = if l3_cache_size != 0 && expose_l2_l3 {",
    "let l2_cache_handle = if l2_cache_size != 0 && expose_l2_l3 {",
    "l1d_cache_node = l1d_cache_node.next_level(l2_cache_handle);",
    "l1i_cache_node = l1i_cache_node.next_level(l2_cache_handle);",
]
for needle in required:
    if needle not in pptt:
        raise RuntimeError(f"PPTT candidate policy missing: {needle}")

print("shared-l2-fdt-policy: l1-only when host L2 is shared")
print("shared-l2-pptt-policy: l1-only when host L2 is shared")
print("shared-l2-candidate-policy-converged")
