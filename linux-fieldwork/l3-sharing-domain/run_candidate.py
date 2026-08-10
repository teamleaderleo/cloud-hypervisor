#!/usr/bin/env python3
import subprocess
from pathlib import Path

MAX_BOOT_COMMIT = "ea179f3c934efcb29eea5c482ce72ba4c0389fbc"
MAX_BOOT_RUNNER_PATH = "linux-fieldwork/aarch64-max-boot-fdt/run_candidate.py"
MAX_BOOT_RUNNER_BLOB = "9c78de564f521a7cfb0e18b9a1db873e784bfa0e"
MAX_BOOT_PATCH_PATH = "linux-fieldwork/aarch64-max-boot-fdt/candidate.patch"
MAX_BOOT_PATCH_BLOB = "c0fdacec33e6e2080118b568ed1668be5cea492f"


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def output(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def materialize(commit: str, source_path: str, destination: Path, expected_blob: str) -> Path:
    content = subprocess.run(
        ["git", "show", f"{commit}:{source_path}"],
        check=True,
        capture_output=True,
    ).stdout
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    actual = output("git", "hash-object", str(destination))
    if actual != expected_blob:
        raise RuntimeError(f"{source_path}: expected blob {expected_blob}, found {actual}")
    return destination


run("git", "fetch", "--no-tags", "origin", "linux-fieldwork/aarch64-max-boot-fdt")
runner = materialize(
    MAX_BOOT_COMMIT,
    MAX_BOOT_RUNNER_PATH,
    Path("/tmp/aarch64-max-boot-runner.py"),
    MAX_BOOT_RUNNER_BLOB,
)
materialize(
    MAX_BOOT_COMMIT,
    MAX_BOOT_PATCH_PATH,
    Path(MAX_BOOT_PATCH_PATH),
    MAX_BOOT_PATCH_BLOB,
)
run("python3", str(runner))

# Freeze exact #547 after its runner has already committed exact #543 v2 and #546.
run("git", "add", "vmm/src/config.rs")
run(
    "git",
    "-c",
    "user.name=Linux Fieldwork CI",
    "-c",
    "user.email=linux-fieldwork@example.invalid",
    "commit",
    "-m",
    "ci: apply validated AArch64 max-vs-boot prerequisite",
)
Path(MAX_BOOT_PATCH_PATH).unlink()
try:
    Path("linux-fieldwork/aarch64-max-boot-fdt").rmdir()
except OSError:
    pass

cache_path = Path("arch/src/aarch64/cache.rs")
cache = cache_path.read_text()
old = '''fn read_common_cache_topology_from(
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
'''
new = '''fn read_l3_sharing_domain(cache_path: &Path) -> Result<Option<String>> {
    let path = cache_property_path(cache_path, CacheLevel::L3, "shared_cpu_list");
    Ok(read_optional_property(&path)?
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty()))
}

fn read_common_cache_topology_from(
    cpu_sysfs_path: &Path,
    host_cpus: &[usize],
) -> Result<Option<CacheTopologyInfo>> {
    let mut common = None;
    let mut l3_domain = None;
    let mut l3_domain_mismatch = false;

    for host_cpu in host_cpus {
        let cache_path = cpu_sysfs_path.join(format!("cpu{host_cpu}/cache"));
        let Some(current) = read_cache_topology_from(&cache_path)? else {
            warn!(
                "Cache topology is unavailable for eligible host CPU {host_cpu}; omitting guest cache information."
            );
            return Ok(None);
        };

        if current.l3_cache_size != 0 && current.l3_cache_shared {
            let Some(current_domain) = read_l3_sharing_domain(&cache_path)? else {
                l3_domain_mismatch = true;
                continue;
            };
            match &l3_domain {
                None => l3_domain = Some(current_domain),
                Some(expected) if *expected == current_domain => {}
                Some(_) => l3_domain_mismatch = true,
            }
        }

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

    if l3_domain_mismatch {
        warn!(
            "Eligible host CPUs span multiple L3 cache sharing domains; omitting guest L3 cache information."
        );
        if let Some(info) = &mut common {
            info.l3_cache_size = 0;
            info.l3_cache_line_size = 0;
            info.l3_cache_sets = 0;
            info.l3_cache_shared = false;
        }
    }

    Ok(common)
}
'''
if old not in cache:
    raise RuntimeError("common cache topology selector anchor changed")
cache = cache.replace(old, new, 1)

tests = r'''

    fn write_l3_domain_fixture(cache_path: &Path, cpu: usize, l3_domain: &str) {
        fs::create_dir_all(cache_path).unwrap();
        write_identity(cache_path, 0, 1, "Data", "64K");
        write_identity(cache_path, 1, 1, "Instruction", "64K");
        write_identity(cache_path, 2, 2, "Unified", "512K");
        write_identity(cache_path, 3, 3, "Unified", "2048K");
        write_property(cache_path, 2, "shared_cpu_list", &format!("{cpu}\n"));
        write_property(cache_path, 3, "shared_cpu_list", l3_domain);
    }

    #[test]
    fn test_common_topology_preserves_one_l3_sharing_domain() {
        let temp = TestDir::new();
        let host_cpus: Vec<usize> = (0..4).collect();
        for cpu in 0..4 {
            let cache_path = temp.path().join(format!("cpu{cpu}/cache"));
            write_l3_domain_fixture(&cache_path, cpu, "0-3\n");
        }

        let info = read_common_cache_topology_from(temp.path(), &host_cpus)
            .unwrap()
            .unwrap();
        assert_eq!(info.l2_cache_size, 512 * 1024);
        assert_eq!(info.l3_cache_size, 2048 * 1024);
        assert!(!info.l2_cache_shared);
        assert!(info.l3_cache_shared);
    }

    #[test]
    fn test_common_topology_omits_l3_across_distinct_sharing_domains() {
        let temp = TestDir::new();
        let host_cpus: Vec<usize> = (0..8).collect();
        for cpu in 0..8 {
            let cache_path = temp.path().join(format!("cpu{cpu}/cache"));
            let l3_domain = if cpu < 4 { "0-3\n" } else { "4-7\n" };
            write_l3_domain_fixture(&cache_path, cpu, l3_domain);
        }

        let info = read_common_cache_topology_from(temp.path(), &host_cpus)
            .unwrap()
            .unwrap();
        assert_eq!(info.l1_d_cache_size, 64 * 1024);
        assert_eq!(info.l1_i_cache_size, 64 * 1024);
        assert_eq!(info.l2_cache_size, 512 * 1024);
        assert!(!info.l2_cache_shared);
        assert_eq!(info.l3_cache_size, 0);
        assert_eq!(info.l3_cache_line_size, 0);
        assert_eq!(info.l3_cache_sets, 0);
        assert!(!info.l3_cache_shared);
    }
'''
if not cache.endswith("\n}\n"):
    raise RuntimeError("cache.rs test module ending changed")
cache_path.write_text(cache[:-3] + tests + "\n}\n")
run("cargo", "+nightly", "fmt", "--all")
print("l3-sharing-domain-prerequisites-applied")
print("l3-sharing-domain-candidate-applied")
