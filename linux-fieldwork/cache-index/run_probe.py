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

probe = r'''

    fn write_identity(
        cache_path: &Path,
        index: u8,
        level: u8,
        cache_type: &str,
        size: &str,
    ) {
        write_property(cache_path, index, "level", &format!("{level}\n"));
        write_property(cache_path, index, "type", &format!("{cache_type}\n"));
        write_property(cache_path, index, "size", &format!("{size}\n"));
        write_property(cache_path, index, "coherency_line_size", "64\n");
        write_property(cache_path, index, "number_of_sets", "128\n");
        write_property(cache_path, index, "shared_cpu_list", "0-3\n");
    }

    fn read_identity(cache_path: &Path, index: u8) -> (u8, String) {
        let index_path = cache_path.join(format!("index{index}"));
        let level = fs::read_to_string(index_path.join("level"))
            .unwrap()
            .trim()
            .parse::<u8>()
            .unwrap();
        let cache_type = fs::read_to_string(index_path.join("type"))
            .unwrap()
            .trim()
            .to_string();
        (level, cache_type)
    }

    #[test]
    fn test_fixed_index_mapping_matches_split_l1_control() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();

        write_identity(&cache_path, 0, 1, "Data", "32K");
        write_identity(&cache_path, 1, 1, "Instruction", "48K");
        write_identity(&cache_path, 2, 2, "Unified", "1024K");
        write_identity(&cache_path, 3, 3, "Unified", "32768K");

        let info = read_cache_topology_from(&cache_path).unwrap().unwrap();

        assert_eq!(read_identity(&cache_path, 0), (1, "Data".to_string()));
        assert_eq!(read_identity(&cache_path, 1), (1, "Instruction".to_string()));
        assert_eq!(read_identity(&cache_path, 2), (2, "Unified".to_string()));
        assert_eq!(read_identity(&cache_path, 3), (3, "Unified".to_string()));
        assert_eq!(info.l1_d_cache_size, 32 * 1024);
        assert_eq!(info.l1_i_cache_size, 48 * 1024);
        assert_eq!(info.l2_cache_size, 1024 * 1024);
        assert_eq!(info.l3_cache_size, 32768 * 1024);
    }

    #[test]
    fn test_fixed_index_mapping_misreads_unified_l1_fixture() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();

        write_identity(&cache_path, 0, 1, "Unified", "64K");
        write_identity(&cache_path, 1, 2, "Unified", "2048K");
        write_identity(&cache_path, 2, 3, "Unified", "32768K");

        let info = read_cache_topology_from(&cache_path).unwrap().unwrap();

        assert_eq!(read_identity(&cache_path, 1), (2, "Unified".to_string()));
        assert_eq!(info.l1_i_cache_size, 2048 * 1024);
        assert_eq!(read_identity(&cache_path, 2), (3, "Unified".to_string()));
        assert_eq!(info.l2_cache_size, 32768 * 1024);
        assert_eq!(info.l3_cache_size, 0);
    }

    #[test]
    fn test_fixed_index_mapping_misreads_split_l2_fixture() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();

        write_identity(&cache_path, 0, 1, "Data", "32K");
        write_identity(&cache_path, 1, 1, "Instruction", "48K");
        write_identity(&cache_path, 2, 2, "Data", "1024K");
        write_identity(&cache_path, 3, 2, "Instruction", "1024K");
        write_identity(&cache_path, 4, 3, "Unified", "32768K");

        let info = read_cache_topology_from(&cache_path).unwrap().unwrap();

        assert_eq!(read_identity(&cache_path, 2), (2, "Data".to_string()));
        assert_eq!(info.l2_cache_size, 1024 * 1024);
        assert_eq!(read_identity(&cache_path, 3), (2, "Instruction".to_string()));
        assert_eq!(info.l3_cache_size, 1024 * 1024);
        assert_eq!(read_identity(&cache_path, 4), (3, "Unified".to_string()));
    }
'''

cache_file = Path("arch/src/aarch64/cache.rs")
source = cache_file.read_text()
if not source.endswith("\n}\n"):
    raise RuntimeError("cache.rs test module ending changed")
cache_file.write_text(source[:-3] + probe + "\n}\n")
run("cargo", "+nightly", "fmt", "--all", "--", "--check")
print("cache-index-prerequisites-applied")
print("cache-index-probe-injected")
