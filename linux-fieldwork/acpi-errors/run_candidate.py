#!/usr/bin/env python3
from pathlib import Path

script_path = Path(__file__).with_name("apply_candidate.py")
script = script_path.read_text()

old = '''vm = replace_once(
    vm,
    '            return None;\\n',
    '            return Ok(None);\\n',
    "TDX no-op return",
)
'''
new = '''vm = replace_once(
    vm,
    ''' + '"""' + '''        #[cfg(feature = "tdx")]
        if self.config.lock().unwrap().is_tdx_enabled() {
            return None;
        }''' + '"""' + ''',
    ''' + '"""' + '''        #[cfg(feature = "tdx")]
        if self.config.lock().unwrap().is_tdx_enabled() {
            return Ok(None);
        }''' + '"""' + ''',
    "TDX no-op return",
)
'''
if script.count(old) != 1:
    raise RuntimeError("failed to scope TDX no-op replacement")
script = script.replace(old, new, 1)

old = "vm = vm.replace('self.create_acpi_tables()\\n', 'self.create_acpi_tables()?\\n')\n"
new = '''vm = vm.replace("self.create_acpi_tables();", "self.create_acpi_tables()?;")
vm = vm.replace("self.create_acpi_tables()\\n", "self.create_acpi_tables()?\\n")
'''
if script.count(old) != 1:
    raise RuntimeError("failed to repair ACPI call-site propagation")
script = script.replace(old, new, 1)

exec(compile(script, str(script_path), "exec"), {"__name__": "__main__"})
