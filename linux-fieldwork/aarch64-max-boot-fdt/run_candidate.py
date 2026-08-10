#!/usr/bin/env python3
import hashlib
import subprocess
from pathlib import Path

AFFINITY_COMMIT = "9acace966a333c9314cceedd0e6f1cdaa8812850"
AFFINITY_RUNNER_PATH = "linux-fieldwork/cache-affinity/run_candidate.py"
AFFINITY_RUNNER_BLOB = "a176dfaa2a639a301b3c4371c14952d9d87e6091"
AFFINITY_PATCH_PATH = "linux-fieldwork/cache-affinity/candidate.patch"
AFFINITY_PATCH_BLOB = "75601cb2fa2a7d8f8f85dcdd9c3724c41a18d947"

L3_COMMIT = "383eebc96afa743dd365c82f34b2feb944a71cf9"
L3_PATCH_PATH = "linux-fieldwork/fdt-l3-smt/candidate.patch"
L3_PATCH_BLOB = "239a2a7c9a7fe7031a594605f3801f2b06c53fa2"

CANDIDATE_PATH = Path("linux-fieldwork/aarch64-max-boot-fdt/candidate.patch")
CANDIDATE_BLOB = "c0fdacec33e6e2080118b568ed1668be5cea492f"
CANDIDATE_SHA256 = "0378049238e3625690577f11168d98ee66a35084d4a68f486632dba33550e694"


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
        raise RuntimeError(
            f"{source_path}: expected blob {expected_blob}, found {actual}"
        )
    return destination


for branch in [
    "linux-fieldwork/cache-affinity-selection",
    "linux-fieldwork/fdt-l3-smt",
]:
    run("git", "fetch", "--no-tags", "origin", branch)

# Apply and locally commit exact #543 v2.
affinity_runner = materialize(
    AFFINITY_COMMIT,
    AFFINITY_RUNNER_PATH,
    Path("/tmp/cache-affinity-runner.py"),
    AFFINITY_RUNNER_BLOB,
)
materialize(
    AFFINITY_COMMIT,
    AFFINITY_PATCH_PATH,
    Path(AFFINITY_PATCH_PATH),
    AFFINITY_PATCH_BLOB,
)
run("python3", str(affinity_runner))
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

# Apply and locally commit exact #546.
l3_patch = materialize(
    L3_COMMIT,
    L3_PATCH_PATH,
    Path("/tmp/fdt-l3-smt.patch"),
    L3_PATCH_BLOB,
)
run("git", "apply", "--check", str(l3_patch))
run("git", "apply", str(l3_patch))
run("cargo", "+nightly", "fmt", "--all", "--", "--check")
run("git", "add", "arch/src/aarch64/fdt.rs")
run(
    "git",
    "-c",
    "user.name=Linux Fieldwork CI",
    "-c",
    "user.email=linux-fieldwork@example.invalid",
    "commit",
    "-m",
    "ci: apply validated FDT L3 SMT prerequisite",
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

run("git", "apply", "--check", str(CANDIDATE_PATH))
run("git", "apply", str(CANDIDATE_PATH))
run("cargo", "+nightly", "fmt", "--all", "--", "--check")

print("aarch64-max-boot-prerequisites-applied")
print("aarch64-max-boot-stored-candidate-verified")
print("aarch64-max-boot-stored-candidate-applied")
print("aarch64-max-boot-candidate-format-verified")
