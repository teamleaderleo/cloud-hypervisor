#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


class TransformError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise TransformError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, label: str) -> str:
    out, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL)
    if count != 1:
        raise TransformError(f"{label}: expected one match, found {count}")
    return out


acpi_path = Path("vmm/src/acpi.rs")
vm_path = Path("vmm/src/vm.rs")
acpi = acpi_path.read_text()
vm = vm_path.read_text()

acpi = replace_once(
    acpi,
    'use std::time::Instant;\n',
    'use std::io;\nuse std::sync::PoisonError;\nuse std::time::Instant;\n',
    "acpi std imports",
)
acpi = replace_once(
    acpi,
    'use tracer::trace_scoped;\n',
    'use thiserror::Error;\nuse tracer::trace_scoped;\n',
    "thiserror import",
)
acpi = replace_once(
    acpi,
    'use crate::{GuestMemoryMmap, GuestRegionMmap};\n\n',
    '''use crate::{GuestMemoryMmap, GuestRegionMmap};

#[derive(Debug, Error)]
pub enum AcpiError {
    #[error("ACPI table address overflow")]
    AddressOverflow,

    #[error("ACPI table layout is invalid")]
    InvalidTableLayout,

    #[error("ACPI interrupt controller is missing")]
    MissingInterruptController,

    #[error("ACPI VGIC is missing")]
    MissingVgic,

    #[error("fw_cfg is missing while ACPI table delivery is enabled")]
    MissingFwCfg,

    #[error("ACPI resource mutex is poisoned")]
    PoisonedLock,

    #[error("failed to write ACPI data to guest memory")]
    GuestMemory(#[source] vm_memory::GuestMemoryError),

    #[error("failed to add ACPI data to fw_cfg")]
    FwCfg(#[source] io::Error),

    #[error("PCI segment {0} cannot be represented in the IORT table")]
    InvalidIortPciSegment(u16),
}

pub type Result<T> = std::result::Result<T, AcpiError>;

fn poisoned_lock<T>(_: PoisonError<T>) -> AcpiError {
    AcpiError::PoisonedLock
}

fn next_table_address(address: GuestAddress, length: u64) -> Result<GuestAddress> {
    address.checked_add(length).ok_or(AcpiError::AddressOverflow)
}

''',
    "ACPI error type",
)

# FADT construction can fail when the allocator mutex is poisoned.
acpi = replace_once(
    acpi,
    '''fn create_facp_table(
    dsdt_offset: GuestAddress,
    device_manager: &DeviceManager,
    legacy_acpi_pm1a: bool,
) -> Sdt {''',
    '''fn create_facp_table(
    dsdt_offset: GuestAddress,
    device_manager: &DeviceManager,
    legacy_acpi_pm1a: bool,
) -> Result<Sdt> {''',
    "FADT signature",
)
acpi = replace_once(
    acpi,
    '        let mut allocator = device_manager.allocator().lock().unwrap();\n',
    '        let mut allocator = device_manager.allocator().lock().map_err(poisoned_lock)?;\n',
    "allocator lock",
)
acpi = replace_once(
    acpi,
    '''    facp.update_checksum();

    facp
}

fn create_mcfg_table''',
    '''    facp.update_checksum();

    Ok(facp)
}

fn create_mcfg_table''',
    "FADT return",
)

# Structure-size checks are compile-time invariants, not runtime failure paths.
acpi = replace_once(
    acpi,
    '''    // Check the MemoryAffinity structure is the right size as expected by
    // the ACPI specification.
    assert_eq!(size_of::<MemoryAffinity>(), 40);
    // Confirm struct size matches ACPI 6.6 spec
    assert_eq!(size_of::<GenericInitiatorAffinity>(), 32);
''',
    '',
    "runtime structure assertions",
)
acpi = replace_once(
    acpi,
    '''impl MemoryAffinity {
''',
    '''const _: () = assert!(size_of::<MemoryAffinity>() == 40);
const _: () = assert!(size_of::<GenericInitiatorAffinity>() == 32);

impl MemoryAffinity {
''',
    "compile-time structure assertions",
)

