from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}")
    p.write_text(text.replace(old, new, 1))


replace_once(
    "hypervisor/src/vm.rs",
    "use std::result;\n",
    "use std::num::NonZeroU64;\nuse std::result;\n",
)

replace_once(
    "hypervisor/src/vm.rs",
    """pub type Result<T> = result::Result<T, HypervisorVmError>;

/// Configuration data for legacy interrupts.
""",
    """pub type Result<T> = result::Result<T, HypervisorVmError>;

/// Dirty-page bitmap and number of bytes represented by each bit.
#[derive(Debug)]
pub struct DirtyLog {
    pub bitmap: Vec<u64>,
    pub bytes_per_bit: NonZeroU64,
}

/// Configuration data for legacy interrupts.
""",
)

replace_once(
    "hypervisor/src/vm.rs",
    """    /// Get dirty pages bitmap
    fn get_dirty_log(&self, slot: u32, base_gpa: u64, memory_size: u64) -> Result<Vec<u64>>;
""",
    """    /// Get dirty pages bitmap and its backend-defined byte granularity.
    fn get_dirty_log(&self, slot: u32, base_gpa: u64, memory_size: u64) -> Result<DirtyLog>;
""",
)

replace_once(
    "hypervisor/src/lib.rs",
    """pub use vm::{
    DataMatch, HypervisorVmError, InterruptSourceConfig, LegacyIrqSourceConfig, MsiIrqSourceConfig,
    Vm, VmOps,
};
""",
    """pub use vm::{
    DataMatch, DirtyLog, HypervisorVmError, InterruptSourceConfig, LegacyIrqSourceConfig,
    MsiIrqSourceConfig, Vm, VmOps,
};
""",
)

replace_once(
    "hypervisor/src/kvm/mod.rs",
    """    ///
    /// Get dirty pages bitmap (one bit per page)
    ///
    fn get_dirty_log(&self, slot: u32, _base_gpa: u64, memory_size: u64) -> vm::Result<Vec<u64>> {
        self.fd
            .get_dirty_log(slot, memory_size as usize)
            .map_err(|e| vm::HypervisorVmError::GetDirtyLog(e.into()))
    }
""",
    """    ///
    /// Get dirty pages bitmap (one bit per host page)
    ///
    fn get_dirty_log(
        &self,
        slot: u32,
        _base_gpa: u64,
        memory_size: u64,
    ) -> vm::Result<crate::DirtyLog> {
        // SAFETY: Calling sysconf with _SC_PAGESIZE has no memory-safety requirements.
        let raw_page_size = unsafe { libc::sysconf(libc::_SC_PAGESIZE) };
        let bytes_per_bit = u64::try_from(raw_page_size)
            .ok()
            .and_then(std::num::NonZeroU64::new)
            .filter(|page_size| page_size.get().is_power_of_two())
            .ok_or_else(|| {
                vm::HypervisorVmError::GetDirtyLog(anyhow!("Invalid host page size"))
            })?;
        let bitmap = self
            .fd
            .get_dirty_log(slot, memory_size as usize)
            .map_err(|e| vm::HypervisorVmError::GetDirtyLog(e.into()))?;

        Ok(crate::DirtyLog {
            bitmap,
            bytes_per_bit,
        })
    }
""",
)

replace_once(
    "hypervisor/src/mshv/mod.rs",
    """    ///
    /// Get dirty pages bitmap (one bit per page)
    ///
    fn get_dirty_log(&self, _slot: u32, base_gpa: u64, memory_size: u64) -> vm::Result<Vec<u64>> {
        self.fd
            .get_dirty_log(
                base_gpa >> PAGE_SHIFT,
                memory_size as usize,
                MSHV_GPAP_ACCESS_OP_CLEAR as u8,
            )
            .map_err(|e| vm::HypervisorVmError::GetDirtyLog(e.into()))
    }
""",
    """    ///
    /// Get dirty pages bitmap (one bit per MSHV page)
    ///
    fn get_dirty_log(
        &self,
        _slot: u32,
        base_gpa: u64,
        memory_size: u64,
    ) -> vm::Result<crate::DirtyLog> {
        let bitmap = self
            .fd
            .get_dirty_log(
                base_gpa >> PAGE_SHIFT,
                memory_size as usize,
                MSHV_GPAP_ACCESS_OP_CLEAR as u8,
            )
            .map_err(|e| vm::HypervisorVmError::GetDirtyLog(e.into()))?;

        Ok(crate::DirtyLog {
            bitmap,
            bytes_per_bit: std::num::NonZeroU64::new(1u64 << PAGE_SHIFT).unwrap(),
        })
    }
""",
)

replace_once(
    "vmm/src/memory_manager.rs",
    "use std::num::NonZeroUsize;\n",
    "use std::num::{NonZeroU64, NonZeroUsize};\n",
)

