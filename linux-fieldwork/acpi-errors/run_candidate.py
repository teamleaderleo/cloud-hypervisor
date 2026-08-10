#!/usr/bin/env python3
import subprocess
from pathlib import Path

EXPECTED_BLOBS = {
    "vmm/src/acpi.rs": "6ac7666ebdc49c67fbc6233c135e8645f7e64e0f",
    "vmm/src/vm.rs": "12a9fe0ad7068df7b26082b32de65d6f54b33d04",
}

for path, expected in EXPECTED_BLOBS.items():
    actual = subprocess.run(
        ["git", "hash-object", path],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual != expected:
        raise RuntimeError(
            f"{path}: expected exact source blob {expected}, found {actual}"
        )

candidate_path = Path(__file__).with_name("candidate.patch")
comment_path = Path(__file__).with_name("comment.patch")
subprocess.run(["git", "apply", "--check", str(candidate_path)], check=True)
subprocess.run(["git", "apply", str(candidate_path)], check=True)
subprocess.run(["git", "apply", "--check", str(comment_path)], check=True)
subprocess.run(["git", "apply", str(comment_path)], check=True)
subprocess.run(["cargo", "+nightly", "fmt", "--all", "--", "--check"], check=True)
print("acpi-error-candidate-applied")
print("acpi-error-comment-refinement-applied")
print("acpi-error-candidate-format-verified")
