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

ACPI_COMMIT = "0a2f55acbd23b7f44899a69132a4236ef9240027"
ACPI_PATH = "linux-fieldwork/acpi-errors/candidate.patch"
ACPI_BLOB = "034cebd92cf31e3b415cdd3d205035b96cd9c1fb"
CACHE_COMMIT = "044a728ddf5d9dbb00eba04a6df6679e84521441"
CACHE_PARSER_PATH = "linux-fieldwork/cache-errors/candidate.patch"
CACHE_PARSER_BLOB = "f381a777ea3343c33d2dd0bdbde067a2a91cc692"
CACHE_PROPAGATION_PATH = "linux-fieldwork/cache-errors/propagation.patch"
CACHE_PROPAGATION_BLOB = "9dab1cadb2d48c919fc5239c974a30e594a9a6c4"


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

run("git", "fetch", "--no-tags", "--depth=100", "origin", "linux-fieldwork/acpi-error-propagation")
run("git", "fetch", "--no-tags", "--depth=100", "origin", "linux-fieldwork/cache-runtime-errors")

acpi = materialize(ACPI_COMMIT, ACPI_PATH, "/tmp/acpi.patch", ACPI_BLOB)
run("git", "apply", "--check", str(acpi))
run("git", "apply", str(acpi))
run("cargo", "+nightly", "fmt", "--all", "--", "--check")
run("git", "add", "vmm/src/acpi.rs", "vmm/src/vm.rs")
run(
    "git",
    "-c",
    "user.name=Linux Fieldwork CI",
    "-c",
    "user.email=linux-fieldwork@example.invalid",
    "commit",
    "-m",
    "ci: apply validated ACPI prerequisite",
)

for source_path, destination, expected_blob in [
    (CACHE_PARSER_PATH, "/tmp/cache-parser.patch", CACHE_PARSER_BLOB),
    (CACHE_PROPAGATION_PATH, "/tmp/cache-propagation.patch", CACHE_PROPAGATION_BLOB),
]:
    patch = materialize(CACHE_COMMIT, source_path, destination, expected_blob)
    run("git", "apply", "--check", str(patch))
    run("git", "apply", str(patch))

run("cargo", "+nightly", "fmt", "--all", "--", "--check")
run(
    "git",
    "add",
    "arch/src/aarch64/cache.rs",
    "arch/src/aarch64/fdt.rs",
    "arch/src/aarch64/mod.rs",
    "vmm/src/acpi.rs",
    "vmm/src/cpu.rs",
)
run(
    "git",
    "-c",
    "user.name=Linux Fieldwork CI",
    "-c",
    "user.email=linux-fieldwork@example.invalid",
    "commit",
    "-m",
    "ci: apply validated cache error prerequisite",
)

cache_file = Path("arch/src/aarch64/cache.rs")
source = cache_file.read_text()

error_anchor = '''    #[error("Cache size in {path:?} exceeds u32 bytes")]
    CacheSizeOverflow { path: PathBuf },
'''
error_replacement = error_anchor + '''
    #[error("Cache identity property {path:?} is missing")]
    MissingCacheIdentity { path: PathBuf },

    #[error("Invalid cache level {level} in {path:?}")]
    InvalidCacheLevel { path: PathBuf, level: u32 },

    #[error("Invalid cache type {value:?} in {path:?}")]
    InvalidCacheType { path: PathBuf, value: String },
'''
if source.count(error_anchor) != 1:
    raise RuntimeError("cache error enum anchor changed")
source = source.replace(error_anchor, error_replacement)

middle_start = source.index("impl CacheLevel {")
source_tests_start = source.index("#[cfg(test)]\nmod tests {")
if source_tests_start <= middle_start:
    raise RuntimeError("cache source layout changed")