replace_once(
    "vmm/src/memory_manager.rs",
    """impl Migratable for MemoryManager {
    // Start the dirty log in the hypervisor (kvm/mshv).
""",
    """fn host_page_size() -> anyhow::Result<NonZeroU64> {
    // SAFETY: Calling sysconf with _SC_PAGESIZE has no memory-safety requirements.
    let raw_page_size = unsafe { libc::sysconf(libc::_SC_PAGESIZE) };
    u64::try_from(raw_page_size)
        .ok()
        .and_then(NonZeroU64::new)
        .filter(|page_size| page_size.get().is_power_of_two())
        .context("Invalid host page size")
}

fn dirty_bitmap_to_range_table(
    vm_dirty_log: &hypervisor::DirtyLog,
    vmm_dirty_bitmap: &[u64],
    vmm_bytes_per_bit: NonZeroU64,
    start_addr: u64,
    memory_size: u64,
) -> anyhow::Result<MemoryRangeTable> {
    let bytes_per_bit = vm_dirty_log.bytes_per_bit;
    if bytes_per_bit != vmm_bytes_per_bit {
        return Err(anyhow!(
            "Dirty bitmap granularity mismatch: VM={} VMM={}",
            bytes_per_bit,
            vmm_bytes_per_bit
        ));
    }
    if !bytes_per_bit.get().is_power_of_two() {
        return Err(anyhow!("Dirty bitmap granularity is not a power of two"));
    }

    let bytes_per_bit = bytes_per_bit.get();
    if memory_size == 0 || !memory_size.is_multiple_of(bytes_per_bit) {
        return Err(anyhow!(
            "Dirty memory size {memory_size} is not aligned to bitmap granularity {bytes_per_bit}"
        ));
    }
    if !start_addr.is_multiple_of(bytes_per_bit) {
        return Err(anyhow!(
            "Dirty memory GPA {start_addr:#x} is not aligned to bitmap granularity {bytes_per_bit}"
        ));
    }
    start_addr
        .checked_add(memory_size)
        .context("Dirty memory range overflows guest address space")?;

    let page_count = memory_size / bytes_per_bit;
    let expected_words = usize::try_from(page_count.div_ceil(u64::BITS as u64))
        .context("Dirty bitmap word count does not fit usize")?;
    if vm_dirty_log.bitmap.len() != expected_words || vmm_dirty_bitmap.len() != expected_words {
        return Err(anyhow!(
            "Dirty bitmap word count mismatch: expected={expected_words} VM={} VMM={}",
            vm_dirty_log.bitmap.len(),
            vmm_dirty_bitmap.len()
        ));
    }

    let dirty_bitmap = vm_dirty_log
        .bitmap
        .iter()
        .zip(vmm_dirty_bitmap.iter())
        .map(|(vm, vmm)| vm | vmm)
        .collect::<Vec<_>>();

    let tail_bits = (page_count % u64::BITS as u64) as u32;
    if tail_bits != 0 {
        let valid_mask = (1u64 << tail_bits) - 1;
        if let Some(last_word) = dirty_bitmap.last()
            && last_word & !valid_mask != 0
        {
            return Err(anyhow!("Dirty bitmap contains bits outside the memory region"));
        }
    }

    Ok(MemoryRangeTable::from_dirty_bitmap(
        dirty_bitmap,
        start_addr,
        bytes_per_bit,
    ))
}

impl Migratable for MemoryManager {
    // Start the dirty log in the hypervisor (kvm/mshv).
""",
)

replace_once(
    "vmm/src/memory_manager.rs",
    """    fn dirty_log(&mut self) -> result::Result<MemoryRangeTable, MigratableError> {
        let mut table = MemoryRangeTable::default();
        for r in &self.guest_ram_mappings {
            let vm_dirty_bitmap = self
                .vm
                .get_dirty_log(r.slot, r.gpa, r.size)
""",
    """    fn dirty_log(&mut self) -> result::Result<MemoryRangeTable, MigratableError> {
        let mut table = MemoryRangeTable::default();
        let vmm_bytes_per_bit = host_page_size()
            .context("Error getting VMM dirty bitmap page size")
            .map_err(MigratableError::MigrateSend)?;
        for r in &self.guest_ram_mappings {
            let vm_dirty_log = self
                .vm
                .get_dirty_log(r.slot, r.gpa, r.size)
""",
)

replace_once(
    "vmm/src/memory_manager.rs",
    """            let dirty_bitmap = vm_dirty_bitmap
                .iter()
                .zip(vmm_dirty_bitmap.iter())
                .map(|(x, y)| x | y);

            let sub_table = MemoryRangeTable::from_dirty_bitmap(dirty_bitmap, r.gpa, 4096);
""",
    """            let sub_table = dirty_bitmap_to_range_table(
                &vm_dirty_log,
                &vmm_dirty_bitmap,
                vmm_bytes_per_bit,
                r.gpa,
                r.size,
            )
            .context("Error combining VM and VMM dirty logs")
            .map_err(MigratableError::MigrateSend)?;
""",
)