# IORT has configuration-sensitive validation and must be fallible.
acpi = replace_once(
    acpi,
    'fn create_iort_table(pci_segments: &[PciSegment]) -> Sdt {\n',
    'fn create_iort_table(pci_segments: &[PciSegment]) -> Result<Sdt> {\n',
    "IORT signature",
)
acpi = acpi.replace(
    '    assert_eq!(iort.len(), ACPI_IORT_HEADER_SIZE as usize);\n',
    '''    if iort.len() != ACPI_IORT_HEADER_SIZE as usize {
        return Err(AcpiError::InvalidTableLayout);
    }
''',
)
acpi = acpi.replace(
    '    assert!(align_to_8_bytes(offset_its_node) == 0); // Ensure the ITS node is 8-byte aligned\n',
    '''    if align_to_8_bytes(offset_its_node) != 0 {
        return Err(AcpiError::InvalidTableLayout);
    }
''',
)
acpi = acpi.replace(
    '    assert!(iort.len() == offset_its_node);\n',
    '''    if iort.len() != offset_its_node {
        return Err(AcpiError::InvalidTableLayout);
    }
''',
)
acpi = acpi.replace(
    '        assert!(align_to_8_bytes(iort.len()) == 0); // Ensure each node is 8-byte aligned\n',
    '''        if align_to_8_bytes(iort.len()) != 0 {
            return Err(AcpiError::InvalidTableLayout);
        }
''',
)
acpi = acpi.replace(
    '        assert!(segment.id < 256, "Up to 256 PCI segments are supported.");\n',
    '''        if segment.id >= 256 {
            return Err(AcpiError::InvalidIortPciSegment(segment.id));
        }
''',
)
acpi = replace_once(
    acpi,
    '''    iort.update_checksum();

    iort
}

fn create_viot_table''',
    '''    iort.update_checksum();

    Ok(iort)
}

fn create_viot_table''',
    "IORT return",
)

# Core table layout becomes fallible.
acpi = replace_once(
    acpi,
    ''') -> (Rsdp, Vec<u8>, Vec<u64>) {
    // Generated bytes for ACPI tables''',
    ''') -> Result<(Rsdp, Vec<u8>, Vec<u64>)> {
    // Generated bytes for ACPI tables''',
    "internal signature",
)
acpi = acpi.replace(
    '    let facp = create_facp_table(dsdt_addr, device_manager, legacy_acpi_pm1a);\n',
    '    let facp = create_facp_table(dsdt_addr, device_manager, legacy_acpi_pm1a)?;\n',
)
acpi = re.sub(
    r'([A-Za-z0-9_\.]+)\.checked_add\(([^\n]+)\)\.unwrap\(\)',
    r'next_table_address(\1, \2)?',
    acpi,
)
acpi = replace_once(
    acpi,
    '''    let vgic = device_manager
        .get_interrupt_controller()
        .unwrap()
        .lock()
        .unwrap()
        .get_vgic()
        .unwrap();''',
    '''    let interrupt_controller = device_manager
        .get_interrupt_controller()
        .ok_or(AcpiError::MissingInterruptController)?;
    let vgic = interrupt_controller
        .lock()
        .map_err(poisoned_lock)?
        .get_vgic()
        .ok_or(AcpiError::MissingVgic)?;''',
    "aarch64 VGIC lookup",
)
acpi = replace_once(
    acpi,
    '''        let is_serial_on = device_manager
            .get_device_info()
            .clone()
            .contains_key(&(DeviceType::Serial, DeviceType::Serial.to_string()));
        let serial_device_addr = layout::LEGACY_SERIAL_MAPPED_IO_START.raw_value();
        let serial_device_irq = if is_serial_on {
            device_manager
                .get_device_info()
                .clone()
                .get(&(DeviceType::Serial, DeviceType::Serial.to_string()))
                .unwrap()
                .irq()
        } else {
            // If serial is turned off, add a fake device with invalid irq.
            31
        };''',
    '''        let device_info = device_manager.get_device_info().clone();
        let serial_device_addr = layout::LEGACY_SERIAL_MAPPED_IO_START.raw_value();
        let serial_device_irq = device_info
            .get(&(DeviceType::Serial, DeviceType::Serial.to_string()))
            .map(|device| device.irq())
            // If serial is turned off, add a fake device with invalid irq.
            .unwrap_or(31);''',
    "aarch64 serial lookup",
)
acpi = acpi.replace(
    '        let iort = create_iort_table(device_manager.pci_segments());\n',
    '        let iort = create_iort_table(device_manager.pci_segments())?;\n',
)
acpi = replace_once(
    acpi,
    '    (rsdp, tables_bytes, xsdt_table_pointers)\n}\n\n#[cfg(feature = "fw_cfg")]\n',
    '    Ok((rsdp, tables_bytes, xsdt_table_pointers))\n}\n\n#[cfg(feature = "fw_cfg")]\n',
    "internal return",
)

