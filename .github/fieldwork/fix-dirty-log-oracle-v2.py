from pathlib import Path

path = Path("vmm/src/memory_manager.rs")
text = path.read_text()
old = "gpa: 0x403f_0000,"
new = "gpa: 0x400f_c000,"
if text.count(old) != 1:
    raise SystemExit(f"expected one stale cross-word oracle, found {text.count(old)}")
path.write_text(text.replace(old, new, 1))
