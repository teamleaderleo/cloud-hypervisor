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
