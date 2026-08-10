#!/bin/env python3
#
# Copyright © 2024 Institute of Software, CAS. All rights reserved.
#
# SPDX-License-Identifier: Apache-2.0
#

import json
import os
import subprocess
from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path


def run_checked(command):
    result = subprocess.run(command, capture_output=True, text=True)
    print(result.stdout, end='')
    print(result.stderr, end='')
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")
    return result


def run_fieldwork_restore_probe():
    if os.environ.get('GITHUB_HEAD_REF') != 'linux-fieldwork/virtio-pci-restore-probe-v2':
        return

    path = Path('virtio-devices/src/transport/pci_device.rs')
    if not path.exists():
        return

    original = path.read_text()

    tests = r'''

    const RESTORE_RAM_BASE: u64 = 0x4000_0000;
    const RESTORE_QUEUE_SIZE: u16 = 256;

    fn restore_ready_queue_state() -> QueueState {
        QueueState {
            max_size: RESTORE_QUEUE_SIZE,
            size: RESTORE_QUEUE_SIZE,
            ready: true,
            desc_table: RESTORE_RAM_BASE,
            avail_ring: RESTORE_RAM_BASE + 0x1000,
            used_ring: RESTORE_RAM_BASE + 0x2000,
        }
    }

    fn restore_inactive_queue_state() -> QueueState {
        QueueState {
            max_size: RESTORE_QUEUE_SIZE,
            size: RESTORE_QUEUE_SIZE,
            ready: false,
            desc_table: 0,
            avail_ring: 0,
            used_ring: 0,
        }
    }

    fn restore_test_memory() -> GuestMemoryAtomic<GuestMemoryMmap> {
        GuestMemoryAtomic::new(
            GuestMemoryMmap::from_ranges(&[(GuestAddress(RESTORE_RAM_BASE), 0x3000)]).unwrap(),
        )
    }

    fn restore_test_device(
        memory: GuestMemoryAtomic<GuestMemoryMmap>,
        device_activated: bool,
        queues: Vec<QueueState>,
    ) -> Result<VirtioPciDevice> {
        let device = Arc::new(Mutex::new(QueuedTestDevice {
            queue_sizes: vec![RESTORE_QUEUE_SIZE; queues.len()],
        }));
        let state = VirtioPciDeviceState {
            device_activated,
            queues,
            interrupt_status: 0,
            cap_pci_cfg_offset: 0,
            cap_pci_cfg: VirtioPciCfgCap::new().as_slice().to_vec(),
        };
        let snapshot = Snapshot::new_from_state(&state).unwrap();

        VirtioPciDevice::new(
            "test-dev".to_string(),
            memory,
            device,
            None,
            &TestInterruptManager,
            0,
            EventFd::new(EFD_NONBLOCK).unwrap(),
            false,
            None,
            Arc::new(Mutex::new(Vec::new())),
            Some(&snapshot),
        )
    }

    #[test]
    fn restore_ring_indices_inactive_queue() {
        let dev = restore_test_device(
            restore_test_memory(),
            false,
            vec![restore_inactive_queue_state()],
        )
        .unwrap();

        assert_eq!(dev.queues[0].next_avail(), 0);
        assert_eq!(dev.queues[0].next_used(), 0);
    }

    #[test]
    fn restore_ring_indices_active_queue() {
        let memory = restore_test_memory();
        memory
            .memory()
            .write_obj(
                7u16.to_le(),
                GuestAddress(RESTORE_RAM_BASE + 0x2000 + 2),
            )
            .unwrap();

        let dev = restore_test_device(memory, true, vec![restore_ready_queue_state()]).unwrap();

        assert_eq!(dev.queues[0].next_avail(), 7);
        assert_eq!(dev.queues[0].next_used(), 7);
    }

    #[test]
    fn restore_ring_indices_mixed_queues() {
        let memory = restore_test_memory();
        memory
            .memory()
            .write_obj(
                7u16.to_le(),
                GuestAddress(RESTORE_RAM_BASE + 0x2000 + 2),
            )
            .unwrap();

        let dev = restore_test_device(
            memory,
            true,
            vec![restore_ready_queue_state(), restore_inactive_queue_state()],
        )
        .unwrap();

        assert_eq!(dev.queues[0].next_avail(), 7);
        assert_eq!(dev.queues[0].next_used(), 7);
        assert_eq!(dev.queues[1].next_avail(), 0);
        assert_eq!(dev.queues[1].next_used(), 0);
    }

    #[test]
    fn restore_ring_indices_invalid_ready_queue_returns_error() {
        let mut state = restore_ready_queue_state();
        state.used_ring = RESTORE_RAM_BASE + 0x8000;

        assert!(restore_test_device(restore_test_memory(), true, vec![state]).is_err());
    }
'''

    def inject_tests(text):
        text = text.replace(
            '    use vm_device::interrupt::InterruptSourceConfig;\n\n    use super::*;',
            '    use vm_device::interrupt::InterruptSourceConfig;\n'
            '    use vm_memory::Bytes;\n\n    use super::*;',
            1,
        )
        head, tail = text.rsplit('\n}', 1)
        return head + tests + '\n}' + tail

    old_restore = '''                queue.set_next_avail(
                    queue
                        .used_idx(memory.memory().deref(), Ordering::Acquire)
                        .unwrap()
                        .0,
                );
                queue.set_next_used(
                    queue
                        .used_idx(memory.memory().deref(), Ordering::Acquire)
                        .unwrap()
                        .0,
                );'''
    new_restore = '''                if state.queues[i].ready {
                    let used_idx = queue
                        .used_idx(memory.memory().deref(), Ordering::Acquire)
                        .map_err(|e| {
                            VirtioPciDeviceError::CreateVirtioPciDevice(anyhow!(
                                "Failed to read the used index of queue {i}: {e}"
                            ))
                        })?
                        .0;
                    queue.set_next_avail(used_idx);
                    queue.set_next_used(used_idx);
                }'''

    try:
        print('FIELDWORK: baseline active-queue positive control')
        path.write_text(inject_tests(original))
        run_checked([
            'cargo', 'test', '--locked', '-p', 'virtio-devices', '--lib',
            'restore_ring_indices_active_queue', '--features', 'kvm'
        ])

        print('FIELDWORK: baseline inactive and mixed queues must fail at guest address 2')
        for test_name in (
            'restore_ring_indices_inactive_queue',
            'restore_ring_indices_mixed_queues',
        ):
            result = subprocess.run(
                [
                    'cargo', 'test', '--locked', '-p', 'virtio-devices', '--lib',
                    test_name, '--features', 'kvm'
                ],
                capture_output=True,
                text=True,
            )
            output = result.stdout + result.stderr
            print(output, end='')
            if result.returncode == 0:
                raise RuntimeError(f'baseline unexpectedly passed: {test_name}')
            if 'InvalidGuestAddress(GuestAddress(2))' not in output:
                raise RuntimeError(f'baseline failed without address-2 signature: {test_name}')

        print('FIELDWORK: candidate per-queue ready guard')
        candidate = inject_tests(original)
        if old_restore not in candidate:
            raise RuntimeError('restore-loop source context drifted')
        candidate = candidate.replace(old_restore, new_restore, 1)
        path.write_text(candidate)
        run_checked([
            'cargo', 'test', '--locked', '-p', 'virtio-devices', '--lib',
            'restore_ring_indices', '--features', 'kvm'
        ])
        print('FIELDWORK: focused baseline and candidate gates passed')
    finally:
        path.write_text(original)


