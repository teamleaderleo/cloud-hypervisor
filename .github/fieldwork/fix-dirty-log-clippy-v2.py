from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected one match for {old!r}, found {text.count(old)}")
    p.write_text(text.replace(old, new, 1))


replace_once(
    "hypervisor/src/kvm/mod.rs",
    "use std::collections::HashMap;\n",
    "use std::collections::HashMap;\nuse std::num::NonZeroU64;\n",
)
replace_once(
    "hypervisor/src/kvm/mod.rs",
    ".and_then(std::num::NonZeroU64::new)",
    ".and_then(NonZeroU64::new)",
)

replace_once(
    "hypervisor/src/mshv/mod.rs",
    "use std::collections::HashMap;\n",
    "use std::collections::HashMap;\nuse std::num::NonZeroU64;\n",
)
replace_once(
    "hypervisor/src/mshv/mod.rs",
    "bytes_per_bit: std::num::NonZeroU64::new(1u64 << PAGE_SHIFT).unwrap(),",
    "bytes_per_bit: NonZeroU64::new(1u64 << PAGE_SHIFT).unwrap(),",
)

replace_once(
    "vmm/src/memory_manager.rs",
    "    use hypervisor::DirtyLog;\n\n    use super::dirty_bitmap_to_range_table;\n",
    "    use hypervisor::DirtyLog;\n    use vm_migration::protocol::MemoryRange;\n\n    use super::dirty_bitmap_to_range_table;\n",
)

path = Path("vmm/src/memory_manager.rs")
text = path.read_text()
old = "&[vm_migration::protocol::MemoryRange {"
if text.count(old) != 2:
    raise SystemExit(f"expected two dirty-log test MemoryRange literals, found {text.count(old)}")
path.write_text(text.replace(old, "&[MemoryRange {"))
