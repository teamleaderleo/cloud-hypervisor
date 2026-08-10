#!/usr/bin/env python3
from pathlib import Path

path = Path("vmm/src/vm_config.rs")
source = path.read_text()
old = '            landlock.add_rule_with_access(Path::new("/sys/devices/system/cpu/cpu0/cache"), "r")?;\n'
new = '            landlock.add_rule_with_access(Path::new("/sys/devices/system/cpu"), "r")?;\n'
if old not in source:
    raise RuntimeError("AArch64 CPU0-only Landlock cache rule changed")
source = source.replace(old, new, 1)
path.write_text(source)
print("cache-affinity-landlock-parent-rule-applied")
