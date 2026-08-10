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
CACHE_COMMIT = "23c8d996457eb8f489f5cfb1bf7f33c9e506e44e"
CACHE_PARSER_PATH = "linux-fieldwork/cache-errors/candidate.patch"
CACHE_PARSER_BLOB = "f381a777ea3343c33d2dd0bdbde067a2a91cc692"
CACHE_PROPAGATION_PATH = "linux-fieldwork/cache-errors/propagation.patch"
CACHE_PROPAGATION_BLOB = "cbfe0675d08f3b4bc1871d3825b9c67d8d5ac71c"
INDEX_COMMIT = "0cffc6c8f8d79dddb95bce305976a101d8b90a9e"
INDEX_PATH = "linux-fieldwork/cache-index/candidate.patch"
INDEX_BLOB = "b6e21517377995f35ff6984ffc29f06a21db06b7"
CANDIDATE_PATH = "linux-fieldwork/cache-sharing/candidate.patch"
CANDIDATE_BLOB = "0eaf11c0fadd706854c112c051826c3906b75327"


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

for branch in [
    "linux-fieldwork/acpi-error-propagation",
    "linux-fieldwork/cache-runtime-errors",
    "linux-fieldwork/cache-index-portability",
]:
    run("git", "fetch", "--no-tags", "--depth=100", "origin", branch)

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

index_patch = materialize(INDEX_COMMIT, INDEX_PATH, "/tmp/cache-index.patch", INDEX_BLOB)
run("git", "apply", "--check", str(index_patch))
run("git", "apply", str(index_patch))
run("cargo", "+nightly", "fmt", "--all", "--", "--check")
run("git", "add", "arch/src/aarch64/cache.rs")
run(
    "git",
    "-c",
    "user.name=Linux Fieldwork CI",
    "-c",
    "user.email=linux-fieldwork@example.invalid",
    "commit",
    "-m",
    "ci: apply validated cache identity prerequisite",
)

# Commit runtime fixtures before applying product code so the retained product
# diff remains vmm/src/cpu.rs only.
cache_file = Path("arch/src/aarch64/cache.rs")
cache_source = cache_file.read_text()
probe = r'''

    #[test]
    fn test_shared_l2_layout_is_returned_with_shared_flag() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_representable_identities(&cache_path);
        write_property(&cache_path, 0, "size", "32K\n");
        write_property(&cache_path, 1, "size", "48K\n");
        write_property(&cache_path, 2, "size", "1024K\n");
        write_property(&cache_path, 3, "size", "32768K\n");
        write_property(&cache_path, 2, "shared_cpu_list", "0,4,8,12\n");
        write_property(&cache_path, 3, "shared_cpu_list", "0-15\n");

        let info = read_cache_topology_from(&cache_path).unwrap().unwrap();
        assert_eq!(info.l2_cache_size, 1024 * 1024);
        assert!(info.l2_cache_shared);
        assert!(info.l3_cache_shared);
    }

    #[test]
    fn test_private_l3_layout_is_returned_with_private_flag() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_representable_identities(&cache_path);
        write_property(&cache_path, 0, "size", "32K\n");
        write_property(&cache_path, 1, "size", "48K\n");
        write_property(&cache_path, 2, "size", "1024K\n");
        write_property(&cache_path, 3, "size", "32768K\n");
        write_property(&cache_path, 2, "shared_cpu_list", "0\n");
        write_property(&cache_path, 3, "shared_cpu_list", "0\n");

        let info = read_cache_topology_from(&cache_path).unwrap().unwrap();
        assert_eq!(info.l3_cache_size, 32768 * 1024);
        assert!(!info.l2_cache_shared);
        assert!(!info.l3_cache_shared);
    }
'''
if not cache_source.endswith("\n}\n"):
    raise RuntimeError("cache.rs test module ending changed")
cache_file.write_text(cache_source[:-3] + probe + "\n}\n")
run("cargo", "+nightly", "fmt", "--all")
run("git", "add", "arch/src/aarch64/cache.rs")
run(
    "git",
    "-c",
    "user.name=Linux Fieldwork CI",
    "-c",
    "user.email=linux-fieldwork@example.invalid",
    "commit",
    "-m",
    "ci: add cache sharing fixtures",
)

candidate = Path(CANDIDATE_PATH)
actual_candidate_blob = output("git", "hash-object", str(candidate))
if actual_candidate_blob != CANDIDATE_BLOB:
    raise RuntimeError(
        f"candidate patch identity mismatch: expected {CANDIDATE_BLOB}, found {actual_candidate_blob}"
    )
run("git", "apply", "--check", str(candidate))
run("git", "apply", str(candidate))
run("cargo", "+nightly", "fmt", "--all", "--", "--check")
print("cache-sharing-prerequisites-applied")
print("cache-sharing-fixtures-committed")
print("cache-sharing-candidate-applied")
print("cache-sharing-candidate-format-verified")
