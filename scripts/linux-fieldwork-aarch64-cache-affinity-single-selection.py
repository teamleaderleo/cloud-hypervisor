from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{label} drifted: expected one match, found {text.count(old)}")
    return text.replace(old, new, 1)


# arch/src/aarch64/cache.rs
p = Path("arch/src/aarch64/cache.rs")
s = p.read_text()
s = replace_once(
    s,
    'const CACHE_SYSFS_PATH: &str = "/sys/devices/system/cpu/cpu0/cache";\n',
    'const CACHE_SYSFS_PATH: &str = "/sys/devices/system/cpu/cpu0/cache";\nconst CPU_SYSFS_PATH: &str = "/sys/devices/system/cpu";\n',
    "cache sysfs constant",
)
s = replace_once(
    s,
    "#[derive(Default, Copy, Clone, Debug)]\npub struct CacheTopologyInfo {",
    "#[derive(Default, Copy, Clone, Debug, Eq, PartialEq)]\npub struct CacheTopologyInfo {",
    "cache topology derive",
)
cache_reader_anchor = """/// Reads cache topology information from sysfs for cpu0.
pub fn read_cache_topology() -> Result<Option<CacheTopologyInfo>> {
    read_cache_topology_from(Path::new(CACHE_SYSFS_PATH))
}
"""
cache_reader_replacement = """fn read_l3_sharing_domain(cache_path: &Path) -> Result<Option<String>> {
    let Some(indices) = read_cache_indices(cache_path)? else {
        return Ok(None);
    };
    let Some(index) = indices.l3 else {
        return Ok(None);
    };
    let path = cache_property_path(cache_path, index, "shared_cpu_list");
    Ok(read_optional_property(&path)?
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty()))
}

fn read_common_cache_topology_from(
    cpu_sysfs_path: &Path,
    host_cpus: &[usize],
) -> Result<Option<CacheTopologyInfo>> {
    if host_cpus.is_empty() {
        return Ok(None);
    }

    let mut common = None;
    let mut l3_domain = None;
    let mut l3_domain_mismatch = false;

    for host_cpu in host_cpus {
        let cache_path = cpu_sysfs_path.join(format!("cpu{host_cpu}/cache"));
        let Some(current) = read_cache_topology_from(&cache_path)? else {
            warn!("Cache topology is unavailable for eligible host CPU {host_cpu}; omitting guest cache topology.");
            return Ok(None);
        };

        if current.l3_cache_size != 0 && current.l3_cache_shared {
            match read_l3_sharing_domain(&cache_path)? {
                Some(current_domain) => match &l3_domain {
                    None => l3_domain = Some(current_domain),
                    Some(expected) if *expected == current_domain => {}
                    Some(_) => l3_domain_mismatch = true,
                },
                None => l3_domain_mismatch = true,
            }
        }

        match common {
            None => common = Some(current),
            Some(expected) if expected == current => {}
            Some(_) => {
                warn!("Eligible host CPUs expose different cache topologies; omitting guest cache topology.");
                return Ok(None);
            }
        }
    }

    if l3_domain_mismatch {
        warn!("Eligible host CPUs span multiple L3 sharing domains; omitting guest L3 cache information.");
        if let Some(info) = &mut common {
            info.l3_cache_size = 0;
            info.l3_cache_line_size = 0;
            info.l3_cache_sets = 0;
            info.l3_cache_shared = false;
        }
    }

    Ok(common)
}

/// Reads cache topology information from sysfs for cpu0.
pub fn read_cache_topology() -> Result<Option<CacheTopologyInfo>> {
    read_cache_topology_from(Path::new(CACHE_SYSFS_PATH))
}

/// Reads one cache topology that is truthful for every eligible host CPU.
pub fn read_common_cache_topology(host_cpus: &[usize]) -> Result<Option<CacheTopologyInfo>> {
    read_common_cache_topology_from(Path::new(CPU_SYSFS_PATH), host_cpus)
}
"""
s = replace_once(s, cache_reader_anchor, cache_reader_replacement, "cache reader")
cache_tests_anchor = "    #[test]\n    fn test_missing_cache_root() {"
cache_tests = """    fn write_common_cpu_fixture(
        cpu_root: &Path,
        cpu: usize,
        l2_size: &str,
        l3_domain: &str,
    ) {
        let cache_path = cpu_root.join(format!("cpu{cpu}/cache"));
        write_identity(&cache_path, 0, 1, "Data");
        write_identity(&cache_path, 2, 1, "Instruction");
        write_identity(&cache_path, 5, 2, "Unified");
        write_identity(&cache_path, 9, 3, "Unified");
        for (index, size) in [(0, "64K"), (2, "64K"), (5, l2_size), (9, "2048K")] {
            write_property(&cache_path, index, "size", &format!("{size}\\n"));
            write_property(&cache_path, index, "coherency_line_size", "64\\n");
            write_property(&cache_path, index, "number_of_sets", "64\\n");
        }
        write_property(&cache_path, 5, "shared_cpu_list", &format!("{cpu}\\n"));
        write_property(&cache_path, 9, "shared_cpu_list", l3_domain);
    }

    #[test]
    fn test_common_topology_preserves_one_l3_domain_with_noncontiguous_indices() {
        let temp = TestDir::new();
        write_common_cpu_fixture(temp.path(), 0, "512K", "0-1\\n");
        write_common_cpu_fixture(temp.path(), 1, "512K", "0-1\\n");

        let info = read_common_cache_topology_from(temp.path(), &[0, 1])
            .unwrap()
            .unwrap();
        assert_eq!(info.l2_cache_size, 512 * 1024);
        assert_eq!(info.l3_cache_size, 2 * 1024 * 1024);
        assert!(info.l3_cache_shared);
    }

    #[test]
    fn test_common_topology_omits_l3_across_distinct_domains() {
        let temp = TestDir::new();
        write_common_cpu_fixture(temp.path(), 0, "512K", "0-1\\n");
        write_common_cpu_fixture(temp.path(), 2, "512K", "2-3\\n");

        let info = read_common_cache_topology_from(temp.path(), &[0, 2])
            .unwrap()
            .unwrap();
        assert_eq!(info.l2_cache_size, 512 * 1024);
        assert_eq!(info.l3_cache_size, 0);
        assert_eq!(info.l3_cache_line_size, 0);
        assert_eq!(info.l3_cache_sets, 0);
        assert!(!info.l3_cache_shared);
    }

    #[test]
    fn test_common_topology_omits_mismatched_geometry() {
        let temp = TestDir::new();
        write_common_cpu_fixture(temp.path(), 0, "512K", "0-1\\n");
        write_common_cpu_fixture(temp.path(), 1, "1024K", "0-1\\n");
        assert!(read_common_cache_topology_from(temp.path(), &[0, 1])
            .unwrap()
            .is_none());
    }

"""
s = replace_once(s, cache_tests_anchor, cache_tests + cache_tests_anchor, "cache tests")
p.write_text(s)


