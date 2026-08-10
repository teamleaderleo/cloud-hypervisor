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

ACPI_PREREQUISITE_BASE = "a1fcb9f790616ac615f66de73be540b0b20844b1"
ACPI_PREREQUISITE_COMMIT = "e9c86bacee14a2fd6fe871dc678c6b3f1ac4012a"
ACPI_PREREQUISITE_BRANCH = "fix/8666-acpi-errors"


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
    "--depth=100",
    "origin",
    ACPI_PREREQUISITE_BRANCH,
)
fetched_head = output("git", "rev-parse", "FETCH_HEAD")
if fetched_head != ACPI_PREREQUISITE_COMMIT:
    raise RuntimeError(
        "ACPI prerequisite branch moved: "
        f"expected {ACPI_PREREQUISITE_COMMIT}, found {fetched_head}"
    )

changed = output(
    "git",
    "diff",
    "--name-only",
    ACPI_PREREQUISITE_BASE,
    ACPI_PREREQUISITE_COMMIT,
    "--",
    "vmm/src/acpi.rs",
    "vmm/src/vm.rs",
).splitlines()
if changed != ["vmm/src/acpi.rs", "vmm/src/vm.rs"]:
    raise RuntimeError(f"unexpected ACPI prerequisite scope: {changed}")

prerequisite = subprocess.run(
    [
        "git",
        "diff",
        "--binary",
        ACPI_PREREQUISITE_BASE,
        ACPI_PREREQUISITE_COMMIT,
        "--",
        "vmm/src/acpi.rs",
        "vmm/src/vm.rs",
    ],
    check=True,
    capture_output=True,
).stdout
prerequisite_path = Path("/tmp/acpi-prerequisite.patch")
prerequisite_path.write_bytes(prerequisite)

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
    "ci: apply submitted ACPI prerequisite",
)

candidate_dir = Path(__file__).parent
for patch_name in ["candidate.patch", "propagation.patch"]:
    patch_path = candidate_dir / patch_name
    run("git", "apply", "--check", str(patch_path))
    run("git", "apply", str(patch_path))

run("cargo", "+nightly", "fmt", "--all", "--", "--check")
print("cache-error-submitted-acpi-prerequisite-applied")
print("cache-error-candidate-applied")
print("cache-error-candidate-format-verified")
