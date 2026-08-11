# Copyright © 2026 Contributors to the Cloud Hypervisor project
#
# SPDX-License-Identifier: Apache-2.0

"""Run the Linux Fieldwork HTTP existence probe inside package consistency."""

import os
import subprocess
from pathlib import Path


BRANCH = "linux-fieldwork/http-existence-probe-1af93ac"
SOURCE_BLOB = "efdf9826f2c8503d394f15a627acec7a929176b1"
CANDIDATE_BLOB = "efe584110b515a1b5af27e703c453b8619f5181a"
TESTS_BLOB = "b3f1dbe979115b3420e125a71f4c8353970a16ac"


def run(command, *, check=True):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", flush=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")
    return result


def probe():
    if os.environ.get("GITHUB_HEAD_REF") != BRANCH:
        return

    source = Path("vmm/src/lib.rs")
    candidate = Path("scripts/fieldwork-http-existence.patch")
    tests = Path("scripts/fieldwork-http-existence-tests.patch")

    source_blob = run(["git", "rev-parse", f"HEAD:{source}"]).stdout.strip()
    candidate_blob = run(["git", "hash-object", str(candidate)]).stdout.strip()
    tests_blob = run(["git", "hash-object", str(tests)]).stdout.strip()
    if source_blob != SOURCE_BLOB:
        raise RuntimeError(f"VMM source drifted: {source_blob} != {SOURCE_BLOB}")
    if candidate_blob != CANDIDATE_BLOB:
        raise RuntimeError(f"candidate drifted: {candidate_blob} != {CANDIDATE_BLOB}")
    if tests_blob != TESTS_BLOB:
        raise RuntimeError(f"tests drifted: {tests_blob} != {TESTS_BLOB}")

    print("FIELDWORK: exact current VMM source and existence candidate confirmed", flush=True)

    try:
        run(["git", "apply", "--check", str(tests)])
        run(["git", "apply", str(tests)])

        print("FIELDWORK: configured-but-unbooted baseline must remain VmNotRunning", flush=True)
        run([
            "cargo", "test", "--locked", "-p", "vmm", "--lib",
            "test_created_unbooted_vmm_lifecycle_reports_not_running", "--features", "kvm",
        ])

        print("FIELDWORK: bare-VMM baseline must fail with VmNotRunning", flush=True)
        baseline = run([
            "cargo", "test", "--locked", "-p", "vmm", "--lib",
            "test_bare_vmm_lifecycle_reports_not_created", "--features", "kvm",
        ], check=False)
        baseline_output = baseline.stdout + baseline.stderr
        if baseline.returncode == 0:
            raise RuntimeError("bare-VMM baseline unexpectedly reported VmNotCreated")
        if "expected VmNotCreated, got VmNotRunning" not in baseline_output:
            raise RuntimeError("bare-VMM baseline failed without VmNotRunning discriminator")

        run(["git", "checkout", "--", str(source)])
        run(["git", "apply", "--check", str(candidate)])
        run(["git", "apply", str(candidate)])
        run(["git", "apply", "--check", str(tests)])
        run(["git", "apply", str(tests)])

        changed = run(["git", "diff", "--name-only"]).stdout.splitlines()
        if changed != ["vmm/src/lib.rs"]:
            raise RuntimeError(f"candidate changed unexpected paths: {changed}")

        print("FIELDWORK: existence-only candidate preserves both lifecycle identities", flush=True)
        run([
            "cargo", "test", "--locked", "-p", "vmm", "--lib",
            "vmm_lifecycle_reports", "--features", "kvm",
        ])
        run(["rustup", "component", "add", "rustfmt", "clippy"])
        run(["cargo", "fmt", "--all", "--", "--check"])
        run([
            "cargo", "clippy", "--locked", "-p", "vmm", "--features", "kvm",
            "--", "-D", "warnings",
        ])
        print("FIELDWORK: HTTP existence candidate tests/rustfmt/clippy passed", flush=True)
    finally:
        run(["git", "checkout", "--", str(source)], check=False)


probe()
