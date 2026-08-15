from pathlib import Path
import subprocess

old_clean = subprocess.check_output([
    'git', 'show',
    'origin/review/ch-bus-r677-r678-r679-clean:vm-device/src/bus.rs',
], text=True)
path = Path('vm-device/src/bus.rs')
text = old_clean

old = '''        let device = devices
            .get(&old_range)
            .cloned()
            .ok_or(Error::MissingAddressRange)?;
        if device.upgrade().is_none() {
            return Err(Error::MissingAddressRange);
        }
'''
new = '''        let device = devices
            .get(&old_range)
            .and_then(Weak::upgrade)
            .ok_or(Error::MissingAddressRange)?;
'''
if old not in text:
    raise SystemExit('old clean weak-lifetime shape changed')
text = text.replace(old, new, 1)

old_insert = '        debug_assert!(devices.insert(new_range, device).is_none());\n'
new_insert = '        debug_assert!(devices.insert(new_range, Arc::downgrade(&device)).is_none());\n'
if old_insert not in text:
    raise SystemExit('old clean update insertion shape changed')
text = text.replace(old_insert, new_insert, 1)

path.write_text(text)
