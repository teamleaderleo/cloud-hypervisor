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

pending_files = []
for _branch, commit, source_path, expected_blob, destination, commit_files, message in PATCHES:
    patch = materialize(commit, source_path, destination, expected_blob)
    run("git", "apply", "--check", str(patch))
    run("git", "apply", str(patch))
    if commit_files is None:
        continue
    run("cargo", "+nightly", "fmt", "--all", "--", "--check")
    files = pending_files + commit_files
    run("git", "add", *dict.fromkeys(files))
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
    pending_files = []

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

        write_identity(&cpu0_cache, 0, 1, "Data", "32K");
        write_identity(&cpu0_cache, 1, 1, "Instruction", "32K");
        write_identity(&cpu0_cache, 2, 2, "Unified", "256K");
        write_identity(&cpu0_cache, 3, 3, "Unified", "4096K");

        write_identity(&cpu4_cache, 0, 1, "Data", "64K");
        write_identity(&cpu4_cache, 1, 1, "Instruction", "64K");
        write_identity(&cpu4_cache, 2, 2, "Unified", "1024K");
        write_identity(&cpu4_cache, 3, 3, "Unified", "4096K");

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
print("cache-affinity-prerequisites-applied")
print("cache-affinity-probe-injected")
