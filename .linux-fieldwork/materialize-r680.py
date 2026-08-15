from pathlib import Path

# pci/src/device.rs: replace the implicit io::Error contract with an explicit outcome.
path = Path("pci/src/device.rs")
text = path.read_text()
marker = "/// This trait defines a set of functions which can be triggered whenever a PCI device is modified in any way.\n"
if marker not in text:
    raise SystemExit("DeviceRelocation marker missing")
error_lines = [
    "#[derive(Error, Debug)]",
    "pub enum DeviceRelocationError {",
    "    #[error(\"BAR relocation failed while the old mapping remained intact: {0}\")]",
    "    OldMappingIntact(#[source] io::Error),",
    "    #[error(\"BAR relocation failed after the new mapping was published: {0}\")]",
    "    NewMappingPublished(#[source] io::Error),",
    "}",
    "",
    "impl DeviceRelocationError {",
    "    pub fn can_restore_old(&self) -> bool {",
    "        matches!(self, Self::OldMappingIntact(_))",
    "    }",
    "}",
    "",
]
text = text.replace(marker, "\n".join(error_lines) + marker, 1)
old_sig = "    ) -> result::Result<(), io::Error>;\n"
new_sig = "    ) -> result::Result<(), DeviceRelocationError>;\n"
if old_sig not in text:
    raise SystemExit("DeviceRelocation return type changed")
path.write_text(text.replace(old_sig, new_sig, 1))

# pci/src/lib.rs: export the new error protocol.
path = Path("pci/src/lib.rs")
text = path.read_text()
old_export = "    BarReprogrammingParams, DeviceRelocation, Error as PciDeviceError, PciDevice,\n"
new_export = "    BarReprogrammingParams, DeviceRelocation, DeviceRelocationError, Error as PciDeviceError,\n    PciDevice,\n"
if old_export not in text:
    raise SystemExit("pci device export shape changed")
path.write_text(text.replace(old_export, new_export, 1))

# pci/src/bus.rs: restore config only when the relocation says OLD mapping survived.
path = Path("pci/src/bus.rs")
text = path.read_text()
old_handler = "\n".join([
    "                if let Err(e) = pci_bus.device_reloc.move_bar(",
    "                    params.old_base,",
    "                    params.new_base,",
    "                    params.len,",
    "                    device.deref_mut(),",
    "                    params.region_type,",
    "                ) {",
    "                    warn!(",
    "                        \"Failed moving device BAR: {}: 0x{:x}->0x{:x}(0x{:x}), keeping old BAR\",",
    "                        e, params.old_base, params.new_base, params.len",
    "                    );",
    "                    // Rollback: the config register was already updated to",
    "                    // new_base by detect_bar_reprogramming(). Restore it by",
    "                    // writing back the old address so device state stays",
    "                    // consistent with the MMIO bus mapping.",
    "                    device.restore_bar_addr(params);",
    "                }",
]) + "\n"
new_handler = "\n".join([
    "                if let Err(e) = pci_bus.device_reloc.move_bar(",
    "                    params.old_base,",
    "                    params.new_base,",
    "                    params.len,",
    "                    device.deref_mut(),",
    "                    params.region_type,",
    "                ) {",
    "                    if e.can_restore_old() {",
    "                        warn!(",
    "                            \"Failed moving device BAR: {}: 0x{:x}->0x{:x}(0x{:x}), restoring old BAR\",",
    "                            e, params.old_base, params.new_base, params.len",
    "                        );",
    "                        device.restore_bar_addr(params);",
    "                    } else {",
    "                        warn!(",
    "                            \"Failed moving device BAR after the new mapping was published: {}: 0x{:x}->0x{:x}(0x{:x}), retaining new BAR config\",",
    "                            e, params.old_base, params.new_base, params.len",
    "                        );",
    "                    }",
    "                }",
]) + "\n"
if old_handler not in text:
    raise SystemExit("PciConfigIo error handler shape changed")
text = text.replace(old_handler, new_handler, 1)
old_mmio_handler = "\n".join([
    "                if let Err(e) = pci_bus.device_reloc.move_bar(",
    "                    params.old_base,",
    "                    params.new_base,",
    "                    params.len,",
    "                    device.deref_mut(),",
    "                    params.region_type,",
    "                ) {",
    "                    warn!(",
    "                        \"Failed moving device BAR: {}: 0x{:x}->0x{:x}(0x{:x}), keeping old BAR\",",
    "                        e, params.old_base, params.new_base, params.len",
    "                    );",
    "                    device.restore_bar_addr(params);",
    "                }",
]) + "\n"
if old_mmio_handler not in text:
    raise SystemExit("PciConfigMmio error handler shape changed")
