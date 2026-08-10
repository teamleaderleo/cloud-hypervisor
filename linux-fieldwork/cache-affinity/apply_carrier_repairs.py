#!/usr/bin/env python3
from pathlib import Path

cpu_file = Path("vmm/src/cpu.rs")
cpu = cpu_file.read_text()
old_import = "use std::mem::zeroed;"
new_import = "use std::mem::{self, zeroed};"
if old_import not in cpu:
    raise RuntimeError("CpuManager mem import anchor changed")
cpu_file.write_text(cpu.replace(old_import, new_import, 1))

vm_file = Path("vmm/src/vm.rs")
vm = vm_file.read_text()
old_call = '''            "console=tty0",
            &[0],
            None,
            &dev_info,
'''
new_call = '''            "console=tty0",
            &[0],
            None,
            &[0],
            &dev_info,
'''
if old_call not in vm:
    raise RuntimeError("direct create_fdt test call anchor changed")
vm_file.write_text(vm.replace(old_call, new_call, 1))
