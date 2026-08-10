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

read_optional = '''fn read_optional_property(path: &Path) -> Result<Option<String>> {
    match fs::read_to_string(path) {
        Ok(value) => Ok(Some(value)),
        Err(source) if source.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(source) => Err(Error::ReadCacheProperty {
            path: path.to_path_buf(),
            source,
        }),
    }
}
'''

identity_helpers = r'''

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
enum CacheLayoutStatus {
    Empty,
    Supported,
    Unsupported,
}

fn cache_index_path(cache_path: &Path, index: u8) -> PathBuf {
    cache_path.join(format!("index{index}"))
}

fn cache_index_exists(cache_path: &Path, index: u8) -> Result<bool> {
    let path = cache_index_path(cache_path, index);
    match fs::metadata(&path) {
        Ok(_) => Ok(true),
        Err(source) if source.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(source) => Err(Error::AccessCacheTopology { path, source }),
    }
}

fn cache_identity_matches(
    cache_path: &Path,
    index: u8,
    expected_level: u32,
    expected_type: &str,
) -> Result<Option<bool>> {
    if !cache_index_exists(cache_path, index)? {
        return Ok(None);
    }

    let index_path = cache_index_path(cache_path, index);
    let level_path = index_path.join("level");
    let cache_type_path = index_path.join("type");
    let Some(level) = read_optional_property(&level_path)? else {
        return Ok(Some(false));
    };
    let Some(cache_type) = read_optional_property(&cache_type_path)? else {
        return Ok(Some(false));
    };
    let level = level
        .trim()
        .parse::<u32>()
        .map_err(|source| Error::ParseCacheProperty {
            path: level_path,
            source,
        })?;

    Ok(Some(
        level == expected_level && cache_type.trim() == expected_type,
    ))
}

fn cache_layout_status(cache_path: &Path) -> Result<CacheLayoutStatus> {
    if !cache_index_exists(cache_path, 0)? {
        for index in 1..=4 {
            if cache_index_exists(cache_path, index)? {
                return Ok(CacheLayoutStatus::Unsupported);
            }
        }
        return Ok(CacheLayoutStatus::Empty);
    }

    let expected = [
        (0, 1, "Data", true),
        (1, 1, "Instruction", true),
        (2, 2, "Unified", false),
        (3, 3, "Unified", false),
    ];
    let mut missing_optional = false;

    for (index, level, cache_type, required) in expected {
        match cache_identity_matches(cache_path, index, level, cache_type)? {
            Some(true) if !missing_optional => {}
            Some(_) => return Ok(CacheLayoutStatus::Unsupported),
            None if required => return Ok(CacheLayoutStatus::Unsupported),
            None => missing_optional = true,
        }
    }

    if cache_index_exists(cache_path, 4)? {
        return Ok(CacheLayoutStatus::Unsupported);
    }

    Ok(CacheLayoutStatus::Supported)
}
'''

if read_optional not in source:
    raise RuntimeError("read_optional_property anchor changed")
source = source.replace(read_optional, read_optional + identity_helpers, 1)

read_topology = source.index("fn read_cache_topology_from(cache_path: &Path)")
info_pos = source.index("\n    let mut info = CacheTopologyInfo {", read_topology)
layout_guard = r'''

    if cache_layout_status(cache_path)? == CacheLayoutStatus::Unsupported {
        warn!(
            "Cache topology at {cache_path:?} cannot be represented by the current AArch64 guest cache model; omitting cache information."
        );
        return Ok(None);
    }
'''
source = source[:info_pos] + layout_guard + source[info_pos:]

write_property = '''    fn write_property(cache_path: &Path, index: u8, property: &str, value: &str) {
        let index_path = cache_path.join(format!("index{index}"));
        fs::create_dir_all(&index_path).unwrap();
        fs::write(index_path.join(property), value).unwrap();
    }
'''
identity_fixture = r'''

    fn write_supported_l1_identity(cache_path: &Path) {
        write_property(cache_path, 0, "level", "1\n");
        write_property(cache_path, 0, "type", "Data\n");
        write_property(cache_path, 1, "level", "1\n");
        write_property(cache_path, 1, "type", "Instruction\n");
    }

    fn write_identity(cache_path: &Path, index: u8, level: u8, cache_type: &str, size: &str) {
        write_property(cache_path, index, "level", &format!("{level}\n"));
        write_property(cache_path, index, "type", &format!("{cache_type}\n"));
        write_property(cache_path, index, "size", &format!("{size}\n"));
        write_property(cache_path, index, "coherency_line_size", "64\n");
        write_property(cache_path, index, "number_of_sets", "128\n");
        write_property(cache_path, index, "shared_cpu_list", "0-3\n");
    }
'''
if write_property not in source:
    raise RuntimeError("test helper anchor changed")