middle = r'''#[derive(Copy, Clone, Debug, Eq, PartialEq)]
enum CacheType {
    Data,
    Instruction,
    Unified,
}

#[derive(Copy, Clone, Debug)]
struct CacheLeaf {
    index: u32,
    level: u32,
    cache_type: CacheType,
}

#[derive(Default, Copy, Clone, Debug)]
struct CacheIndices {
    l1_d: Option<u32>,
    l1_i: Option<u32>,
    l2: Option<u32>,
    l3: Option<u32>,
}

fn cache_property_path(cache_path: &Path, index: u32, property: &str) -> PathBuf {
    cache_path.join(format!("index{index}")).join(property)
}

fn read_optional_property(path: &Path) -> Result<Option<String>> {
    match fs::read_to_string(path) {
        Ok(value) => Ok(Some(value)),
        Err(source) if source.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(source) => Err(Error::ReadCacheProperty {
            path: path.to_path_buf(),
            source,
        }),
    }
}

fn read_cache_identity_property(path: &Path) -> Result<String> {
    read_optional_property(path)?.ok_or_else(|| Error::MissingCacheIdentity {
        path: path.to_path_buf(),
    })
}

fn get_cache_size_from_index(cache_path: &Path, index: u32) -> Result<u32> {
    let path = cache_property_path(cache_path, index, "size");
    let Some(src) = read_optional_property(&path)? else {
        return Ok(0);
    };
    let src = src.trim();

    let (digits, multiplier) = if let Some(digits) = src.strip_suffix('K') {
        (digits, 1u32 << 10)
    } else if let Some(digits) = src.strip_suffix('M') {
        (digits, 1u32 << 20)
    } else if let Some(digits) = src.strip_suffix('G') {
        (digits, 1u32 << 30)
    } else {
        return Err(Error::InvalidCacheSize { path });
    };

    let value = digits
        .parse::<u32>()
        .map_err(|source| Error::ParseCacheProperty {
            path: path.clone(),
            source,
        })?;

    value
        .checked_mul(multiplier)
        .ok_or(Error::CacheSizeOverflow { path })
}

fn get_cache_u32_from_index(cache_path: &Path, index: u32, property: &str) -> Result<u32> {
    let path = cache_property_path(cache_path, index, property);
    let Some(src) = read_optional_property(&path)? else {
        return Ok(0);
    };

    src.trim()
        .parse::<u32>()
        .map_err(|source| Error::ParseCacheProperty { path, source })
}

fn get_cache_shared_from_index(cache_path: &Path, index: u32) -> Result<bool> {
    let path = cache_property_path(cache_path, index, "shared_cpu_list");
    let Some(src) = read_optional_property(&path)? else {
        return Ok(false);
    };
    let src = src.trim();

    Ok(!src.is_empty() && (src.contains('-') || src.contains(',')))
}

fn read_cache_leaves(cache_path: &Path) -> Result<Option<Vec<CacheLeaf>>> {
    match fs::metadata(cache_path) {
        Ok(_) => {}
        Err(source) if source.kind() == io::ErrorKind::NotFound => {
            warn!("Cache topology information is not available in sysfs.");
            return Ok(None);
        }
        Err(source) => {
            return Err(Error::AccessCacheTopology {
                path: cache_path.to_path_buf(),
                source,
            });
        }
    }

    let entries = fs::read_dir(cache_path).map_err(|source| Error::AccessCacheTopology {
        path: cache_path.to_path_buf(),
        source,
    })?;
    let mut leaves = Vec::new();

    for entry in entries {
        let entry = entry.map_err(|source| Error::AccessCacheTopology {
            path: cache_path.to_path_buf(),
            source,
        })?;
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            continue;
        };
        let Some(index) = name
            .strip_prefix("index")
            .and_then(|value| value.parse::<u32>().ok())
        else {
            continue;
        };

        let level_path = cache_property_path(cache_path, index, "level");
        let level = read_cache_identity_property(&level_path)?
            .trim()
            .parse::<u32>()
            .map_err(|source| Error::ParseCacheProperty {
                path: level_path.clone(),
                source,
            })?;
        if level == 0 {
            return Err(Error::InvalidCacheLevel {
                path: level_path,
                level,
            });
        }

        let type_path = cache_property_path(cache_path, index, "type");
        let value = read_cache_identity_property(&type_path)?;
        let value = value.trim();
        let cache_type = match value {
            "Data" => CacheType::Data,
            "Instruction" => CacheType::Instruction,
            "Unified" => CacheType::Unified,
            _ => {
                return Err(Error::InvalidCacheType {
                    path: type_path,
                    value: value.to_string(),
                });
            }
        };

        leaves.push(CacheLeaf {
            index,
            level,
            cache_type,
        });
    }

    leaves.sort_unstable_by_key(|leaf| leaf.index);
    Ok(Some(leaves))
}

fn classify_cache_leaves(leaves: &[CacheLeaf]) -> Option<CacheIndices> {
    if leaves.is_empty() {
        return Some(CacheIndices::default());
    }

    let mut indices = CacheIndices::default();
    for leaf in leaves {
        if leaf.level > 3 {
            continue;
        }

        let slot = match (leaf.level, leaf.cache_type) {
            (1, CacheType::Data) => &mut indices.l1_d,
            (1, CacheType::Instruction) => &mut indices.l1_i,
            (2, CacheType::Unified) => &mut indices.l2,
            (3, CacheType::Unified) => &mut indices.l3,
            _ => {
                warn!(
                    "Host cache topology cannot be represented by the current AArch64 guest cache model; omitting cache topology."
                );
                return None;
            }
        };

        if slot.replace(leaf.index).is_some() {
            warn!(
                "Host cache topology contains duplicate cache identities that cannot be represented by the current AArch64 guest cache model; omitting cache topology."
            );
            return None;
        }
    }

    if indices.l1_d.is_none()
        || indices.l1_i.is_none()
        || (indices.l3.is_some() && indices.l2.is_none())
    {
        warn!(
            "Host cache topology is incomplete for the current AArch64 guest cache model; omitting cache topology."
        );
        return None;
    }

    Some(indices)
}

fn read_cache_indices(cache_path: &Path) -> Result<Option<CacheIndices>> {
    let Some(leaves) = read_cache_leaves(cache_path)? else {
        return Ok(None);
    };

    Ok(classify_cache_leaves(&leaves))
}

fn cache_index(indices: CacheIndices, cache_level: CacheLevel) -> Option<u32> {
    match cache_level {
        CacheLevel::L1D => indices.l1_d,
        CacheLevel::L1I => indices.l1_i,
        CacheLevel::L2 => indices.l2,
        CacheLevel::L3 => indices.l3,
    }
}

/// NOTE: cache size file directory example,
/// "/sys/devices/system/cpu/cpu0/cache/index0/size".
pub fn get_cache_size(cache_level: CacheLevel) -> Result<u32> {
    let cache_path = Path::new(CACHE_SYSFS_PATH);
    let Some(indices) = read_cache_indices(cache_path)? else {
        return Ok(0);
    };
    let Some(index) = cache_index(indices, cache_level) else {
        return Ok(0);
    };

    get_cache_size_from_index(cache_path, index)
}

/// NOTE: coherency_line_size file directory example,
/// "/sys/devices/system/cpu/cpu0/cache/index0/coherency_line_size".
pub fn get_cache_coherency_line_size(cache_level: CacheLevel) -> Result<u32> {
    let cache_path = Path::new(CACHE_SYSFS_PATH);
    let Some(indices) = read_cache_indices(cache_path)? else {
        return Ok(0);
    };
    let Some(index) = cache_index(indices, cache_level) else {
        return Ok(0);
    };

    get_cache_u32_from_index(cache_path, index, "coherency_line_size")
}

/// NOTE: number_of_sets file directory example,
/// "/sys/devices/system/cpu/cpu0/cache/index0/number_of_sets".
pub fn get_cache_number_of_sets(cache_level: CacheLevel) -> Result<u32> {
    let cache_path = Path::new(CACHE_SYSFS_PATH);
    let Some(indices) = read_cache_indices(cache_path)? else {
        return Ok(0);
    };
    let Some(index) = cache_index(indices, cache_level) else {
        return Ok(0);
    };

    get_cache_u32_from_index(cache_path, index, "number_of_sets")
}

/// NOTE: shared_cpu_list file directory example,
/// "/sys/devices/system/cpu/cpu0/cache/index0/shared_cpu_list".
pub fn get_cache_shared(cache_level: CacheLevel) -> Result<bool> {
    if matches!(cache_level, CacheLevel::L1D | CacheLevel::L1I) {
        return Ok(false);
    }

    let cache_path = Path::new(CACHE_SYSFS_PATH);
    let Some(indices) = read_cache_indices(cache_path)? else {
        return Ok(false);
    };
    let Some(index) = cache_index(indices, cache_level) else {
        return Ok(false);
    };

    get_cache_shared_from_index(cache_path, index)
}

#[derive(Default, Copy, Clone, Debug)]
pub struct CacheTopologyInfo {
    pub l1_d_cache_size: u32,
    pub l1_d_cache_line_size: u32,
    pub l1_d_cache_sets: u32,

    pub l1_i_cache_size: u32,
    pub l1_i_cache_line_size: u32,
    pub l1_i_cache_sets: u32,

    pub l2_cache_size: u32,
    pub l2_cache_line_size: u32,
    pub l2_cache_sets: u32,

    pub l3_cache_size: u32,
    pub l3_cache_line_size: u32,
    pub l3_cache_sets: u32,

    pub l2_cache_shared: bool,
    pub l3_cache_shared: bool,
}

fn read_optional_cache_size(cache_path: &Path, index: Option<u32>) -> Result<u32> {
    match index {
        Some(index) => get_cache_size_from_index(cache_path, index),
        None => Ok(0),
    }
}

fn read_optional_cache_u32(
    cache_path: &Path,
    index: Option<u32>,
    property: &str,
) -> Result<u32> {
    match index {
        Some(index) => get_cache_u32_from_index(cache_path, index, property),
        None => Ok(0),
    }
}

fn read_optional_cache_shared(cache_path: &Path, index: Option<u32>, size: u32) -> Result<bool> {
    if size == 0 {
        return Ok(false);
    }

    match index {
        Some(index) => get_cache_shared_from_index(cache_path, index),
        None => Ok(false),
    }
}

fn read_cache_topology_from(cache_path: &Path) -> Result<Option<CacheTopologyInfo>> {
    let Some(indices) = read_cache_indices(cache_path)? else {
        return Ok(None);
    };

    let l2_cache_size = read_optional_cache_size(cache_path, indices.l2)?;
    let l3_cache_size = read_optional_cache_size(cache_path, indices.l3)?;
    let info = CacheTopologyInfo {
        l1_d_cache_size: read_optional_cache_size(cache_path, indices.l1_d)?,
        l1_d_cache_line_size: read_optional_cache_u32(
            cache_path,
            indices.l1_d,
            "coherency_line_size",
        )?,
        l1_d_cache_sets: read_optional_cache_u32(cache_path, indices.l1_d, "number_of_sets")?,

        l1_i_cache_size: read_optional_cache_size(cache_path, indices.l1_i)?,
        l1_i_cache_line_size: read_optional_cache_u32(
            cache_path,
            indices.l1_i,
            "coherency_line_size",
        )?,
        l1_i_cache_sets: read_optional_cache_u32(cache_path, indices.l1_i, "number_of_sets")?,

        l2_cache_size,
        l2_cache_line_size: read_optional_cache_u32(
            cache_path,
            indices.l2,
            "coherency_line_size",
        )?,
        l2_cache_sets: read_optional_cache_u32(cache_path, indices.l2, "number_of_sets")?,

        l3_cache_size,
        l3_cache_line_size: read_optional_cache_u32(
            cache_path,
            indices.l3,
            "coherency_line_size",
        )?,
        l3_cache_sets: read_optional_cache_u32(cache_path, indices.l3, "number_of_sets")?,

        l2_cache_shared: read_optional_cache_shared(cache_path, indices.l2, l2_cache_size)?,
        l3_cache_shared: read_optional_cache_shared(cache_path, indices.l3, l3_cache_size)?,
    };

    Ok(Some(info))
}

/// Reads cache topology information from sysfs for cpu0.
pub fn read_cache_topology() -> Result<Option<CacheTopologyInfo>> {
    read_cache_topology_from(Path::new(CACHE_SYSFS_PATH))
}

'''

