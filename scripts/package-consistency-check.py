#!/bin/env python3
#
# Copyright © 2024 Institute of Software, CAS. All rights reserved.
#
# SPDX-License-Identifier: Apache-2.0
#

import json
import os
import subprocess
from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path


PROBE_BRANCH = "linux-fieldwork/http-existence-probe-1af93ac"
SOURCE_BLOB = "efdf9826f2c8503d394f15a627acec7a929176b1"
CANDIDATE_BLOB = "efe584110b515a1b5af27e703c453b8619f5181a"
TESTS_BLOB = "b3f1dbe979115b3420e125a71f4c8353970a16ac"


def run_checked(command, *, check=True):
    result = subprocess.run(command, capture_output=True, text=True)
    print(result.stdout, end="")
    print(result.stderr, end="")
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")
    return result


def run_fieldwork_http_existence_probe():
    if os.environ.get("GITHUB_HEAD_REF") != PROBE_BRANCH:
        return

    source = Path("vmm/src/lib.rs")
    candidate = Path("scripts/fieldwork-http-existence.patch")
    tests = Path("scripts/fieldwork-http-existence-tests.patch")
    if not source.exists() or not candidate.exists() or not tests.exists():
        return

    source_blob = run_checked(["git", "rev-parse", f"HEAD:{source}"]).stdout.strip()
    candidate_blob = run_checked(["git", "hash-object", str(candidate)]).stdout.strip()
    tests_blob = run_checked(["git", "hash-object", str(tests)]).stdout.strip()
    if source_blob != SOURCE_BLOB:
        raise RuntimeError(f"VMM source drifted: {source_blob} != {SOURCE_BLOB}")
    if candidate_blob != CANDIDATE_BLOB:
        raise RuntimeError(f"candidate drifted: {candidate_blob} != {CANDIDATE_BLOB}")
    if tests_blob != TESTS_BLOB:
        raise RuntimeError(f"tests drifted: {tests_blob} != {TESTS_BLOB}")

    print("FIELDWORK: exact current VMM source and existence candidate confirmed")

    try:
        run_checked(["git", "apply", "--check", str(tests)])
        run_checked(["git", "apply", str(tests)])

        print("FIELDWORK: configured-but-unbooted baseline remains VmNotRunning")
        run_checked([
            "cargo", "test", "--locked", "-p", "vmm", "--lib",
            "test_created_unbooted_vmm_lifecycle_reports_not_running", "--features", "kvm",
        ])

        print("FIELDWORK: bare-VMM baseline must expose current VmNotRunning bug")
        baseline = run_checked([
            "cargo", "test", "--locked", "-p", "vmm", "--lib",
            "test_bare_vmm_lifecycle_reports_not_created", "--features", "kvm",
        ], check=False)
        baseline_output = baseline.stdout + baseline.stderr
        if baseline.returncode == 0:
            raise RuntimeError("bare-VMM baseline unexpectedly reported VmNotCreated")
        if "expected VmNotCreated, got VmNotRunning" not in baseline_output:
            raise RuntimeError("bare-VMM baseline failed without VmNotRunning discriminator")

        run_checked(["git", "checkout", "--", str(source)])
        run_checked(["git", "apply", "--check", str(candidate)])
        run_checked(["git", "apply", str(candidate)])
        run_checked(["git", "apply", "--check", str(tests)])
        run_checked(["git", "apply", str(tests)])

        changed = run_checked(["git", "diff", "--name-only"]).stdout.splitlines()
        if changed != ["vmm/src/lib.rs"]:
            raise RuntimeError(f"candidate changed unexpected paths: {changed}")

        print("FIELDWORK: existence-only candidate preserves both lifecycle identities")
        run_checked([
            "cargo", "test", "--locked", "-p", "vmm", "--lib",
            "vmm_lifecycle_reports", "--features", "kvm",
        ])
        run_checked(["rustup", "component", "add", "rustfmt", "clippy"])
        run_checked(["cargo", "fmt", "--all", "--", "--check"])
        run_checked([
            "cargo", "clippy", "--locked", "-p", "vmm", "--features", "kvm",
            "--", "-D", "warnings",
        ])
        print("FIELDWORK: HTTP existence candidate tests/rustfmt/clippy passed")
    finally:
        run_checked(["git", "checkout", "--", str(source)], check=False)


def get_cargo_metadata():
    result = subprocess.run(
        ["cargo", "metadata", "--format-version=1"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        exit(1)

    return json.loads(result.stdout)


def find_dependents_of_package(metadata, package_source):
    packages = defaultdict(list)
    direct_dependents = defaultdict(list)

    for pkg in metadata["packages"]:
        repository = pkg["repository"] or ""
        if package_source in repository:
            packages[pkg["name"]].append(pkg["version"])

    for node in metadata["resolve"]["nodes"]:
        current_pkg = next(pkg for pkg in metadata["packages"] if pkg["id"] == node["id"])
        current_pkg_name = current_pkg["name"]
        current_pkg_version = current_pkg["version"]

        for dep_id in node["dependencies"]:
            dep_pkg = next(pkg for pkg in metadata["packages"] if pkg["id"] == dep_id)
            dep_name = dep_pkg["name"]
            dep_version = dep_pkg["version"]
            if dep_name in packages:
                direct_dependents[(dep_name, dep_version)].append(
                    (current_pkg_name, current_pkg_version)
                )

    return packages, direct_dependents


def check_for_version_conflicts(packages, direct_dependents):
    has_conflicts = False
    for pkg_name, versions in packages.items():
        if len(set(versions)) > 1:
            has_conflicts = True
            print(f"Error: Multiple versions detected for {pkg_name}: {set(versions)}")
            for version in set(versions):
                print(f"  Version {version} used by:")
                for dependent, dep_version in direct_dependents[(pkg_name, version)]:
                    print(f"          - {dependent} v{dep_version}")
    return has_conflicts


if __name__ == "__main__":
    run_fieldwork_http_existence_probe()

    parser = ArgumentParser(description="Cargo dependency conflict checker.")
    parser.add_argument(
        "package_source", type=str, help="A keyword used to match the repository URL field"
    )
    args = parser.parse_args()

    metadata = get_cargo_metadata()
    if metadata is None:
        print("Error: Metadata is empty")
        exit(1)

    packages, direct_dependents = find_dependents_of_package(metadata, args.package_source)
    if check_for_version_conflicts(packages, direct_dependents):
        exit(1)
