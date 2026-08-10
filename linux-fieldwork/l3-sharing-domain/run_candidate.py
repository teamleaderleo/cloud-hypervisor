#!/usr/bin/env python3
import hashlib
import subprocess
from pathlib import Path

MAX_BOOT_COMMIT = "ea179f3c934efcb29eea5c482ce72ba4c0389fbc"
MAX_BOOT_RUNNER_PATH = "linux-fieldwork/aarch64-max-boot-fdt/run_candidate.py"
MAX_BOOT_RUNNER_BLOB = "9c78de564f521a7cfb0e18b9a1db873e784bfa0e"
MAX_BOOT_PATCH_PATH = "linux-fieldwork/aarch64-max-boot-fdt/candidate.patch"
MAX_BOOT_PATCH_BLOB = "c0fdacec33e6e2080118b568ed1668be5cea492f"

CANDIDATE_PATH = Path("linux-fieldwork/l3-sharing-domain/candidate.patch")
CANDIDATE_BLOB = "c3ac26a31a302bfd01962aa0d33f6a44e58da908"
CANDIDATE_SHA256 = "e9c8f5fb20be1ef7c4a63c95c8e098059fa92f3bd1b2bb0a87cedcf84aac067c"


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

run("git", "apply", "--check", str(CANDIDATE_PATH))
run("git", "apply", str(CANDIDATE_PATH))
run("cargo", "+nightly", "fmt", "--all", "--", "--check")

print("l3-sharing-domain-prerequisites-applied")
print("l3-sharing-domain-stored-candidate-verified")
print("l3-sharing-domain-stored-candidate-applied")
print("l3-sharing-domain-candidate-format-verified")
