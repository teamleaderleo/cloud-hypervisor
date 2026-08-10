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

PREREQUISITES = [
    (
        "0a2f55acbd23b7f44899a69132a4236ef9240027",
        "linux-fieldwork/acpi-errors/candidate.patch",
        "034cebd92cf31e3b415cdd3d205035b96cd9c1fb",
        "/tmp/acpi.patch",
        ["vmm/src/acpi.rs", "vmm/src/vm.rs"],
        "ci: apply validated ACPI prerequisite",
    ),
    (
        "23c8d996457eb8f489f5cfb1bf7f33c9e506e44e",
        "linux-fieldwork/cache-errors/candidate.patch",
        "f381a777ea3343c33d2dd0bdbde067a2a91cc692",
        "/tmp/cache-errors-parser.patch",
        ["arch/src/aarch64/cache.rs"],
        None,
    ),
    (
        "23c8d996457eb8f489f5cfb1bf7f33c9e506e44e",
        "linux-fieldwork/cache-errors/propagation.patch",
        "cbfe0675d08f3b4bc1871d3825b9c67d8d5ac71c",
        "/tmp/cache-errors-propagation.patch",
        ["arch/src/aarch64/fdt.rs", "arch/src/aarch64/mod.rs", "vmm/src/acpi.rs", "vmm/src/cpu.rs"],
        "ci: apply validated cache-error prerequisite",
    ),
    (
        "0cffc6c8f8d79dddb95bce305976a101d8b90a9e",
        "linux-fieldwork/cache-index/candidate.patch",
        "b6e21517377995f35ff6984ffc29f06a21db06b7",
        "/tmp/cache-index.patch",
        ["arch/src/aarch64/cache.rs"],
        "ci: apply validated cache-index prerequisite",
    ),
]

CANDIDATE_BLOB = "29454b225bc61ac358ea65fae15fbd3ebebd4a40"


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


def commit(paths: list[str], message: str) -> None:
    run("git", "add", *paths)
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

run("git", "fetch", "--no-tags", "--depth=100", "origin", "linux-fieldwork/acpi-error-propagation")
run("git", "fetch", "--no-tags", "--depth=100", "origin", "linux-fieldwork/cache-runtime-errors")
run("git", "fetch", "--no-tags", "--depth=100", "origin", "linux-fieldwork/cache-index-portability")

pending_paths: list[str] = []
for prerequisite_commit, source_path, expected_blob, destination, paths, message in PREREQUISITES:
    patch = materialize(prerequisite_commit, source_path, destination, expected_blob)
    run("git", "apply", "--check", str(patch))
    run("git", "apply", str(patch))
    pending_paths.extend(paths)
    if message is not None:
        run("cargo", "+nightly", "fmt", "--all", "--", "--check")
        commit(sorted(set(pending_paths)), message)
        pending_paths = []

candidate = Path(__file__).with_name("candidate.patch")
actual_candidate_blob = output("git", "hash-object", str(candidate))
if actual_candidate_blob != CANDIDATE_BLOB:
    raise RuntimeError(
        f"candidate.patch: expected blob {CANDIDATE_BLOB}, found {actual_candidate_blob}"
    )
run("git", "apply", "--check", str(candidate))
run("git", "apply", str(candidate))
run("cargo", "+nightly", "fmt", "--all", "--", "--check")
print("pptt-cache-sharing-prerequisites-applied")
print("pptt-cache-sharing-candidate-applied")
