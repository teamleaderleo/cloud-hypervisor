from pathlib import Path

path = Path('vm-device/src/bus.rs')
text = path.read_text()

old_struct = '''#[derive(Default)]
pub struct Bus {
    devices: RwLock<BTreeMap<BusRange, Weak<dyn BusDeviceSync>>>,
}
'''
new_struct = '''#[derive(Default)]
pub struct Bus {
    devices: RwLock<BTreeMap<BusRange, Weak<dyn BusDeviceSync>>>,
    #[cfg(test)]
    update_barrier: Mutex<Option<Arc<Barrier>>>,
}
'''
if old_struct not in text:
    raise SystemExit('Bus struct shape changed')
text = text.replace(old_struct, new_struct, 1)

old_new = '''    pub fn new() -> Bus {
        Bus {
            devices: RwLock::new(BTreeMap::new()),
        }
    }
'''
new_new = '''    pub fn new() -> Bus {
        Bus {
            devices: RwLock::new(BTreeMap::new()),
            #[cfg(test)]
            update_barrier: Mutex::new(None),
        }
    }

    #[cfg(test)]
    fn set_update_barrier(&self, barrier: Option<Arc<Barrier>>) {
        *self.update_barrier.lock().unwrap() = barrier;
    }
'''
if old_new not in text:
    raise SystemExit('Bus::new shape changed')
text = text.replace(old_new, new_new, 1)

seam = '''        let device = devices
            .get(&old_range)
            .and_then(Weak::upgrade)
            .ok_or(Error::MissingAddressRange)?;

        if devices
'''
seam_instrumented = '''        let device = devices
            .get(&old_range)
            .and_then(Weak::upgrade)
            .ok_or(Error::MissingAddressRange)?;

        #[cfg(test)]
        let update_barrier = self.update_barrier.lock().unwrap().clone();
        #[cfg(test)]
        if let Some(barrier) = update_barrier {
            barrier.wait();
            barrier.wait();
        }

        if devices
'''
if seam not in text:
    raise SystemExit('update_range strong-lifetime seam changed')
text = text.replace(seam, seam_instrumented, 1)

unit_marker = '#[cfg(test)]\nmod unit_tests {\n    use super::*;\n'
if unit_marker not in text:
    raise SystemExit('unit test marker changed')
text = text.replace(unit_marker, unit_marker + '    use std::thread;\n', 1)

end = text.rfind('\n}')
if end < text.index('#[cfg(test)]\nmod unit_tests'):
    raise SystemExit('unit test module terminator missing')
test_lines = [
    '',
    '    #[test]',
    '    fn update_range_keeps_device_alive_until_move_finishes() {',
    '        let bus = Arc::new(Bus::new());',
    '        let device = Arc::new(DummyDevice);',
    '        let weak = Arc::downgrade(&device);',
    '        bus.insert(device.clone(), 0x1000, 0x100).unwrap();',
    '',
    '        let barrier = Arc::new(Barrier::new(2));',
    '        bus.set_update_barrier(Some(barrier.clone()));',
    '',
    '        let update_bus = bus.clone();',
    '        let handle = thread::spawn(move || {',
    '            update_bus.update_range(0x1000, 0x100, 0x2000, 0x100)',
    '        });',
    '',
    '        barrier.wait();',
    '        drop(device);',
    '        assert!(',
    '            weak.upgrade().is_some(),',
    '            "update_range must retain the device strongly while the move is in flight"',
    '        );',
    '        barrier.wait();',
    '        handle.join().unwrap().unwrap();',
    '        bus.set_update_barrier(None);',
    '',
    '        assert!(weak.upgrade().is_none());',
    '    }',
]
text = text[:end] + '\n'.join(test_lines) + text[end:]
path.write_text(text)
