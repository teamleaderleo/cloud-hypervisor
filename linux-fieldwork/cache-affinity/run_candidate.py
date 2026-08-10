#!/usr/bin/env python3
import hashlib
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

CANDIDATE_PATH = Path("linux-fieldwork/cache-affinity/candidate.patch")
CANDIDATE_BLOB = "75601cb2fa2a7d8f8f85dcdd9c3724c41a18d947"
CANDIDATE_SHA256 = "b38cfe17b90a7cda804b8ad9bdcd921cab4891457d55674a0691b7f0da310498"


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

actual_blob = output("git", "hash-object", str(CANDIDATE_PATH))
if actual_blob != CANDIDATE_BLOB:
    raise RuntimeError(
        f"candidate patch identity mismatch: expected {CANDIDATE_BLOB}, found {actual_blob}"
    )
actual_sha256 = hashlib.sha256(CANDIDATE_PATH.read_bytes()).hexdigest()
if actual_sha256 != CANDIDATE_SHA256:
    raise RuntimeError(
        f"candidate patch sha256 mismatch: expected {CANDIDATE_SHA256}, found {actual_sha256}"
    )

# The frozen v2 candidate was authored over an earlier cache-identity carrier.
# Use the patch's recorded preimage blobs for a real three-way restack onto the
# refreshed prerequisite chain; the workflow verifies resulting scope, policy,
# tests, and stable patch identity before accepting the restack.
run("git", "apply", "--3way", str(CANDIDATE_PATH))
run("cargo", "+nightly", "fmt", "--all", "--", "--check")

print("cache-affinity-submitted-acpi-prerequisite-applied")
print("cache-affinity-final-cache-error-prerequisite-applied")
print("cache-affinity-final-cache-identity-prerequisite-applied")
print("cache-affinity-final-cache-sharing-prerequisite-applied")
print("cache-affinity-stored-candidate-verified")
print("cache-affinity-stored-candidate-three-way-restacked")
print("cache-affinity-candidate-format-verified")