text = text.replace(old_mmio_handler, new_handler, 1)
old_mock_sig = "        ) -> Result<(), io::Error> {\n            Ok(())\n        }\n"
new_mock_sig = "        ) -> Result<(), crate::device::DeviceRelocationError> {\n            Ok(())\n        }\n"
if old_mock_sig not in text:
    raise SystemExit("pci MockDeviceRelocation signature changed")
text = text.replace(old_mock_sig, new_mock_sig, 1)

end = text.rfind("\n}")
if end < text.index("#[cfg(test)]\nmod unit_tests"):
    raise SystemExit("pci unit test terminator missing")
tests = [
    "",
    "    struct OutcomeBarDevice {",
    "        configuration: PciConfiguration,",
    "    }",
    "",
    "    impl OutcomeBarDevice {",
    "        fn new(base: u64) -> Self {",
    "            let mut configuration = PciConfiguration::new(",
    "                0x1234,",
    "                0x5678,",
    "                0,",
    "                PciClassCode::BridgeDevice,",
    "                &PciBridgeSubclass::HostBridge,",
    "                None,",
    "                PciHeaderType::Device,",
    "                0,",
    "                0,",
    "                None,",
    "                None,",
    "            );",
    "            configuration",
    "                .add_pci_bar(",
    "                    &crate::configuration::PciBarConfiguration::new(",
    "                        0,",
    "                        0x1000,",
    "                        PciBarRegionType::Memory32BitRegion,",
    "                        crate::configuration::PciBarPrefetchable::NotPrefetchable,",
    "                    )",
    "                    .set_address(base),",
    "                )",
    "                .unwrap();",
    "            assert!(",
    "                configuration",
    "                    .write_config_register(",
    "                        crate::configuration::COMMAND_REG,",
    "                        0,",
    "                        &crate::configuration::COMMAND_REG_MEMORY_SPACE_MASK.to_le_bytes(),",
    "                    )",
    "                    .is_empty()",
    "            );",
    "            Self { configuration }",
    "        }",
    "    }",
    "",
    "    impl PciDevice for OutcomeBarDevice {",
    "        fn write_config_register(",
    "            &mut self,",
    "            reg_idx: usize,",
    "            offset: u64,",
    "            data: &[u8],",
    "        ) -> (Vec<crate::device::BarReprogrammingParams>, Option<Arc<Barrier>>) {",
    "            (self.configuration.write_config_register(reg_idx, offset, data), None)",
    "        }",
    "        fn read_config_register(&mut self, reg_idx: usize) -> u32 {",
    "            self.configuration.read_reg(reg_idx)",
    "        }",
    "        fn restore_bar_addr(&mut self, params: &crate::device::BarReprogrammingParams) {",
    "            self.configuration.restore_bar_addr(params);",
    "        }",
    "        fn as_any_mut(&mut self) -> &mut dyn std::any::Any { self }",
    "        fn id(&self) -> Option<String> { None }",
    "    }",
    "",
    "    struct PublishedThenFailRelocation {",
    "        mapping: Arc<std::sync::atomic::AtomicU64>,",
    "    }",
    "    impl DeviceRelocation for PublishedThenFailRelocation {",
    "        fn move_bar(",
    "            &self,",
    "            _old_base: u64,",
    "            new_base: u64,",
    "            _len: u64,",
    "            _pci_dev: &mut dyn PciDevice,",
    "            _region_type: PciBarRegionType,",
    "        ) -> Result<(), crate::device::DeviceRelocationError> {",
    "            self.mapping.store(new_base, std::sync::atomic::Ordering::SeqCst);",
    "            Err(crate::device::DeviceRelocationError::NewMappingPublished(",
    "                io::Error::other(\"injected late failure\"),",
    "            ))",
    "        }",
    "    }",
    "",
    "    struct RejectedRelocation;",
    "    impl DeviceRelocation for RejectedRelocation {",
    "        fn move_bar(",
    "            &self,",
    "            _old_base: u64,",
    "            _new_base: u64,",
    "            _len: u64,",
    "            _pci_dev: &mut dyn PciDevice,",
    "            _region_type: PciBarRegionType,",
    "        ) -> Result<(), crate::device::DeviceRelocationError> {",
    "            Err(crate::device::DeviceRelocationError::OldMappingIntact(",
    "                io::Error::other(\"injected rejection\"),",
    "            ))",
    "        }",
    "    }",
    "",
    "    fn write_outcome_bar(",
    "        device: &Arc<Mutex<OutcomeBarDevice>> ,",
    "        relocation: Arc<dyn DeviceRelocation>,",
    "        new_base: u64,",
    "    ) {",
    "        const DEVICE: u8 = 1;",
    "        const BAR0_REG_INDEX: u64 = 4;",
    "        let mut pci_bus = PciBus::new(PciRoot::new(None), relocation);",
    "        let bus_device: Arc<Mutex<dyn PciDevice>> = device.clone();",
    "        pci_bus.add_device(DEVICE, bus_device).unwrap();",
    "        let mut config = PciConfigMmio::new(Arc::new(Mutex::new(pci_bus)));",
    "        let ecam_bar0 = (u64::from(DEVICE) << 15) | (BAR0_REG_INDEX << 2);",
    "        config.write(0, ecam_bar0, &(new_base as u32).to_le_bytes());",
    "    }",
    "",
    "    #[test]",
    "    fn published_move_error_keeps_new_config() {",
    "        const OLD: u64 = 0x1000_0000;",
    "        const NEW: u64 = 0x1000_1000;",
    "        let mapping = Arc::new(std::sync::atomic::AtomicU64::new(OLD));",
    "        let device = Arc::new(Mutex::new(OutcomeBarDevice::new(OLD)));",
    "        write_outcome_bar(",
    "            &device,",
    "            Arc::new(PublishedThenFailRelocation { mapping: mapping.clone() }),",
    "            NEW,",
    "        );",
    "        assert_eq!(device.lock().unwrap().configuration.get_bar_addr(0), NEW);",
    "        assert_eq!(mapping.load(std::sync::atomic::Ordering::SeqCst), NEW);",
    "    }",
    "",
    "    #[test]",
    "    fn rejected_move_error_restores_old_config() {",
    "        const OLD: u64 = 0x1000_0000;",
    "        const NEW: u64 = 0x1000_1000;",
    "        let device = Arc::new(Mutex::new(OutcomeBarDevice::new(OLD)));",
    "        write_outcome_bar(&device, Arc::new(RejectedRelocation), NEW);",
    "        assert_eq!(device.lock().unwrap().configuration.get_bar_addr(0), OLD);",
    "    }",
]
text = text[:end] + "\n".join(tests) + text[end:]
path.write_text(text)

