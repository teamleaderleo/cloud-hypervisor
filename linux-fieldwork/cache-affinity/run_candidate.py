#!/usr/bin/env python3
import subprocess
from pathlib import Path

EXPECTED_BLOBS = {
    "arch/src/aarch64/cache.rs": "9200c59627beba0e6366b5105d2fe51a312efaed",
    "arch/src/aarch64/fdt.rs": "887d9edfe02056ab2567e4252fb6172236e1f770",
    "arch/src/aarch64/mod.rs": "c53e4829b48c2bcd294642f86e501a6b85dfe680",
    "vmm/src/cpu.rs": "5d9499878b04f7c0fb53cece5768988ceb439d25",
    "vmm/src/acpi.rs": "6ac7666ebdc49c67fbc6233c135e8645f7e64e0f",
    "vmm/src/vm.rs": "12a9fe0ad7068df7b26082b32de65d6f54b33d04",
}

PATCHES = [
    (
        "linux-fieldwork/acpi-error-propagation",
        "0a2f55acbd23b7f44899a69132a4236ef9240027",
        "linux-fieldwork/acpi-errors/candidate.patch",
        "034cebd92cf31e3b415cdd3d205035b96cd9c1fb",
        "/tmp/acpi.patch",
        ["vmm/src/acpi.rs", "vmm/src/vm.rs"],
        "ci: apply validated ACPI prerequisite",
    ),
    (
        "linux-fieldwork/cache-runtime-errors",
        "044a728ddf5d9dbb00eba04a6df6679e84521441",
        "linux-fieldwork/cache-errors/candidate.patch",
        "f381a777ea3343c33d2dd0bdbde067a2a91cc692",
        "/tmp/cache-parser.patch",
        None,
        None,
    ),
    (
        "linux-fieldwork/cache-runtime-errors",
        "044a728ddf5d9dbb00eba04a6df6679e84521441",
        "linux-fieldwork/cache-errors/propagation.patch",
        "9dab1cadb2d48c919fc5239c974a30e594a9a6c4",
        "/tmp/cache-propagation.patch",
        [
            "arch/src/aarch64/cache.rs",
            "arch/src/aarch64/fdt.rs",
            "arch/src/aarch64/mod.rs",
            "vmm/src/acpi.rs",
            "vmm/src/cpu.rs",
        ],
        "ci: apply validated cache error prerequisite",
    ),
    (
        "linux-fieldwork/cache-index-portability",
        "7713a59e21c48262843da100087454dae3c0772d",
        "linux-fieldwork/cache-index/candidate.patch",
        "4550e55faba24d0c1ffc9f7be7a11596d5866b8a",
        "/tmp/cache-index.patch",
        ["arch/src/aarch64/cache.rs"],
        "ci: apply validated cache index prerequisite",
    ),
    (
        "linux-fieldwork/cache-sharing-pptt",
        "b3c66237ed59f6d7ac521d821f2f9bf138868ead",
        "linux-fieldwork/cache-sharing/candidate.patch",
        "bb45c3741cdebecd183cd05b769dfd56da4f80ab",
        "/tmp/cache-sharing.patch",
        ["vmm/src/cpu.rs"],
        "ci: apply validated cache sharing prerequisite",
    ),
]


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def output(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def materialize(commit: str, source_path: str, destination: str, expected_blob: str) -> Path:
    content = subprocess.run(
        ["git", "show", f"{commit}:{source_path}"],
        check=True,
        capture_output=True,
    ).stdout
    path = Path(destination)
    path.write_bytes(content)
    actual = output("git", "hash-object", str(path))
    if actual != expected_blob:
        raise RuntimeError(
            f"{source_path}: expected prerequisite blob {expected_blob}, found {actual}"
        )
    return path


for path, expected in EXPECTED_BLOBS.items():
    actual = output("git", "hash-object", path)
    if actual != expected:
        raise RuntimeError(f"{path}: expected source blob {expected}, found {actual}")

for branch in sorted({entry[0] for entry in PATCHES}):
    run("git", "fetch", "--no-tags", "--depth=100", "origin", branch)

for _branch, commit, source_path, expected_blob, destination, commit_files, message in PATCHES:
    patch = materialize(commit, source_path, destination, expected_blob)
    run("git", "apply", "--check", str(patch))
    run("git", "apply", str(patch))
    if commit_files is None:
        continue
    run("cargo", "+nightly", "fmt", "--all", "--", "--check")
    run("git", "add", *commit_files)
    run(
        "git",
        "-c",
        "user.name=Linux Fieldwork CI",
        "-c",
        "user.email=linux-fieldwork@example.invalid",
        "commit",
        "-m",
        message,
    )

# arch/src/aarch64/cache.rs: compare exact representable topology across the
# host CPUs selected by CpuManager.
cache_file = Path("arch/src/aarch64/cache.rs")
cache = cache_file.read_text()
cache = cache.replace(
    'const CACHE_SYSFS_PATH: &str = "/sys/devices/system/cpu/cpu0/cache";\n',
    'const CACHE_SYSFS_PATH: &str = "/sys/devices/system/cpu/cpu0/cache";\n'
    'const CPU_SYSFS_PATH: &str = "/sys/devices/system/cpu";\n',
    1,
)
cache = cache.replace(
    "#[derive(Default, Copy, Clone, Debug)]\npub struct CacheTopologyInfo {",
    "#[derive(Default, Copy, Clone, Debug, Eq, PartialEq)]\npub struct CacheTopologyInfo {",
    1,
)
read_anchor = '''/// Reads cache topology information from sysfs for cpu0.
pub fn read_cache_topology() -> Result<Option<CacheTopologyInfo>> {
    read_cache_topology_from(Path::new(CACHE_SYSFS_PATH))
}
'''
common_helpers = r'''

fn read_common_cache_topology_from(
    cpu_sysfs_path: &Path,
    host_cpus: &[usize],
) -> Result<Option<CacheTopologyInfo>> {
    let mut common = None;

    for host_cpu in host_cpus {
        let cache_path = cpu_sysfs_path.join(format!("cpu{host_cpu}/cache"));
        let Some(current) = read_cache_topology_from(&cache_path)? else {
            warn!(
                "Cache topology is unavailable for eligible host CPU {host_cpu}; omitting guest cache information."
            );
            return Ok(None);
        };

        match common {
            None => common = Some(current),
            Some(expected) if expected == current => {}
            Some(_) => {
                warn!(
                    "Cache topology differs across eligible host CPUs; omitting guest cache information."
                );
                return Ok(None);
            }
        }
    }

    Ok(common)
}

/// Reads one common representable cache topology for the eligible host CPUs.
pub fn read_common_cache_topology(host_cpus: &[usize]) -> Result<Option<CacheTopologyInfo>> {
    read_common_cache_topology_from(Path::new(CPU_SYSFS_PATH), host_cpus)
}
'''
if read_anchor not in cache:
    raise RuntimeError("cache topology public reader anchor changed")
cache = cache.replace(read_anchor, read_anchor + common_helpers, 1)

cache_tests = r'''

    #[test]
    fn test_common_cache_topology_preserves_matching_cpu_roots() {
        let temp = TestDir::new();
        for cpu in [0, 4] {
            let cache_path = temp.path().join(format!("cpu{cpu}/cache"));
            fs::create_dir_all(&cache_path).unwrap();
            write_identity(&cache_path, 0, 1, "Data", "64K");
            write_identity(&cache_path, 1, 1, "Instruction", "64K");
            write_identity(&cache_path, 2, 2, "Unified", "1024K");
            write_identity(&cache_path, 3, 3, "Unified", "4096K");
        }

        let info = read_common_cache_topology_from(temp.path(), &[0, 4])
            .unwrap()
            .unwrap();
        assert_eq!(info.l1_d_cache_size, 64 * 1024);
        assert_eq!(info.l2_cache_size, 1024 * 1024);
    }

    #[test]
    fn test_common_cache_topology_omits_different_cpu_roots() {
        let temp = TestDir::new();
        let cpu0_cache = temp.path().join("cpu0/cache");
        let cpu4_cache = temp.path().join("cpu4/cache");
        fs::create_dir_all(&cpu0_cache).unwrap();
        fs::create_dir_all(&cpu4_cache).unwrap();

        write_identity(&cpu0_cache, 0, 1, "Data", "32K");
        write_identity(&cpu0_cache, 1, 1, "Instruction", "32K");
        write_identity(&cpu0_cache, 2, 2, "Unified", "256K");
        write_identity(&cpu0_cache, 3, 3, "Unified", "4096K");

        write_identity(&cpu4_cache, 0, 1, "Data", "64K");
        write_identity(&cpu4_cache, 1, 1, "Instruction", "64K");
        write_identity(&cpu4_cache, 2, 2, "Unified", "1024K");
        write_identity(&cpu4_cache, 3, 3, "Unified", "4096K");

        assert!(
            read_common_cache_topology_from(temp.path(), &[0, 4])
                .unwrap()
                .is_none()
        );
    }
'''
if not cache.endswith("\n}\n"):
    raise RuntimeError("cache.rs test module ending changed")
cache = cache[:-3] + cache_tests + "\n}\n"
cache_file.write_text(cache)

# vmm/src/cpu.rs: derive the host CPU execution set from configured affinity
# and the VMM thread's scheduler affinity for unpinned boot vCPUs.
cpu_file = Path("vmm/src/cpu.rs")
cpu = cpu_file.read_text()
cpu = cpu.replace(
    "use std::collections::BTreeMap;\n",
    "use std::collections::BTreeMap;\n#[cfg(target_arch = \"aarch64\")]\nuse std::collections::BTreeSet;\n",
    1,
)
cpu = cpu.replace(
    "use arch::aarch64::cache::{CacheTopologyInfo, read_cache_topology};",
    "use arch::aarch64::cache::{CacheTopologyInfo, read_common_cache_topology};",
    1,
)
error_anchor = '''    #[cfg(target_arch = "aarch64")]
    #[error("Failed to read cache topology")]
    CacheTopology(#[source] arch::aarch64::cache::Error),
'''
error_replacement = '''    #[cfg(target_arch = "aarch64")]
    #[error("Failed to read cache topology")]
    CacheTopology(#[source] arch::aarch64::cache::Error),

    #[cfg(target_arch = "aarch64")]
    #[error("Failed to read host CPU affinity")]
    HostCpuAffinity(#[source] io::Error),
'''
if error_anchor not in cpu:
    raise RuntimeError("CpuManager cache error anchor changed")
cpu = cpu.replace(error_anchor, error_replacement, 1)

struct_anchor = "pub struct CpuManager {\n"
affinity_helpers = r'''
#[cfg(target_arch = "aarch64")]
fn process_host_cpus() -> Result<Vec<usize>> {
    // SAFETY: all zeros is a valid cpu_set_t bit pattern.
    let mut cpuset: libc::cpu_set_t = unsafe { zeroed() };
    // SAFETY: cpuset points to writable storage of the advertised size.
    let ret = unsafe {
        libc::sched_getaffinity(
            0,
            std::mem::size_of::<libc::cpu_set_t>(),
            &mut cpuset,
        )
    };
    if ret != 0 {
        return Err(Error::HostCpuAffinity(io::Error::last_os_error()));
    }

    let mut host_cpus = Vec::new();
    for host_cpu in 0..libc::CPU_SETSIZE as usize {
        // SAFETY: host_cpu is bounded by CPU_SETSIZE and cpuset is initialized.
        if unsafe { libc::CPU_ISSET(host_cpu, &cpuset) } {
            host_cpus.push(host_cpu);
        }
    }
    Ok(host_cpus)
}

#[cfg(target_arch = "aarch64")]
fn cache_host_cpus_from_affinity(
    boot_vcpus: u32,
    affinity: &BTreeMap<u32, Box<[usize]>>,
    default_host_cpus: &[usize],
) -> Vec<usize> {
    let mut host_cpus = BTreeSet::new();
    for vcpu_id in 0..boot_vcpus {
        if let Some(vcpu_host_cpus) = affinity.get(&vcpu_id) {
            host_cpus.extend(vcpu_host_cpus.iter().copied());
        } else {
            host_cpus.extend(default_host_cpus.iter().copied());
        }
    }
    host_cpus.into_iter().collect()
}

'''
if struct_anchor not in cpu:
    raise RuntimeError("CpuManager struct anchor changed")
cpu = cpu.replace(struct_anchor, affinity_helpers + struct_anchor, 1)

pptt_anchor = '''    #[cfg(target_arch = "aarch64")]
    pub fn create_pptt(&self) -> Result<PPTT> {
'''
cache_method = r'''    #[cfg(target_arch = "aarch64")]
    pub fn cache_host_cpus(&self) -> Result<Vec<usize>> {
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

'''
if pptt_anchor not in cpu:
    raise RuntimeError("create_pptt anchor changed")
cpu = cpu.replace(pptt_anchor, cache_method + pptt_anchor, 1)
cpu = cpu.replace(
    "let cache_info = read_cache_topology().map_err(Error::CacheTopology)?;",
    "let cache_host_cpus = self.cache_host_cpus()?;\n        let cache_info =\n            read_common_cache_topology(&cache_host_cpus).map_err(Error::CacheTopology)?;",
    1,
)

cpu_tests = r'''

#[cfg(all(test, target_arch = "aarch64"))]
mod cache_affinity_tests {
    use super::*;

    #[test]
    fn test_cache_host_cpus_uses_fully_pinned_execution_set() {
        let affinity = BTreeMap::from([
            (0, vec![4, 5].into_boxed_slice()),
            (1, vec![5, 6].into_boxed_slice()),
        ]);
        assert_eq!(
            cache_host_cpus_from_affinity(2, &affinity, &[0, 1, 2, 3]),
            vec![4, 5, 6]
        );
    }

    #[test]
    fn test_cache_host_cpus_adds_default_set_for_unpinned_vcpu() {
        let affinity = BTreeMap::from([(0, vec![4, 5].into_boxed_slice())]);
        assert_eq!(
            cache_host_cpus_from_affinity(2, &affinity, &[0, 1, 2, 3]),
            vec![0, 1, 2, 3, 4, 5]
        );
    }
}
'''
cpu += cpu_tests
cpu_file.write_text(cpu)

# arch/src/aarch64/fdt.rs: consume the selector chosen by CpuManager instead of
# independently rereading host CPU0.
fdt_file = Path("arch/src/aarch64/fdt.rs")
fdt = fdt_file.read_text()
fdt = fdt.replace(
    "use super::cache::{CacheTopologyInfo, read_cache_topology};",
    "use super::cache::{CacheTopologyInfo, read_common_cache_topology};",
    1,
)
fdt = fdt.replace(
    "    vcpu_topology: Option<(u16, u16, u16, u16)>,\n    device_info:",
    "    vcpu_topology: Option<(u16, u16, u16, u16)>,\n    cache_host_cpus: &[usize],\n    device_info:",
    1,
)
fdt = fdt.replace(
    "    create_cpu_nodes(&mut fdt, vcpu_mpidr, vcpu_topology, numa_nodes)?;",
    "    create_cpu_nodes(\n        &mut fdt,\n        vcpu_mpidr,\n        vcpu_topology,\n        cache_host_cpus,\n        numa_nodes,\n    )?;",
    1,
)
fdt = fdt.replace(
    "    vcpu_topology: Option<(u16, u16, u16, u16)>,\n    numa_nodes: &NumaNodes,\n) -> Result<()> {",
    "    vcpu_topology: Option<(u16, u16, u16, u16)>,\n    cache_host_cpus: &[usize],\n    numa_nodes: &NumaNodes,\n) -> Result<()> {",
    1,
)
fdt = fdt.replace(
    "let cache_info = read_cache_topology().map_err(Error::CacheTopology)?;",
    "let cache_info =\n        read_common_cache_topology(cache_host_cpus).map_err(Error::CacheTopology)?;",
    1,
)
fdt_file.write_text(fdt)

# arch/src/aarch64/mod.rs: thread the selected host CPU set into FDT creation.
arch_file = Path("arch/src/aarch64/mod.rs")
arch = arch_file.read_text()
arch = arch.replace(
    "    vcpu_topology: Option<(u16, u16, u16, u16)>,\n    device_info:",
    "    vcpu_topology: Option<(u16, u16, u16, u16)>,\n    cache_host_cpus: &[usize],\n    device_info:",
    1,
)
arch = arch.replace(
    "        vcpu_topology,\n        device_info,",
    "        vcpu_topology,\n        cache_host_cpus,\n        device_info,",
    1,
)
arch_file.write_text(arch)

# vmm/src/vm.rs: obtain the execution set from CpuManager and use it for FDT.
vm_file = Path("vmm/src/vm.rs")
vm = vm_file.read_text()
old_reads = '''        let vcpu_mpidrs = self.cpu_manager.lock().unwrap().get_mpidrs();
        let vcpu_topology = self.cpu_manager.lock().unwrap().get_vcpu_topology();
'''
new_reads = '''        let (vcpu_mpidrs, vcpu_topology, cache_host_cpus) = {
            let cpu_manager = self.cpu_manager.lock().unwrap();
            (
                cpu_manager.get_mpidrs(),
                cpu_manager.get_vcpu_topology(),
                cpu_manager.cache_host_cpus().map_err(Error::CpuManager)?,
            )
        };
'''
if old_reads not in vm:
    raise RuntimeError("AArch64 VM CpuManager read anchor changed")
vm = vm.replace(old_reads, new_reads, 1)
vm = vm.replace(
    "            vcpu_topology,\n            device_info,",
    "            vcpu_topology,\n            &cache_host_cpus,\n            device_info,",
    1,
)
vm_file.write_text(vm)

run("cargo", "+nightly", "fmt", "--all")
print("cache-affinity-prerequisites-applied")
print("cache-affinity-candidate-applied")
