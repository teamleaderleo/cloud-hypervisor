#!/usr/bin/env python3
from pathlib import Path

fdt = Path("arch/src/aarch64/fdt.rs").read_text()
cpu = Path("vmm/src/cpu.rs").read_text()

fdt_l2 = "if l2_cache_size != 0 && !l2_cache_shared {"
fdt_l3 = "if cache_exist && l3_cache_size != 0 && !l2_cache_shared && l3_cache_shared {"
if fdt_l2 not in fdt:
    raise RuntimeError("FDT shared-L2 omission guard changed")
if fdt_l3 not in fdt:
    raise RuntimeError("FDT shared-L2/L3 omission guard changed")

start = cpu.index("pub fn create_pptt(&self)")
end = cpu.index("#[cfg(all(target_arch = \"x86_64\", feature = \"guest_debug\"))]", start)
pptt = cpu[start:end]

if "l2_cache_shared" in pptt:
    raise RuntimeError("PPTT now consumes l2_cache_shared; baseline assumption changed")
if "let l2_cache_handle = if l2_cache_size != 0 {" not in pptt:
    raise RuntimeError("PPTT L2 creation condition changed")
if "l1d_cache_node = l1d_cache_node.next_level(l2_cache_handle);" not in pptt:
    raise RuntimeError("PPTT L1D to L2 relationship changed")
if "l1i_cache_node = l1i_cache_node.next_level(l2_cache_handle);" not in pptt:
    raise RuntimeError("PPTT L1I to L2 relationship changed")
if "thread_hierarchy_node.add_cache(l1d_cache_handle);" not in pptt:
    raise RuntimeError("PPTT processor-private L1D attachment changed")
if "thread_hierarchy_node.add_cache(l1i_cache_handle);" not in pptt:
    raise RuntimeError("PPTT processor-private L1I attachment changed")

print("shared-l2-fdt-policy: omit-l2-and-l3")
print("shared-l2-pptt-policy: ignores-sharing-flag-and-keeps-l2-private-chain")
