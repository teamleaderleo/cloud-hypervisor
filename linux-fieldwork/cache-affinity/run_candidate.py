#!/usr/bin/env python3
import hashlib
import shutil
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

OLD_PATCHES = [
    (
        "0a2f55acbd23b7f44899a69132a4236ef9240027",
        "linux-fieldwork/acpi-errors/candidate.patch",
        "034cebd92cf31e3b415cdd3d205035b96cd9c1fb",
        "/tmp/old-acpi.patch",
        ["vmm/src/acpi.rs", "vmm/src/vm.rs"],
        "ci: reconstruct old ACPI prerequisite",
    ),
    (
        "044a728ddf5d9dbb00eba04a6df6679e84521441",
        "linux-fieldwork/cache-errors/candidate.patch",
        "f381a777ea3343c33d2dd0bdbde067a2a91cc692",
        "/tmp/old-cache-parser.patch",
        None,
        None,
    ),
    (
        "044a728ddf5d9dbb00eba04a6df6679e84521441",
        "linux-fieldwork/cache-errors/propagation.patch",
        "9dab1cadb2d48c919fc5239c974a30e594a9a6c4",
        "/tmp/old-cache-propagation.patch",
        [
            "arch/src/aarch64/cache.rs",
            "arch/src/aarch64/fdt.rs",
            "arch/src/aarch64/mod.rs",
            "vmm/src/acpi.rs",
            "vmm/src/cpu.rs",
        ],
        "ci: reconstruct old cache error prerequisite",
    ),
    (
        "7713a59e21c48262843da100087454dae3c0772d",
        "linux-fieldwork/cache-index/candidate.patch",
        "4550e55faba24d0c1ffc9f7be7a11596d5866b8a",
        "/tmp/old-cache-index.patch",
        ["arch/src/aarch64/cache.rs"],
        "ci: reconstruct old cache identity prerequisite",
    ),
    (
        "b3c66237ed59f6d7ac521d821f2f9bf138868ead",
        "linux-fieldwork/cache-sharing/candidate.patch",
        "bb45c3741cdebecd183cd05b769dfd56da4f80ab",
        "/tmp/old-cache-sharing.patch",
        ["vmm/src/cpu.rs"],
        "ci: reconstruct old cache sharing prerequisite",
    ),
]

CANDIDATE_PATH = Path("linux-fieldwork/cache-affinity/candidate.patch")
CANDIDATE_BLOB = "75601cb2fa2a7d8f8f85dcdd9c3724c41a18d947"
CANDIDATE_SHA256 = "b38cfe17b90a7cda804b8ad9bdcd921cab4891457d55674a0691b7f0da310498"


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, check=True, cwd=cwd)


def output(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    ).stdout.strip()


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


def apply_and_commit(
    patches: list[Path], files: list[str], message: str, *, cwd: Path | None = None
) -> None:
    for patch in patches:
        run("git", "apply", "--check", str(patch), cwd=cwd)
        run("git", "apply", str(patch), cwd=cwd)
    run("cargo", "+nightly", "fmt", "--all", "--", "--check", cwd=cwd)
    run("git", "add", *files, cwd=cwd)
    run(
        "git",
        "-c",
        "user.name=Linux Fieldwork CI",
        "-c",
        "user.email=linux-fieldwork@example.invalid",
        "commit",
        "-m",
        message,
        cwd=cwd,
    )


def seed_old_candidate_preimages() -> None:
    old_worktree = Path("/tmp/cache-affinity-old-preimage")
    if old_worktree.exists():
        run("git", "worktree", "remove", "--force", str(old_worktree))
        shutil.rmtree(old_worktree, ignore_errors=True)
    run("git", "worktree", "add", "--detach", str(old_worktree), CANONICAL_BASE)

    try:
        for commit, source_path, expected_blob, destination, commit_files, message in OLD_PATCHES:
            patch = materialize(commit, source_path, destination, expected_blob)
            run("git", "apply", "--check", str(patch), cwd=old_worktree)
            run("git", "apply", str(patch), cwd=old_worktree)
            if commit_files is None:
                continue
            run("cargo", "+nightly", "fmt", "--all", "--", "--check", cwd=old_worktree)
            run("git", "add", *commit_files, cwd=old_worktree)
            run(
                "git",
                "-c",
                "user.name=Linux Fieldwork CI",
                "-c",
                "user.email=linux-fieldwork@example.invalid",
                "commit",
                "-m",
                message,
                cwd=old_worktree,
            )

        candidate_copy = Path("/tmp/cache-affinity-frozen-v2.patch")
        candidate_copy.write_bytes(CANDIDATE_PATH.read_bytes())
        run("git", "apply", "--check", str(candidate_copy), cwd=old_worktree)
    finally:
        run("git", "worktree", "remove", "--force", str(old_worktree))


for path, expected in EXPECTED_BLOBS.items():
    actual = output("git", "hash-object", path)
    if actual != expected:
        raise RuntimeError(f"{path}: expected source blob {expected}, found {actual}")

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

# Reconstruct and commit the exact historical prerequisite tree in a temporary
# worktree. Those commits populate the repository object database with the
# preimage blobs recorded by the frozen v2 patch, while the --check proves the
# historical candidate/prerequisite pairing is still reconstructible.
seed_old_candidate_preimages()

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

# With the historical preimage blobs restored to the shared object database,
# three-way apply can perform an actual mechanical rebase of the frozen v2
# candidate onto the refreshed prerequisite chain.
run("git", "apply", "--3way", str(CANDIDATE_PATH))
run("cargo", "+nightly", "fmt", "--all", "--", "--check")

print("cache-affinity-old-preimages-reconstructed")
print("cache-affinity-submitted-acpi-prerequisite-applied")
print("cache-affinity-final-cache-error-prerequisite-applied")
print("cache-affinity-final-cache-identity-prerequisite-applied")
print("cache-affinity-final-cache-sharing-prerequisite-applied")
print("cache-affinity-stored-candidate-verified")
print("cache-affinity-stored-candidate-three-way-restacked")
print("cache-affinity-candidate-format-verified")
