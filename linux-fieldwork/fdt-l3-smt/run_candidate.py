#!/usr/bin/env python3
import hashlib
import subprocess
from pathlib import Path

AFFINITY_COMMIT = "9acace966a333c9314cceedd0e6f1cdaa8812850"
AFFINITY_RUNNER_PATH = "linux-fieldwork/cache-affinity/run_candidate.py"
AFFINITY_RUNNER_BLOB = "a176dfaa2a639a301b3c4371c14952d9d87e6091"
AFFINITY_PATCH_PATH = "linux-fieldwork/cache-affinity/candidate.patch"
AFFINITY_PATCH_BLOB = "75601cb2fa2a7d8f8f85dcdd9c3724c41a18d947"

CANDIDATE_PATH = Path("linux-fieldwork/fdt-l3-smt/candidate.patch")
CANDIDATE_BLOB = "239a2a7c9a7fe7031a594605f3801f2b06c53fa2"
CANDIDATE_SHA256 = "146c6af0807ab5a7b8af98958a6b9836af9d44075711ef6d73e62621d14b3665"


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def output(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def materialize(commit: str, source_path: str, destination: Path, expected_blob: str) -> None:
    content = subprocess.run(
        ["git", "show", f"{commit}:{source_path}"],
        check=True,
        capture_output=True,
    ).stdout
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    actual = output("git", "hash-object", str(destination))
    if actual != expected_blob:
        raise RuntimeError(
            f"{source_path}: expected blob {expected_blob}, found {actual}"
        )


run("git", "fetch", "--no-tags", "origin", "linux-fieldwork/cache-affinity-selection")
runner = Path("/tmp/cache-affinity-runner.py")
materialize(AFFINITY_COMMIT, AFFINITY_RUNNER_PATH, runner, AFFINITY_RUNNER_BLOB)
materialize(AFFINITY_COMMIT, AFFINITY_PATCH_PATH, Path(AFFINITY_PATCH_PATH), AFFINITY_PATCH_BLOB)
run("python3", str(runner))

# Freeze #543 v2 as the exact prerequisite so the retained #546 product diff
# remains only arch/src/aarch64/fdt.rs.
run(
    "git",
    "add",
    "arch/src/aarch64/cache.rs",
    "arch/src/aarch64/fdt.rs",
    "arch/src/aarch64/mod.rs",
    "vmm/src/cpu.rs",
    "vmm/src/vm.rs",
    "vmm/src/vm_config.rs",
)
run(
    "git",
    "-c",
    "user.name=Linux Fieldwork CI",
    "-c",
    "user.email=linux-fieldwork@example.invalid",
    "commit",
    "-m",
    "ci: apply validated cache affinity v2 prerequisite",
)
Path(AFFINITY_PATCH_PATH).unlink()
try:
    Path("linux-fieldwork/cache-affinity").rmdir()
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

print("fdt-l3-smt-prerequisites-applied")
print("fdt-l3-smt-stored-candidate-verified")
print("fdt-l3-smt-stored-candidate-applied")
print("fdt-l3-smt-candidate-format-verified")
