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

CANONICAL_BASE = "a1fcb9f790616ac615f66de73be540b0b20844b1"
ACPI_BRANCH = "fix/8666-acpi-errors"
ACPI_COMMIT = "e9c86bacee14a2fd6fe871dc678c6b3f1ac4012a"
CACHE_BRANCH = "linux-fieldwork/cache-runtime-errors"
CACHE_COMMIT = "a696e285eaece00335e106acdfb5a651ccb2261f"
CACHE_PARSER_PATH = "linux-fieldwork/cache-errors/candidate.patch"
CACHE_PARSER_BLOB = "64dc6a19b132aad66b1adaccf9aaa1853a734d7c"
CACHE_PROPAGATION_PATH = "linux-fieldwork/cache-errors/propagation.patch"
CACHE_PROPAGATION_BLOB = "9e175e73a26530d8dd5584cb15ae3ab4b36df196"
INDEX_BRANCH = "linux-fieldwork/cache-index-portability"
INDEX_COMMIT = "8dfd55a96b0cbf3d6891c25735455b8b793133e9"
INDEX_PATH = "linux-fieldwork/cache-index/candidate.patch"
INDEX_BLOB = "b6e21517377995f35ff6984ffc29f06a21db06b7"
SHARING_BRANCH = "linux-fieldwork/cache-sharing-pptt"
SHARING_COMMIT = "32cde9c6849c9744e2945f6900c8e4035f7ccf03"
SHARING_PATH = "linux-fieldwork/cache-sharing/candidate.patch"
SHARING_BLOB = "e606e0559e7d82689eb2ec2f29ed485715d36900"


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def output(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def fetch_exact(branch: str, expected_commit: str) -> None:
    run("git", "fetch", "--no-tags", "--depth=100", "origin", branch)
    actual = output("git", "rev-parse", "FETCH_HEAD")
    if actual != expected_commit:
        raise RuntimeError(
            f"{branch}: expected prerequisite head {expected_commit}, found {actual}"
        )


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


def apply_and_commit(patches: list[Path], files: list[str], message: str) -> None:
    for patch in patches:
        run("git", "apply", "--check", str(patch))
        run("git", "apply", str(patch))
    run("cargo", "+nightly", "fmt", "--all", "--", "--check")
    run("git", "add", *files)
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


for path, expected in EXPECTED_BLOBS.items():
    actual = output("git", "hash-object", path)
    if actual != expected:
        raise RuntimeError(f"{path}: expected source blob {expected}, found {actual}")

fetch_exact(ACPI_BRANCH, ACPI_COMMIT)
acpi_files = output(
    "git",
    "diff",
    "--name-only",
    CANONICAL_BASE,
    ACPI_COMMIT,
    "--",
    "vmm/src/acpi.rs",
    "vmm/src/vm.rs",
).splitlines()
if acpi_files != ["vmm/src/acpi.rs", "vmm/src/vm.rs"]:
    raise RuntimeError(f"unexpected ACPI prerequisite scope: {acpi_files}")

acpi_bytes = subprocess.run(
    [
        "git",
        "diff",
        "--binary",
        CANONICAL_BASE,
        ACPI_COMMIT,
        "--",
        "vmm/src/acpi.rs",
        "vmm/src/vm.rs",
    ],
    check=True,
    capture_output=True,
).stdout
acpi = Path("/tmp/acpi.patch")
acpi.write_bytes(acpi_bytes)
apply_and_commit(
    [acpi],
    ["vmm/src/acpi.rs", "vmm/src/vm.rs"],
    "ci: apply submitted ACPI prerequisite",
)

fetch_exact(CACHE_BRANCH, CACHE_COMMIT)
cache_parser = materialize(
    CACHE_COMMIT,
    CACHE_PARSER_PATH,
    "/tmp/cache-parser.patch",
    CACHE_PARSER_BLOB,
)
cache_propagation = materialize(
    CACHE_COMMIT,
    CACHE_PROPAGATION_PATH,
    "/tmp/cache-propagation.patch",
    CACHE_PROPAGATION_BLOB,
)
apply_and_commit(
    [cache_parser, cache_propagation],
    [
        "arch/src/aarch64/cache.rs",
        "arch/src/aarch64/fdt.rs",
        "arch/src/aarch64/mod.rs",
        "vmm/src/acpi.rs",
        "vmm/src/cpu.rs",
    ],
    "ci: apply validated cache error prerequisite",
)

fetch_exact(INDEX_BRANCH, INDEX_COMMIT)
index_patch = materialize(INDEX_COMMIT, INDEX_PATH, "/tmp/cache-index.patch", INDEX_BLOB)
apply_and_commit(
    [index_patch],
    ["arch/src/aarch64/cache.rs"],
    "ci: apply validated cache identity prerequisite",
)

fetch_exact(SHARING_BRANCH, SHARING_COMMIT)
sharing_patch = materialize(
    SHARING_COMMIT,
    SHARING_PATH,
    "/tmp/cache-sharing.patch",
    SHARING_BLOB,
)
apply_and_commit(
    [sharing_patch],
    ["vmm/src/cpu.rs"],
    "ci: apply validated cache sharing prerequisite",
)

cache_file = Path("arch/src/aarch64/cache.rs")
source = cache_file.read_text()
probe = r'''

    #[test]
    fn test_valid_cpu_roots_can_have_different_private_cache_geometry() {
        let temp = TestDir::new();
        let cpu0_cache = temp.path().join("cpu0/cache");
        let cpu4_cache = temp.path().join("cpu4/cache");
        fs::create_dir_all(&cpu0_cache).unwrap();
        fs::create_dir_all(&cpu4_cache).unwrap();

        write_identity(&cpu0_cache, 0, 1, "Data");
        write_property(&cpu0_cache, 0, "size", "32K");
        write_identity(&cpu0_cache, 1, 1, "Instruction");
        write_property(&cpu0_cache, 1, "size", "32K");
        write_identity(&cpu0_cache, 2, 2, "Unified");
        write_property(&cpu0_cache, 2, "size", "256K");
        write_identity(&cpu0_cache, 3, 3, "Unified");
        write_property(&cpu0_cache, 3, "size", "4096K");

        write_identity(&cpu4_cache, 0, 1, "Data");
        write_property(&cpu4_cache, 0, "size", "64K");
        write_identity(&cpu4_cache, 1, 1, "Instruction");
        write_property(&cpu4_cache, 1, "size", "64K");
        write_identity(&cpu4_cache, 2, 2, "Unified");
        write_property(&cpu4_cache, 2, "size", "1024K");
        write_identity(&cpu4_cache, 3, 3, "Unified");
        write_property(&cpu4_cache, 3, "size", "4096K");

        let cpu0 = read_cache_topology_from(&cpu0_cache).unwrap().unwrap();
        let cpu4 = read_cache_topology_from(&cpu4_cache).unwrap().unwrap();

        assert_eq!(cpu0.l1_d_cache_size, 32 * 1024);
        assert_eq!(cpu4.l1_d_cache_size, 64 * 1024);
        assert_eq!(cpu0.l2_cache_size, 256 * 1024);
        assert_eq!(cpu4.l2_cache_size, 1024 * 1024);
        assert_ne!(cpu0.l1_d_cache_size, cpu4.l1_d_cache_size);
        assert_ne!(cpu0.l2_cache_size, cpu4.l2_cache_size);
    }
'''
if not source.endswith("\n}\n"):
    raise RuntimeError("cache.rs test module ending changed")
cache_file.write_text(source[:-3] + probe + "\n}\n")
run("cargo", "+nightly", "fmt", "--all")
print("cache-affinity-final-prerequisites-applied")
print("cache-affinity-negative-control-probe-injected")