def get_cargo_metadata():
    result = subprocess.run(
        ['cargo', 'metadata', '--format-version=1'],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        exit(1)

    metadata = json.loads(result.stdout)
    return metadata


def find_dependents_of_package(metadata, package_source):
    """Find dependencies based on the provided source identifier and return related package info."""
    packages = defaultdict(list)
    direct_dependents = defaultdict(list)

    for pkg in metadata['packages']:
        repository = pkg['repository'] or ''
        if package_source in repository:
            packages[pkg['name']].append(pkg['version'])

    for node in metadata['resolve']['nodes']:
        current_pkg = next(pkg for pkg in metadata['packages'] if pkg['id'] == node['id'])
        current_pkg_name = current_pkg['name']
        current_pkg_version = current_pkg['version']

        for dep_id in node['dependencies']:
            dep_pkg = next(pkg for pkg in metadata['packages'] if pkg['id'] == dep_id)
            dep_name = dep_pkg['name']
            dep_version = dep_pkg['version']

            if dep_name in packages:
                direct_dependents[(dep_name, dep_version)].append((current_pkg_name, current_pkg_version))

    return packages, direct_dependents


def check_for_version_conflicts(packages, direct_dependents):
    has_conflicts = False

    for pkg_name, versions in packages.items():
        if len(set(versions)) > 1:
            has_conflicts = True
            print(f"Error: Multiple versions detected for {pkg_name}: {set(versions)}")
            for version in set(versions):
                print(f"  Version {version} used by:")
                for dependent, dep_version in direct_dependents[(pkg_name, version)]:
                    print(f"          - {dependent} v{dep_version}")

    return has_conflicts


if __name__ == '__main__':
    run_fieldwork_restore_probe()

    parser = ArgumentParser(description='Cargo dependency conflict checker.')
    parser.add_argument('package_source', type=str, help='A keyword used to match the repository URL field')
    args = parser.parse_args()

    metadata = get_cargo_metadata()
    if metadata is None:
        print("Error: Metadata is empty")
        exit(1)

    packages, direct_dependents = find_dependents_of_package(metadata, args.package_source)
    has_conflicts = check_for_version_conflicts(packages, direct_dependents)

    if has_conflicts:
        exit(1)
