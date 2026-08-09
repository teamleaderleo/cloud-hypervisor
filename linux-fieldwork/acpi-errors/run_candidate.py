#!/usr/bin/env python3
import subprocess
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
    """        #[cfg(feature = "tdx")]
        if self.config.lock().unwrap().is_tdx_enabled() {
            return None;
        }""",
    """        #[cfg(feature = "tdx")]
        if self.config.lock().unwrap().is_tdx_enabled() {
            return Ok(None);
        }""",
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

old = '''    let interrupt_controller = device_manager
        .get_interrupt_controller()
        .ok_or(AcpiError::MissingInterruptController)?;
    let vgic = interrupt_controller
        .lock()
        .map_err(poisoned_lock)?
        .get_vgic()
        .ok_or(AcpiError::MissingVgic)?;'''
new = '''    let vgic = {
        let interrupt_controller = device_manager
            .get_interrupt_controller()
            .ok_or(AcpiError::MissingInterruptController)?;
        let interrupt_controller = interrupt_controller
            .lock()
            .map_err(poisoned_lock)?;
        interrupt_controller
            .get_vgic()
            .ok_or(AcpiError::MissingVgic)?
    };'''
if script.count(old) != 1:
    raise RuntimeError("failed to scope aarch64 interrupt-controller lookup")
script = script.replace(old, new, 1)

exec(compile(script, str(script_path), "exec"), {"__name__": "__main__"})
subprocess.run(["cargo", "fmt", "--all"], check=True)
print("acpi-error-candidate-formatted")
