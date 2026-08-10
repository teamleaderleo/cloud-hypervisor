#!/usr/bin/env python3
import subprocess
from pathlib import Path

EXPECTED_BLOBS = {
    "arch/src/aarch64/cache.rs": "9200c59627beba0e6366b5105d2fe51a312efaed",
    "vmm/src/cpu.rs": "5d9499878b04f7c0fb53cece5768988ceb439d25",
    "vmm/src/acpi.rs": "6ac7666ebdc49c67fbc6233c135e8645f7e64e0f",
    "vmm/src/vm.rs": "12a9fe0ad7068df7b26082b32de65d6f54b33d04",
}

ACPI_PREREQUISITE_COMMIT = "0a2f55acbd23b7f44899a69132a4236ef9240027"
ACPI_PREREQUISITE_PATH = "linux-fieldwork/acpi-errors/candidate.patch"
ACPI_PREREQUISITE_BLOB = "034cebd92cf31e3b415cdd3d205035b96cd9c1fb"


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def output(*args: str) -> str:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


for path, expected in EXPECTED_BLOBS.items():
    actual = output("git", "hash-object", path)
    if actual != expected:
        raise RuntimeError(f"{path}: expected source blob {expected}, found {actual}")

run(
    "git",
    "fetch",
    "--no-tags",
    "--depth=20",
    "origin",
    "linux-fieldwork/acpi-error-propagation",
)
prerequisite = subprocess.run(
    ["git", "show", f"{ACPI_PREREQUISITE_COMMIT}:{ACPI_PREREQUISITE_PATH}"],
    check=True,
    capture_output=True,
).stdout
prerequisite_path = Path("/tmp/acpi-prerequisite.patch")
prerequisite_path.write_bytes(prerequisite)
actual_prerequisite_blob = output("git", "hash-object", str(prerequisite_path))
if actual_prerequisite_blob != ACPI_PREREQUISITE_BLOB:
    raise RuntimeError(
        "ACPI prerequisite patch identity mismatch: "
        f"expected {ACPI_PREREQUISITE_BLOB}, found {actual_prerequisite_blob}"
    )

run("git", "apply", "--check", str(prerequisite_path))
run("git", "apply", str(prerequisite_path))
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

candidate_dir = Path(__file__).parent
for patch_name in ["candidate.patch", "propagation.patch"]:
    patch_path = candidate_dir / patch_name
    run("git", "apply", "--check", str(patch_path))
    run("git", "apply", str(patch_path))

run("cargo", "+nightly", "fmt", "--all", "--", "--check")
print("cache-error-acpi-prerequisite-applied")
print("cache-error-candidate-applied")
print("cache-error-candidate-format-verified")