# vmm/src/pci_segment.rs: update the test mock signature.
path = Path("vmm/src/pci_segment.rs")
text = path.read_text()
text = text.replace("    use std::io;\n", "", 1)
old = "        ) -> Result<(), io::Error> {\n            Ok(())\n        }\n"
new = "        ) -> Result<(), pci::DeviceRelocationError> {\n            Ok(())\n        }\n"
if old not in text:
    raise SystemExit("pci_segment mock signature changed")
path.write_text(text.replace(old, new, 1))

# vmm/src/device_manager.rs: classify failures around the actual Bus publication point.
path = Path("vmm/src/device_manager.rs")
text = path.read_text()
old_import = "    DeviceRelocation, MmioRegion, PciBarConfiguration, PciBarRegionType, PciBdf, PciDevice,\n"
new_import = "    DeviceRelocation, DeviceRelocationError, MmioRegion, PciBarConfiguration, PciBarRegionType,\n    PciBdf, PciDevice,\n"
if old_import not in text:
    raise SystemExit("pci import shape changed")
text = text.replace(old_import, new_import, 1)
old_start = "    ) -> result::Result<(), io::Error> {\n        let mut mmio_relocation_reservation = None;\n"
new_start = "    ) -> result::Result<(), DeviceRelocationError> {\n        let mut new_mapping_published = false;\n        let result: result::Result<(), io::Error> = (|| {\n            let mut mmio_relocation_reservation = None;\n"
if old_start not in text:
    raise SystemExit("AddressManager move_bar start changed")
text = text.replace(old_start, new_start, 1)
pio = "                self.io_bus\n                    .update_range(old_base, len, new_base, len)\n                    .map_err(io::Error::other)?;\n"
if pio not in text:
    raise SystemExit("PIO Bus update shape changed")
text = text.replace(pio, pio + "                new_mapping_published = true;\n", 1)
mmio = "                self.mmio_bus\n                    .update_range(old_base, len, new_base, len)\n                    .map_err(io::Error::other)?;\n"
if mmio not in text:
    raise SystemExit("MMIO Bus update shape changed")
text = text.replace(mmio, mmio + "                new_mapping_published = true;\n", 1)
old_end = "        pci_dev.move_bar(old_base, new_base)?;\n        if let Some(reservation) = mmio_relocation_reservation {\n            reservation.commit();\n        }\n        Ok(())\n    }\n}\n"
new_end = "            pci_dev.move_bar(old_base, new_base)?;\n            if let Some(reservation) = mmio_relocation_reservation {\n                reservation.commit();\n            }\n            Ok(())\n        })();\n\n        result.map_err(|error| {\n            if new_mapping_published {\n                DeviceRelocationError::NewMappingPublished(error)\n            } else {\n                DeviceRelocationError::OldMappingIntact(error)\n            }\n        })\n    }\n}\n"
if old_end not in text:
    raise SystemExit("AddressManager move_bar end changed")
path.write_text(text.replace(old_end, new_end, 1))