# vmm/src/cpu.rs
p = Path("vmm/src/cpu.rs")
s = p.read_text()
s = replace_once(
    s,
    "use std::collections::BTreeMap;\n",
    'use std::collections::BTreeMap;\n#[cfg(target_arch = "aarch64")]\nuse std::collections::BTreeSet;\n',
    "BTreeSet import",
)
s = replace_once(
    s,
    "use std::mem::zeroed;\n",
    '#[cfg(target_arch = "aarch64")]\nuse std::mem;\nuse std::mem::zeroed;\n',
    "mem import",
)
s = replace_once(
    s,
    "use arch::aarch64::cache::{CacheTopologyInfo, read_cache_topology};",
    "use arch::aarch64::cache::{CacheTopologyInfo, read_common_cache_topology};",
    "cache import",
)
cpu_error_anchor = """    #[cfg(target_arch = "aarch64")]
    #[error("Failed to read cache topology")]
    CacheTopology(#[source] arch::aarch64::cache::Error),
"""
s = replace_once(
    s,
    cpu_error_anchor,
    cpu_error_anchor
    + '\n    #[cfg(target_arch = "aarch64")]\n    #[error("Failed to read host CPU affinity")]\n    HostCpuAffinity(#[source] io::Error),\n',
    "host affinity error",
)
helpers = """#[cfg(target_arch = "aarch64")]
fn host_cpus_from_affinity_words(words: &[usize]) -> Vec<usize> {
    let bits_per_word = usize::BITS as usize;
    let mut host_cpus = Vec::new();
    for (word_index, word) in words.iter().copied().enumerate() {
        for bit in 0..bits_per_word {
            if word & (1usize << bit) != 0 {
                host_cpus.push(word_index * bits_per_word + bit);
            }
        }
    }
    host_cpus
}

#[cfg(target_arch = "aarch64")]
fn process_host_cpus() -> Result<Vec<usize>> {
    let word_size = mem::size_of::<usize>();
    let initial_words = mem::size_of::<libc::cpu_set_t>().div_ceil(word_size);
    let mut words = vec![0usize; initial_words];

    loop {
        let cpusetsize = words.len() * word_size;
        // SAFETY: `words` is writable for `cpusetsize` bytes. The kernel treats
        // the mask as opaque bytes and reports EINVAL when the buffer is too small.
        let ret = unsafe {
            libc::sched_getaffinity(0, cpusetsize, words.as_mut_ptr().cast::<libc::cpu_set_t>())
        };
        if ret == 0 {
            return Ok(host_cpus_from_affinity_words(&words));
        }

        let source = io::Error::last_os_error();
        if source.raw_os_error() != Some(libc::EINVAL) {
            return Err(Error::HostCpuAffinity(source));
        }
        words.resize(words.len() * 2, 0);
    }
}

#[cfg(target_arch = "aarch64")]
fn cache_host_cpus_from_affinity(
    boot_vcpus: u32,
    affinity: &BTreeMap<u32, Box<[usize]>>,
    default_host_cpus: &[usize],
) -> Vec<usize> {
    let mut host_cpus = BTreeSet::new();
    for vcpu_id in 0..boot_vcpus {
        match affinity.get(&vcpu_id) {
            Some(pinned) => host_cpus.extend(pinned.iter().copied()),
            None => host_cpus.extend(default_host_cpus.iter().copied()),
        }
    }
    host_cpus.into_iter().collect()
}

"""
s = replace_once(s, "pub struct CpuManager {\n", helpers + "pub struct CpuManager {\n", "CpuManager helper insertion")
s = replace_once(
    s,
    "    affinity: BTreeMap<u32, Box<[usize]>>,\n",
    '    affinity: BTreeMap<u32, Box<[usize]>>,\n    #[cfg(target_arch = "aarch64")]\n    cache_topology: Option<CacheTopologyInfo>,\n',
    "cache topology field",
)
s = replace_once(
    s,
    "            affinity,\n            dynamic,\n",
    '            affinity,\n            #[cfg(target_arch = "aarch64")]\n            cache_topology: None,\n            dynamic,\n',
    "cache topology init",
)
methods = """    #[cfg(target_arch = "aarch64")]
    fn cache_host_cpus(&self) -> Result<Vec<usize>> {
        let needs_default =
            (0..self.config.boot_vcpus).any(|vcpu_id| !self.affinity.contains_key(&vcpu_id));
        let default_host_cpus = if needs_default {
            process_host_cpus()?
        } else {
            Vec::new()
        };
        Ok(cache_host_cpus_from_affinity(
            self.config.boot_vcpus,
            &self.affinity,
            &default_host_cpus,
        ))
    }

    #[cfg(target_arch = "aarch64")]
    pub fn select_cache_topology(&mut self) -> Result<()> {
        let host_cpus = self.cache_host_cpus()?;
        self.cache_topology =
            read_common_cache_topology(&host_cpus).map_err(Error::CacheTopology)?;
        Ok(())
    }

    #[cfg(target_arch = "aarch64")]
    pub fn cache_topology(&self) -> Option<CacheTopologyInfo> {
        self.cache_topology
    }

"""
pptt_anchor = '    #[cfg(target_arch = "aarch64")]\n    fn pptt_cache_exposure('
s = replace_once(s, pptt_anchor, methods + pptt_anchor, "PPTT method insertion")
s = replace_once(
    s,
    "        let cache_info = read_cache_topology().map_err(Error::CacheTopology)?;\n",
    "        let cache_info = self.cache_topology;\n",
    "PPTT direct cache read",
)
s += """
#[cfg(all(test, target_arch = "aarch64"))]
mod cache_affinity_tests {
    use super::*;

    #[test]
    fn explicit_and_unpinned_boot_vcpus_union_eligible_host_cpus() {
        let affinity = BTreeMap::from([(0, vec![4usize, 2].into_boxed_slice())]);
        assert_eq!(
            cache_host_cpus_from_affinity(2, &affinity, &[1, 3]),
            vec![1, 2, 3, 4]
        );
    }

    #[test]
    fn affinity_for_nonboot_vcpu_does_not_affect_firmware_selection() {
        let affinity = BTreeMap::from([
            (0, vec![2usize].into_boxed_slice()),
            (3, vec![99usize].into_boxed_slice()),
        ]);
        assert_eq!(cache_host_cpus_from_affinity(1, &affinity, &[1, 3]), vec![2]);
    }

    #[test]
    fn affinity_word_decoder_handles_cpus_above_libc_cpu_set_size() {
        let mut words = vec![0usize; 32];
        let cpu = 1537usize;
        let bits = usize::BITS as usize;
        words[cpu / bits] |= 1usize << (cpu % bits);
        assert_eq!(host_cpus_from_affinity_words(&words), vec![cpu]);
    }
}
"""
p.write_text(s)