# fw_cfg delivery returns the same ACPI error type.
acpi = replace_once(
    acpi,
    ') -> Result<(), vm::Error> {\n',
    ') -> Result<()> {\n',
    "fw_cfg signature",
)
acpi = replace_once(
    acpi,
    '''    let (rsdp, table_bytes, xsdt_table_pointers) = create_acpi_tables_internal(
        dsdt_offset,
        device_manager,
        cpu_manager,
        memory_manager,
        numa_nodes,
        tpm_enabled,
    );''',
    '''    let (rsdp, table_bytes, xsdt_table_pointers) = create_acpi_tables_internal(
        dsdt_offset,
        device_manager,
        cpu_manager,
        memory_manager,
        numa_nodes,
        tpm_enabled,
    )?;''',
    "fw_cfg internal call",
)
acpi = replace_once(
    acpi,
    '''    device_manager
        .fw_cfg()
        .expect("fw_cfg must be present")
        .lock()
        .unwrap()
        .add_acpi(rsdp, table_bytes, checksums, pointer_offsets)
        .map_err(vm::Error::CreatingAcpiTables)
}''',
    '''    device_manager
        .fw_cfg()
        .ok_or(AcpiError::MissingFwCfg)?
        .lock()
        .map_err(poisoned_lock)?
        .add_acpi(rsdp, table_bytes, checksums, pointer_offsets)
        .map_err(AcpiError::FwCfg)
}''',
    "fw_cfg delivery",
)

# Direct guest-memory delivery returns errors.
acpi = replace_once(
    acpi,
    ') -> GuestAddress {\n    trace_scoped!("create_acpi_tables");',
    ') -> Result<GuestAddress> {\n    trace_scoped!("create_acpi_tables");',
    "direct signature",
)
acpi = replace_once(
    acpi,
    '''    let (rsdp, tables_bytes, _xsdt_table_pointers) = create_acpi_tables_internal(
        dsdt_addr,
        device_manager,
        cpu_manager,
        memory_manager,
        numa_nodes,
        tpm_enabled,
    );''',
    '''    let (rsdp, tables_bytes, _xsdt_table_pointers) = create_acpi_tables_internal(
        dsdt_addr,
        device_manager,
        cpu_manager,
        memory_manager,
        numa_nodes,
        tpm_enabled,
    )?;''',
    "direct internal call",
)
acpi = replace_once(
    acpi,
    '''    guest_mem
        .write_slice(rsdp.as_bytes(), rsdp_addr)
        .expect("Error writing RSDP");

    guest_mem
        .write_slice(tables_bytes.as_slice(), dsdt_addr)
        .expect("Error writing ACPI tables");''',
    '''    guest_mem
        .write_slice(rsdp.as_bytes(), rsdp_addr)
        .map_err(AcpiError::GuestMemory)?;

    guest_mem
        .write_slice(tables_bytes.as_slice(), dsdt_addr)
        .map_err(AcpiError::GuestMemory)?;''',
    "guest memory writes",
)
acpi = replace_once(
    acpi,
    '    rsdp_addr\n}\n\n#[cfg(feature = "tdx")]\n',
    '    Ok(rsdp_addr)\n}\n\n#[cfg(feature = "tdx")]\n',
    "direct return",
)

# TDX reuses fallible children.
acpi = replace_once(
    acpi,
    ') -> Vec<Sdt> {\n    // DSDT\n',
    ') -> Result<Vec<Sdt>> {\n    // DSDT\n',
    "TDX signature",
)
acpi = replace_once(
    acpi,
    '''    tables.push(create_facp_table(
        GuestAddress(0),
        device_manager,
        legacy_acpi_pm1a,
    ));''',
    '''    tables.push(create_facp_table(
        GuestAddress(0),
        device_manager,
        legacy_acpi_pm1a,
    )?);''',
    "TDX FADT",
)
acpi = replace_once(
    acpi,
    '    tables\n}\n\n#[cfg(test)]\n',
    '    Ok(tables)\n}\n\n#[cfg(test)]\n',
    "TDX return",
)

