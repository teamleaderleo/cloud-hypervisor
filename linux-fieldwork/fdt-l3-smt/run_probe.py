#!/usr/bin/env python3
import subprocess
from pathlib import Path

AFFINITY_COMMIT = "9acace966a333c9314cceedd0e6f1cdaa8812850"
AFFINITY_RUNNER_PATH = "linux-fieldwork/cache-affinity/run_candidate.py"
AFFINITY_RUNNER_BLOB = "a176dfaa2a639a301b3c4371c14952d9d87e6091"
AFFINITY_PATCH_PATH = "linux-fieldwork/cache-affinity/candidate.patch"
AFFINITY_PATCH_BLOB = "75601cb2fa2a7d8f8f85dcdd9c3724c41a18d947"


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

# Freeze #543 v2 as a prerequisite so the retained #546 diff remains test-only.
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

fdt_path = Path("arch/src/aarch64/fdt.rs")
fdt = fdt_path.read_text()
probe = r'''

#[cfg(test)]
mod l3_smt_mapping_tests {
    #[test]
    fn test_current_l3_package_selector_exceeds_emitted_nodes_with_smt() {
        let threads_per_core = 2u32;
        let cores_per_package = 2u32;
        let packages = 2u32;
        let logical_cpus = threads_per_core * cores_per_package * packages;

        let current: Vec<u32> = (0..logical_cpus)
            .map(|cpu_id| cpu_id / cores_per_package)
            .collect();
        let expected: Vec<u32> = (0..logical_cpus)
            .map(|cpu_id| cpu_id / (threads_per_core * cores_per_package))
            .collect();

        assert_eq!(current, vec![0, 0, 1, 1, 2, 2, 3, 3]);
        assert_eq!(expected, vec![0, 0, 0, 0, 1, 1, 1, 1]);
        assert!(current.iter().any(|package_id| *package_id >= packages));
        assert!(expected.iter().all(|package_id| *package_id < packages));
    }
}
'''
if "mod l3_smt_mapping_tests" in fdt:
    raise RuntimeError("FDT L3 SMT probe already present")
fdt_path.write_text(fdt + probe)
run("cargo", "+nightly", "fmt", "--all")
print("fdt-l3-smt-prerequisites-applied")
print("fdt-l3-smt-test-only-probe-injected")