memory_manager = Path("vmm/src/memory_manager.rs")
memory_manager.write_text(
    memory_manager.read_text()
    + r'''

#[cfg(test)]
mod dirty_log_tests {
    use std::num::NonZeroU64;

    use hypervisor::DirtyLog;

    use super::dirty_bitmap_to_range_table;

    const BASE_GPA: u64 = 0x4000_0000;

    fn page_size(value: u64) -> NonZeroU64 {
        NonZeroU64::new(value).unwrap()
    }

    fn dirty_log(bitmap: Vec<u64>, bytes_per_bit: u64) -> DirtyLog {
        DirtyLog {
            bitmap,
            bytes_per_bit: page_size(bytes_per_bit),
        }
    }

    #[test]
    fn test_dirty_log_page_granules() {
        for (bytes_per_bit, expected_gpa) in [
            (0x1000, 0x4000_1000),
            (0x4000, 0x4000_4000),
            (0x1_0000, 0x4001_0000),
        ] {
            let table = dirty_bitmap_to_range_table(
                &dirty_log(vec![0b10], bytes_per_bit),
                &[0],
                page_size(bytes_per_bit),
                BASE_GPA,
                bytes_per_bit * 8,
            )
            .unwrap();
            assert_eq!(table.regions().len(), 1);
            assert_eq!(table.regions()[0].gpa, expected_gpa);
            assert_eq!(table.regions()[0].length, bytes_per_bit);
        }
    }

    #[test]
    fn test_dirty_log_combines_sources_and_coalesces() {
        let bytes_per_bit = 0x4000;
        let table = dirty_bitmap_to_range_table(
            &dirty_log(vec![0b0010], bytes_per_bit),
            &[0b0100],
            page_size(bytes_per_bit),
            BASE_GPA,
            bytes_per_bit * 8,
        )
        .unwrap();
        assert_eq!(
            table.regions(),
            &[vm_migration::protocol::MemoryRange {
                gpa: 0x4000_4000,
                length: 0x8000,
            }]
        );
    }

    #[test]
    fn test_dirty_log_coalesces_across_bitmap_words() {
        let bytes_per_bit = 0x4000;
        let table = dirty_bitmap_to_range_table(
            &dirty_log(vec![1u64 << 63, 0], bytes_per_bit),
            &[0, 1],
            page_size(bytes_per_bit),
            BASE_GPA,
            bytes_per_bit * 65,
        )
        .unwrap();
        assert_eq!(
            table.regions(),
            &[vm_migration::protocol::MemoryRange {
                gpa: 0x403f_0000,
                length: 0x8000,
            }]
        );
    }

    #[test]
    fn test_dirty_log_rejects_granularity_mismatch() {
        let error = dirty_bitmap_to_range_table(
            &dirty_log(vec![0b10], 0x1000),
            &[0b10],
            page_size(0x4000),
            BASE_GPA,
            0x4000 * 8,
        )
        .unwrap_err();
        assert!(error.to_string().contains("granularity mismatch"));
    }

    #[test]
    fn test_dirty_log_rejects_word_count_mismatch() {
        let bytes_per_bit = 0x4000;
        let error = dirty_bitmap_to_range_table(
            &dirty_log(vec![0, 0], bytes_per_bit),
            &[0],
            page_size(bytes_per_bit),
            BASE_GPA,
            bytes_per_bit * 65,
        )
        .unwrap_err();
        assert!(error.to_string().contains("word count mismatch"));
    }

    #[test]
    fn test_dirty_log_rejects_bits_outside_region() {
        let bytes_per_bit = 0x4000;
        let error = dirty_bitmap_to_range_table(
            &dirty_log(vec![1 << 2], bytes_per_bit),
            &[0],
            page_size(bytes_per_bit),
            BASE_GPA,
            bytes_per_bit * 2,
        )
        .unwrap_err();
        assert!(error.to_string().contains("outside the memory region"));
    }

    #[test]
    fn test_dirty_log_rejects_invalid_alignment_and_overflow() {
        let invalid_granule = DirtyLog {
            bitmap: vec![0],
            bytes_per_bit: page_size(3),
        };
        assert!(
            dirty_bitmap_to_range_table(
                &invalid_granule,
                &[0],
                page_size(3),
                BASE_GPA,
                3 * 8,
            )
            .unwrap_err()
            .to_string()
            .contains("power of two")
        );

        let bytes_per_bit = 0x4000;
        assert!(
            dirty_bitmap_to_range_table(
                &dirty_log(vec![0], bytes_per_bit),
                &[0],
                page_size(bytes_per_bit),
                BASE_GPA,
                0x5000,
            )
            .unwrap_err()
            .to_string()
            .contains("not aligned")
        );
        assert!(
            dirty_bitmap_to_range_table(
                &dirty_log(vec![0], bytes_per_bit),
                &[0],
                page_size(bytes_per_bit),
                BASE_GPA + 1,
                bytes_per_bit * 8,
            )
            .unwrap_err()
            .to_string()
            .contains("not aligned")
        );

        let bytes_per_bit = 0x1000;
        assert!(
            dirty_bitmap_to_range_table(
                &dirty_log(vec![0], bytes_per_bit),
                &[0],
                page_size(bytes_per_bit),
                u64::MAX - 0x1fff,
                0x4000,
            )
            .unwrap_err()
            .to_string()
            .contains("overflows")
        );
    }
}
'''
)