# arch/src/aarch64/fdt.rs
p = Path("arch/src/aarch64/fdt.rs")
s = p.read_text()
s = replace_once(s, "use super::cache::{CacheTopologyInfo, read_cache_topology};", "use super::cache::CacheTopologyInfo;", "FDT cache import")
s = replace_once(
    s,
    """    /// Failure in reading cache topology.
    #[error("Failure in reading cache topology")]
    CacheTopology(#[source] super::cache::Error),

""",
    "",
    "FDT cache error",
)
s = replace_once(
    s,
    "    vcpu_topology: Option<(u16, u16, u16, u16)>,\n    device_info:",
    "    vcpu_topology: Option<(u16, u16, u16, u16)>,\n    cache_info: Option<CacheTopologyInfo>,\n    device_info:",
    "create_fdt cache arg",
)
s = replace_once(
    s,
    "    create_cpu_nodes(&mut fdt, vcpu_mpidr, vcpu_topology, numa_nodes)?;",
    "    create_cpu_nodes(&mut fdt, vcpu_mpidr, vcpu_topology, cache_info, numa_nodes)?;",
    "create_cpu_nodes call",
)
s = replace_once(
    s,
    "    vcpu_topology: Option<(u16, u16, u16, u16)>,\n    numa_nodes: &NumaNodes,\n) -> Result<()> {",
    "    vcpu_topology: Option<(u16, u16, u16, u16)>,\n    cache_info: Option<CacheTopologyInfo>,\n    numa_nodes: &NumaNodes,\n) -> Result<()> {",
    "create_cpu_nodes cache arg",
)
s = replace_once(
    s,
    "    // Add cache info.\n    let cache_info = read_cache_topology().map_err(Error::CacheTopology)?;\n",
    "    // Add the cache information selected once for this boot.\n",
    "FDT direct cache read",
)
p.write_text(s)