source = source.replace(write_property, write_property + identity_fixture, 1)

valid_anchor = '''        fs::create_dir(&cache_path).unwrap();

        write_property(&cache_path, 0, "size", "32K\\n");
'''
valid_replacement = '''        fs::create_dir(&cache_path).unwrap();
        write_supported_l1_identity(&cache_path);
        write_property(&cache_path, 2, "level", "2\\n");
        write_property(&cache_path, 2, "type", "Unified\\n");

        write_property(&cache_path, 0, "size", "32K\\n");
'''
if valid_anchor not in source:
    raise RuntimeError("valid cache fixture anchor changed")
source = source.replace(valid_anchor, valid_replacement, 1)

for test_name in [
    "test_malformed_cache_size_is_error",
    "test_malformed_decimal_is_error",
    "test_cache_property_io_error_is_error",
    "test_cache_size_overflow_is_error",
]:
    start = source.index(f"    fn {test_name}()")
    create = source.index("        fs::create_dir(&cache_path).unwrap();", start)
    insert = create + len("        fs::create_dir(&cache_path).unwrap();")
    source = source[:insert] + "\n        write_supported_l1_identity(&cache_path);" + source[insert:]

new_tests = r'''

    #[test]
    fn test_split_l1_layout_is_preserved() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();

        write_identity(&cache_path, 0, 1, "Data", "32K");
        write_identity(&cache_path, 1, 1, "Instruction", "48K");
        write_identity(&cache_path, 2, 2, "Unified", "1024K");
        write_identity(&cache_path, 3, 3, "Unified", "32768K");

        let info = read_cache_topology_from(&cache_path).unwrap().unwrap();
        assert_eq!(info.l1_d_cache_size, 32 * 1024);
        assert_eq!(info.l1_i_cache_size, 48 * 1024);
        assert_eq!(info.l2_cache_size, 1024 * 1024);
        assert_eq!(info.l3_cache_size, 32768 * 1024);
    }

    #[test]
    fn test_unified_l1_layout_is_omitted() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();

        write_identity(&cache_path, 0, 1, "Unified", "64K");
        write_identity(&cache_path, 1, 2, "Unified", "2048K");
        write_identity(&cache_path, 2, 3, "Unified", "32768K");

        assert!(read_cache_topology_from(&cache_path).unwrap().is_none());
    }

    #[test]
    fn test_split_l2_layout_is_omitted() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();

        write_identity(&cache_path, 0, 1, "Data", "32K");
        write_identity(&cache_path, 1, 1, "Instruction", "48K");
        write_identity(&cache_path, 2, 2, "Data", "1024K");
        write_identity(&cache_path, 3, 2, "Instruction", "1024K");
        write_identity(&cache_path, 4, 3, "Unified", "32768K");

        assert!(read_cache_topology_from(&cache_path).unwrap().is_none());
    }

    #[test]
    fn test_extra_cache_level_is_omitted() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();

        write_identity(&cache_path, 0, 1, "Data", "32K");
        write_identity(&cache_path, 1, 1, "Instruction", "48K");
        write_identity(&cache_path, 2, 2, "Unified", "1024K");
        write_identity(&cache_path, 3, 3, "Unified", "32768K");
        write_identity(&cache_path, 4, 4, "Unified", "65536K");

        assert!(read_cache_topology_from(&cache_path).unwrap().is_none());
    }
'''

if not source.endswith("\n}\n"):
    raise RuntimeError("cache.rs test module ending changed")
source = source[:-3] + new_tests + "\n}\n"
cache_file.write_text(source)
run("cargo", "+nightly", "fmt", "--all")
print("cache-index-candidate-applied")
