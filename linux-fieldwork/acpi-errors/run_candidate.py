#!/usr/bin/env python3
import subprocess
from pathlib import Path

script_path = Path(__file__).with_name("apply_candidate.py")
script = script_path.read_text()


def rewrite_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


# Scope replacements to the exact VM helper call sites.
script = rewrite_once(
    script,
    '''vm = replace_once(
    vm,
    '            return None;\\n',
    '            return Ok(None);\\n',
    "TDX no-op return",
)
''',
    '''vm = replace_once(
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
''',
    "scope TDX no-op replacement",
)
script = rewrite_once(
    script,
    "vm = vm.replace('self.create_acpi_tables()\\n', 'self.create_acpi_tables()?\\n')\n",
    '''vm = vm.replace("self.create_acpi_tables();", "self.create_acpi_tables()?;")
vm = vm.replace("self.create_acpi_tables()\\n", "self.create_acpi_tables()?\\n")
''',
    "repair ACPI call-site propagation",
)

# Keep programmer/layout invariants out of the runtime ACPI error type.
for variant in (
    '''    #[error("ACPI table layout is invalid")]
    InvalidTableLayout,

''',
    '''    #[error("ACPI interrupt controller is missing")]
    MissingInterruptController,

''',
    '''    #[error("ACPI VGIC is missing")]
    MissingVgic,

''',
    '''    #[error("PCI segment {0} cannot be represented in the IORT table")]
    InvalidIortPciSegment(u16),
''',
):
    script = rewrite_once(script, variant, "", "remove invariant ACPI error variant")

start_marker = "# IORT has configuration-sensitive validation and must be fallible.\n"
end_marker = "# Core table layout becomes fallible.\n"
if script.count(start_marker) != 1 or script.count(end_marker) != 1:
    raise RuntimeError("failed to locate IORT transform block")
start = script.index(start_marker)
end = script.index(end_marker, start)
script = script[:start] + "# IORT layout checks remain programmer invariants.\n\n" + script[end:]

# On aarch64, controller/VGIC presence is established during VM initialization.
# Propagate only the mutex poisoning that can occur while ACPI reads the GIC.
script = rewrite_once(
    script,
    '''    let interrupt_controller = device_manager
        .get_interrupt_controller()
        .ok_or(AcpiError::MissingInterruptController)?;
    let vgic = interrupt_controller
        .lock()
        .map_err(poisoned_lock)?
        .get_vgic()
        .ok_or(AcpiError::MissingVgic)?;''',
    '''    let vgic = device_manager
        .get_interrupt_controller()
        .unwrap()
        .lock()
        .map_err(poisoned_lock)?
        .get_vgic()
        .unwrap();''',
    "narrow aarch64 VGIC propagation",
)

# The serial lookup checks the same immutable device-info map before indexing it;
# retain the explicit invariant instead of silently treating inconsistency as off.
serial_start = "acpi = replace_once(\n    acpi,\n    '''        let is_serial_on = device_manager\n"
iort_call = "acpi = acpi.replace(\n    '        let iort = create_iort_table(device_manager.pci_segments());\\n',\n    '        let iort = create_iort_table(device_manager.pci_segments())?;\\n',\n)\n"
if script.count(serial_start) != 1 or script.count(iort_call) != 1:
    raise RuntimeError("failed to locate aarch64 serial/IORT transforms")
serial_pos = script.index(serial_start)
iort_pos = script.index(iort_call, serial_pos)
script = script[:serial_pos] + script[iort_pos:]
script = rewrite_once(script, iort_call, "", "remove IORT propagation call-site")

exec(compile(script, str(script_path), "exec"), {"__name__": "__main__"})
subprocess.run(["cargo", "fmt", "--all"], check=True)
print("acpi-error-candidate-formatted")