tests = r'''#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::{env, process};

    use super::*;

    static NEXT_TEST_DIR: AtomicUsize = AtomicUsize::new(0);

    struct TestDir(PathBuf);

    impl TestDir {
        fn new() -> Self {
            let path = env::temp_dir().join(format!(
                "cloud-hypervisor-cache-test-{}-{}",
                process::id(),
                NEXT_TEST_DIR.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }

        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for TestDir {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }

    fn write_property(cache_path: &Path, index: u32, property: &str, value: &str) {
        let index_path = cache_path.join(format!("index{index}"));
        fs::create_dir_all(&index_path).unwrap();
        fs::write(index_path.join(property), value).unwrap();
    }

    fn write_identity(cache_path: &Path, index: u32, level: u32, cache_type: &str) {
        write_property(cache_path, index, "level", &format!("{level}\n"));
        write_property(cache_path, index, "type", &format!("{cache_type}\n"));
    }

    fn write_representable_identities(cache_path: &Path) {
        write_identity(cache_path, 0, 1, "Data");
        write_identity(cache_path, 1, 1, "Instruction");
        write_identity(cache_path, 2, 2, "Unified");
        write_identity(cache_path, 3, 3, "Unified");
    }

    #[test]
    fn test_missing_cache_root() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("missing");

        assert!(read_cache_topology_from(&cache_path).unwrap().is_none());
    }

    #[test]
    fn test_empty_cache_root_uses_defaults() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();

        let info = read_cache_topology_from(&cache_path).unwrap().unwrap();

        assert_eq!(info.l1_d_cache_size, 0);
        assert_eq!(info.l1_i_cache_size, 0);
        assert_eq!(info.l2_cache_size, 0);
        assert_eq!(info.l3_cache_size, 0);
    }

    #[test]
    fn test_valid_cache_properties() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_representable_identities(&cache_path);

        write_property(&cache_path, 0, "size", "32K\n");
        write_property(&cache_path, 0, "coherency_line_size", "64\n");
        write_property(&cache_path, 0, "number_of_sets", "128\n");
        write_property(&cache_path, 2, "size", "1024K\n");
        write_property(&cache_path, 2, "coherency_line_size", "64\n");
        write_property(&cache_path, 2, "number_of_sets", "2048\n");
        write_property(&cache_path, 2, "shared_cpu_list", "0-3\n");

        let info = read_cache_topology_from(&cache_path).unwrap().unwrap();

        assert_eq!(info.l1_d_cache_size, 32 * 1024);
        assert_eq!(info.l1_d_cache_line_size, 64);
        assert_eq!(info.l1_d_cache_sets, 128);
        assert_eq!(info.l2_cache_size, 1024 * 1024);
        assert_eq!(info.l2_cache_line_size, 64);
        assert_eq!(info.l2_cache_sets, 2048);
        assert!(info.l2_cache_shared);
    }

    #[test]
    fn test_split_l1_control_preserves_mapping() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_representable_identities(&cache_path);
        for (index, size) in [(0, "32K"), (1, "48K"), (2, "1024K"), (3, "32768K")] {
            write_property(&cache_path, index, "size", &format!("{size}\n"));
            write_property(&cache_path, index, "coherency_line_size", "64\n");
            write_property(&cache_path, index, "number_of_sets", "128\n");
        }
        write_property(&cache_path, 2, "shared_cpu_list", "0-3\n");
        write_property(&cache_path, 3, "shared_cpu_list", "0-7\n");

        let info = read_cache_topology_from(&cache_path).unwrap().unwrap();

        assert_eq!(info.l1_d_cache_size, 32 * 1024);
        assert_eq!(info.l1_i_cache_size, 48 * 1024);
        assert_eq!(info.l2_cache_size, 1024 * 1024);
        assert_eq!(info.l3_cache_size, 32768 * 1024);
        assert!(info.l2_cache_shared);
        assert!(info.l3_cache_shared);
    }

    #[test]
    fn test_unified_l1_is_omitted() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_identity(&cache_path, 0, 1, "Unified");
        write_identity(&cache_path, 1, 2, "Unified");
        write_identity(&cache_path, 2, 3, "Unified");

        assert!(read_cache_topology_from(&cache_path).unwrap().is_none());
    }

    #[test]
    fn test_split_l2_is_omitted() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_identity(&cache_path, 0, 1, "Data");
        write_identity(&cache_path, 1, 1, "Instruction");
        write_identity(&cache_path, 2, 2, "Data");
        write_identity(&cache_path, 3, 2, "Instruction");
        write_identity(&cache_path, 4, 3, "Unified");

        assert!(read_cache_topology_from(&cache_path).unwrap().is_none());
    }

    #[test]
    fn test_higher_cache_level_does_not_shift_mapping() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_representable_identities(&cache_path);
        write_identity(&cache_path, 4, 4, "Unified");
        write_property(&cache_path, 0, "size", "32K\n");
        write_property(&cache_path, 1, "size", "48K\n");
        write_property(&cache_path, 2, "size", "1024K\n");
        write_property(&cache_path, 3, "size", "32768K\n");
        write_property(&cache_path, 4, "size", "65536K\n");

        let info = read_cache_topology_from(&cache_path).unwrap().unwrap();

        assert_eq!(info.l1_d_cache_size, 32 * 1024);
        assert_eq!(info.l1_i_cache_size, 48 * 1024);
        assert_eq!(info.l2_cache_size, 1024 * 1024);
        assert_eq!(info.l3_cache_size, 32768 * 1024);
    }

    #[test]
    fn test_missing_cache_identity_is_error() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_property(&cache_path, 0, "type", "Data\n");

        assert!(matches!(
            read_cache_topology_from(&cache_path),
            Err(Error::MissingCacheIdentity { .. })
        ));
    }

    #[test]
    fn test_malformed_cache_level_is_error() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_property(&cache_path, 0, "level", "invalid\n");
        write_property(&cache_path, 0, "type", "Data\n");

        assert!(matches!(
            read_cache_topology_from(&cache_path),
            Err(Error::ParseCacheProperty { .. })
        ));
    }

    #[test]
    fn test_zero_cache_level_is_error() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_identity(&cache_path, 0, 0, "Data");

        assert!(matches!(
            read_cache_topology_from(&cache_path),
            Err(Error::InvalidCacheLevel { .. })
        ));
    }

    #[test]
    fn test_invalid_cache_type_is_error() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_identity(&cache_path, 0, 1, "Separate");

        assert!(matches!(
            read_cache_topology_from(&cache_path),
            Err(Error::InvalidCacheType { .. })
        ));
    }

    #[test]
    fn test_duplicate_cache_identity_is_omitted() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_identity(&cache_path, 0, 1, "Data");
        write_identity(&cache_path, 1, 1, "Data");
        write_identity(&cache_path, 2, 1, "Instruction");

        assert!(read_cache_topology_from(&cache_path).unwrap().is_none());
    }

    #[test]
    fn test_l3_without_l2_is_omitted() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_identity(&cache_path, 0, 1, "Data");
        write_identity(&cache_path, 1, 1, "Instruction");
        write_identity(&cache_path, 2, 3, "Unified");

        assert!(read_cache_topology_from(&cache_path).unwrap().is_none());
    }

    #[test]
    fn test_malformed_cache_size_is_error() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_identity(&cache_path, 0, 1, "Data");
        write_identity(&cache_path, 1, 1, "Instruction");
        write_property(&cache_path, 0, "size", "32Q\n");

        assert!(matches!(
            read_cache_topology_from(&cache_path),
            Err(Error::InvalidCacheSize { .. })
        ));
    }

    #[test]
    fn test_malformed_decimal_is_error() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_identity(&cache_path, 0, 1, "Data");
        write_identity(&cache_path, 1, 1, "Instruction");
        write_property(&cache_path, 0, "coherency_line_size", "invalid\n");

        assert!(matches!(
            read_cache_topology_from(&cache_path),
            Err(Error::ParseCacheProperty { .. })
        ));
    }

    #[test]
    fn test_cache_property_io_error_is_error() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_identity(&cache_path, 0, 1, "Data");
        write_identity(&cache_path, 1, 1, "Instruction");
        fs::create_dir(cache_path.join("index0/size")).unwrap();

        assert!(matches!(
            read_cache_topology_from(&cache_path),
            Err(Error::ReadCacheProperty { .. })
        ));
    }

    #[test]
    fn test_cache_size_overflow_is_error() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_identity(&cache_path, 0, 1, "Data");
        write_identity(&cache_path, 1, 1, "Instruction");
        write_property(&cache_path, 0, "size", "4194304K\n");

        assert!(matches!(
            read_cache_topology_from(&cache_path),
            Err(Error::CacheSizeOverflow { .. })
        ));
    }
}
'''

source = source[:middle_start] + middle + tests
cache_file.write_text(source)
run("cargo", "+nightly", "fmt", "--all")
print("cache-index-prerequisites-applied")
print("cache-index-candidate-generated")
