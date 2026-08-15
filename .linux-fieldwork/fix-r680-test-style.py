from pathlib import Path

path = Path('pci/src/bus.rs')
text = path.read_text()
marker = '#[cfg(test)]\nmod unit_tests {\n'
if marker not in text:
    raise SystemExit('pci unit-test module marker missing')

unit_pos = text.index(marker)
prefix = text[:unit_pos]
unit = text[unit_pos:]

imports = '\n'.join([
    '    use std::sync::atomic::{AtomicU64, Ordering};',
    '',
    '    use crate::configuration::{',
    '        COMMAND_REG, COMMAND_REG_MEMORY_SPACE_MASK, PciBarConfiguration,',
    '        PciBarPrefetchable,',
    '    };',
    '    use crate::DeviceRelocationError;',
    '',
])
unit = unit.replace(marker, marker + imports, 1)

replacements = {
    'crate::device::DeviceRelocationError': 'DeviceRelocationError',
    'crate::configuration::PciBarConfiguration': 'PciBarConfiguration',
    'crate::configuration::PciBarPrefetchable': 'PciBarPrefetchable',
    'crate::configuration::COMMAND_REG_MEMORY_SPACE_MASK': 'COMMAND_REG_MEMORY_SPACE_MASK',
    'crate::configuration::COMMAND_REG': 'COMMAND_REG',
    'crate::device::BarReprogrammingParams': 'BarReprogrammingParams',
    'std::any::Any': 'Any',
    'std::sync::atomic::AtomicU64': 'AtomicU64',
    'std::sync::atomic::Ordering::SeqCst': 'Ordering::SeqCst',
}
for old, new in replacements.items():
    unit = unit.replace(old, new)

path.write_text(prefix + unit)