# VM error type and call boundary.
vm = replace_once(
    vm,
    '''    #[cfg(feature = "fw_cfg")]
    #[error("Error creating acpi tables")]
    CreatingAcpiTables(#[source] io::Error),''',
    '''    #[error("Error creating ACPI tables")]
    CreatingAcpiTables(#[source] acpi::AcpiError),''',
    "VM ACPI error variant",
)
vm = replace_once(
    vm,
    '    fn create_acpi_tables(&self) -> Option<GuestAddress> {\n',
    '    fn create_acpi_tables(&self) -> Result<Option<GuestAddress>> {\n',
    "VM helper signature",
)
vm = replace_once(
    vm,
    '            return None;\n',
    '            return Ok(None);\n',
    "TDX no-op return",
)
vm = replace_once(
    vm,
    '''        let rsdp_addr = acpi::create_acpi_tables(
            &mem,
            &self.device_manager.lock().unwrap(),
            &self.cpu_manager.lock().unwrap(),
            &self.memory_manager.lock().unwrap(),
            &self.numa_nodes,
            tpm_enabled,
        );''',
    '''        let rsdp_addr = acpi::create_acpi_tables(
            &mem,
            &self.device_manager.lock().unwrap(),
            &self.cpu_manager.lock().unwrap(),
            &self.memory_manager.lock().unwrap(),
            &self.numa_nodes,
            tpm_enabled,
        )
        .map_err(Error::CreatingAcpiTables)?;''',
    "VM direct call",
)
vm = replace_once(vm, '        Some(rsdp_addr)\n', '        Ok(Some(rsdp_addr))\n', "VM helper return")
vm = vm.replace('self.create_acpi_tables()\n', 'self.create_acpi_tables()?\n')
vm = replace_once(
    vm,
    '''                    acpi::create_acpi_tables_for_fw_cfg(
                        &self.device_manager.lock().unwrap(),
                        &self.cpu_manager.lock().unwrap(),
                        &self.memory_manager.lock().unwrap(),
                        &self.numa_nodes,
                        tpm_enabled,
                    )?;''',
    '''                    acpi::create_acpi_tables_for_fw_cfg(
                        &self.device_manager.lock().unwrap(),
                        &self.cpu_manager.lock().unwrap(),
                        &self.memory_manager.lock().unwrap(),
                        &self.numa_nodes,
                        tpm_enabled,
                    )
                    .map_err(Error::CreatingAcpiTables)?;''',
    "VM fw_cfg call",
)
vm = replace_once(
    vm,
    '''        for acpi_table in acpi::create_acpi_tables_tdx(
            &self.device_manager.lock().unwrap(),
            &self.cpu_manager.lock().unwrap(),
            &self.memory_manager.lock().unwrap(),
            &self.numa_nodes,
        ) {''',
    '''        for acpi_table in acpi::create_acpi_tables_tdx(
            &self.device_manager.lock().unwrap(),
            &self.cpu_manager.lock().unwrap(),
            &self.memory_manager.lock().unwrap(),
            &self.numa_nodes,
        )
        .map_err(Error::CreatingAcpiTables)?
        {''',
    "VM TDX call",
)

# Deterministic unit coverage for the new arithmetic boundary.
acpi = replace_once(
    acpi,
    '''    #[test]
    fn test_generic_initiator_affinity_size() {''',
    '''    #[test]
    fn test_next_table_address_overflow() {
        assert!(matches!(
            next_table_address(GuestAddress(u64::MAX), 1),
            Err(AcpiError::AddressOverflow)
        ));
    }

    #[test]
    fn test_generic_initiator_affinity_size() {''',
    "overflow test",
)

# The old crate::vm import is no longer needed in acpi.rs.
acpi = acpi.replace('#[cfg(feature = "fw_cfg")]\nuse crate::vm;\n', '')

acpi_path.write_text(acpi)
vm_path.write_text(vm)
print("acpi-error-candidate-applied")
