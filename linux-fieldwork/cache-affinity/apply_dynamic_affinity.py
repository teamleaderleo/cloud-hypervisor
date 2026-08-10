#!/usr/bin/env python3
from pathlib import Path

cpu_file = Path("vmm/src/cpu.rs")
cpu = cpu_file.read_text()

old = '''#[cfg(target_arch = "aarch64")]
fn process_host_cpus() -> Result<Vec<usize>> {
    // SAFETY: all zeros is a valid cpu_set_t bit pattern.
    let mut cpuset: libc::cpu_set_t = unsafe { zeroed() };
    // SAFETY: cpuset points to writable storage of the advertised size.
    let ret = unsafe {
        libc::sched_getaffinity(
            0,
            mem::size_of::<libc::cpu_set_t>(),
            &mut cpuset,
        )
    };
    if ret != 0 {
        return Err(Error::HostCpuAffinity(io::Error::last_os_error()));
    }

    let mut host_cpus = Vec::new();
    for host_cpu in 0..libc::CPU_SETSIZE as usize {
        // SAFETY: host_cpu is bounded by CPU_SETSIZE and cpuset is initialized.
        if unsafe { libc::CPU_ISSET(host_cpu, &cpuset) } {
            host_cpus.push(host_cpu);
        }
    }
    Ok(host_cpus)
}
'''

new = '''#[cfg(target_arch = "aarch64")]
fn host_cpus_from_affinity_words(words: &[usize]) -> Vec<usize> {
    let word_bits = usize::BITS as usize;
    let mut host_cpus = Vec::new();

    for (word_index, word) in words.iter().enumerate() {
        for bit in 0..word_bits {
            if word & (1usize << bit) != 0 {
                host_cpus.push(word_index * word_bits + bit);
            }
        }
    }

    host_cpus
}

#[cfg(target_arch = "aarch64")]
fn process_host_cpus() -> Result<Vec<usize>> {
    let word_size = mem::size_of::<usize>();
    let initial_words = mem::size_of::<libc::cpu_set_t>().div_ceil(word_size);
    let mut words = vec![0usize; initial_words];

    loop {
        let cpusetsize = words.len() * word_size;
        // SAFETY: `words` is writable for `cpusetsize` bytes. The kernel treats
        // this argument as an opaque CPU mask and does not dereference it as a
        // Rust `cpu_set_t`.
        let ret = unsafe {
            libc::sched_getaffinity(
                0,
                cpusetsize,
                words.as_mut_ptr().cast::<libc::cpu_set_t>(),
            )
        };
        if ret == 0 {
            return Ok(host_cpus_from_affinity_words(&words));
        }

        let source = io::Error::last_os_error();
        if source.raw_os_error() != Some(libc::EINVAL) {
            return Err(Error::HostCpuAffinity(source));
        }
        words.resize(words.len() * 2, 0);
    }
}
'''

if old not in cpu:
    raise RuntimeError("fixed-size process_host_cpus body changed")
cpu = cpu.replace(old, new, 1)

module_end = '''    fn test_cache_host_cpus_adds_default_set_for_unpinned_vcpu() {
        let affinity = BTreeMap::from([(0, vec![4, 5].into_boxed_slice())]);
        assert_eq!(
            cache_host_cpus_from_affinity(2, &affinity, &[0, 1, 2, 3]),
            vec![0, 1, 2, 3, 4, 5]
        );
    }
}
'''
module_replacement = '''    fn test_cache_host_cpus_adds_default_set_for_unpinned_vcpu() {
        let affinity = BTreeMap::from([(0, vec![4, 5].into_boxed_slice())]);
        assert_eq!(
            cache_host_cpus_from_affinity(2, &affinity, &[0, 1, 2, 3]),
            vec![0, 1, 2, 3, 4, 5]
        );
    }

    #[test]
    fn test_host_cpus_from_affinity_words_supports_high_cpu_ids() {
        let high_cpu = 1300usize;
        let word_bits = usize::BITS as usize;
        let mut words = vec![0usize; high_cpu / word_bits + 1];
        words[high_cpu / word_bits] |= 1usize << (high_cpu % word_bits);

        assert_eq!(host_cpus_from_affinity_words(&words), vec![high_cpu]);
    }
}
'''
if module_end not in cpu:
    raise RuntimeError("cache affinity test module ending changed")
cpu = cpu.replace(module_end, module_replacement, 1)

cpu_file.write_text(cpu)
