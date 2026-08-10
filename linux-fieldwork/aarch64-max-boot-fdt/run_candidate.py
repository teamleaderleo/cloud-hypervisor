#!/usr/bin/env python3
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

config_path = Path("vmm/src/config.rs")
config = config_path.read_text()

error_anchor = '''    /// Max is less than boot
    #[error("Max CPUs ({0}) lower than boot CPUs ({1})")]
    CpusMaxLowerThanBoot(u32 /* max vCPUs */, u32 /* boot vCPUs */),
'''
error_replacement = error_anchor + '''    #[cfg(target_arch = "aarch64")]
    /// CPU hotplug is unsupported on AArch64.
    #[error("CPU hotplug is not supported on AArch64")]
    Aarch64CpuHotplugUnsupported,
'''
if error_anchor not in config:
    raise RuntimeError("CPU validation error anchor changed")
config = config.replace(error_anchor, error_replacement, 1)

validation_anchor = '''        if self.cpus.max_vcpus < self.cpus.boot_vcpus {
            return Err(ValidationError::CpusMaxLowerThanBoot(
                self.cpus.max_vcpus,
                self.cpus.boot_vcpus,
            ));
        }
'''
validation_replacement = validation_anchor + '''
        #[cfg(target_arch = "aarch64")]
        if self.cpus.max_vcpus != self.cpus.boot_vcpus {
            return Err(ValidationError::Aarch64CpuHotplugUnsupported);
        }
'''
if validation_anchor not in config:
    raise RuntimeError("CPU max/boot validation anchor changed")
config = config.replace(validation_anchor, validation_replacement, 1)

test_anchor = '''        let mut still_valid_config = valid_config.clone();
        still_valid_config.cpus.max_vcpus = 8;
        still_valid_config.cpus.boot_vcpus = 8;
        still_valid_config.cpus.topology = Some(CpuTopology {
            threads_per_core: 2,
            cores_per_die: 4,
            dies_per_package: 1,
            packages: 1,
        });
        still_valid_config.validate().unwrap();
'''
test_addition = test_anchor + '''
        #[cfg(target_arch = "aarch64")]
        {
            let mut invalid_config = valid_config.clone();
            invalid_config.cpus.max_vcpus = 4;
            invalid_config.cpus.boot_vcpus = 2;
            invalid_config.cpus.topology = Some(CpuTopology {
                threads_per_core: 1,
                cores_per_die: 4,
                dies_per_package: 1,
                packages: 1,
            });
            assert_eq!(
                invalid_config.validate(),
                Err(ValidationError::Aarch64CpuHotplugUnsupported)
            );

            let mut still_valid_config = valid_config.clone();
            still_valid_config.cpus.max_vcpus = 4;
            still_valid_config.cpus.boot_vcpus = 4;
            still_valid_config.cpus.topology = Some(CpuTopology {
                threads_per_core: 1,
                cores_per_die: 4,
                dies_per_package: 1,
                packages: 1,
            });
            still_valid_config.validate().unwrap();
        }
'''
if test_anchor not in config:
    raise RuntimeError("configuration validation test anchor changed")
config = config.replace(test_anchor, test_addition, 1)

config_path.write_text(config)
run("cargo", "+nightly", "fmt", "--all")
print("aarch64-max-boot-prerequisites-applied")
print("aarch64-max-boot-validation-candidate-applied")
