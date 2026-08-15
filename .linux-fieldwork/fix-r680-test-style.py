from pathlib import Path

path = Path('pci/src/bus.rs')
text = path.read_text()

marker = '#[cfg(test)]\nmod unit_tests {\n'
imports = '\n'.join([
    '    use std::any::Any;',
    '    use std::sync::atomic::{AtomicU64, Ordering};',
    '',
    '    use crate::configuration::{',
    '        BarReprogrammingParams, COMMAND_REG, COMMAND_REG_MEMORY_SPACE_MASK,',
    '        PciBarConfiguration, PciBarPrefetchable,',
    '    };',
    '    use crate::device::DeviceRelocationError;',
    '',
])
if marker not in text:
    raise SystemExit('pci unit-test module marker missing')
text = text.replace(marker, marker + imports, 1)

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
    text = text.replace(old, new)

path.write_text(text)