# arch/src/aarch64/mod.rs
p = Path("arch/src/aarch64/mod.rs")
s = p.read_text()
s = replace_once(
    s,
    "    vcpu_topology: Option<(u16, u16, u16, u16)>,\n    device_info:",
    "    vcpu_topology: Option<(u16, u16, u16, u16)>,\n    cache_info: Option<cache::CacheTopologyInfo>,\n    device_info:",
    "configure_system cache arg",
)
s = replace_once(
    s,
    "        vcpu_topology,\n        device_info,",
    "        vcpu_topology,\n        cache_info,\n        device_info,",
    "configure_system cache forwarding",
)
p.write_text(s)


# vmm/src/vm.rs
p = Path("vmm/src/vm.rs")
s = p.read_text()
s = replace_once(
    s,
    "        let vcpu_mpidrs = self.cpu_manager.lock().unwrap().get_mpidrs();\n        let vcpu_topology = self.cpu_manager.lock().unwrap().get_vcpu_topology();\n",
    """        let (vcpu_mpidrs, vcpu_topology, cache_topology) = {
            let cpu_manager = self.cpu_manager.lock().unwrap();
            (
                cpu_manager.get_mpidrs(),
                cpu_manager.get_vcpu_topology(),
                cpu_manager.cache_topology(),
            )
        };
""",
    "VM firmware input snapshot",
)
s = replace_once(
    s,
    "            vcpu_topology,\n            device_info,",
    "            vcpu_topology,\n            cache_topology,\n            device_info,",
    "VM FDT cache forwarding",
)
boot_anchor = """        #[cfg(feature = "mshv")]
        {
            self.cpu_manager
                .lock()
                .unwrap()
                .set_processors_per_socket_property()
                .ok();
        }
"""
s = replace_once(
    s,
    boot_anchor,
    boot_anchor
    + '\n        #[cfg(target_arch = "aarch64")]\n        self.cpu_manager\n            .lock()\n            .unwrap()\n            .select_cache_topology()\n            .map_err(Error::CpuManager)?;\n',
    "boot-time cache selection",
)
p.write_text(s)


# vmm/src/vm_config.rs
p = Path("vmm/src/vm_config.rs")
s = p.read_text()
s = replace_once(
    s,
    '            landlock.add_rule_with_access(Path::new("/sys/devices/system/cpu/cpu0/cache"), "r")?;',
    '            landlock.add_rule_with_access(Path::new("/sys/devices/system/cpu"), "r")?;',
    "Landlock CPU sysfs scope",
)
p.write_text(s)
