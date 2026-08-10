#!/usr/bin/env python3
from pathlib import Path

cpu_file = Path("vmm/src/cpu.rs")
cpu = cpu_file.read_text()

start_marker = '''#[cfg(target_arch = "aarch64")]
fn process_host_cpus() -> Result<Vec<usize>> {
'''
end_marker = '''#[cfg(target_arch = "aarch64")]
fn cache_host_cpus_from_affinity(
'''
start = cpu.index(start_marker)
end = cpu.index(end_marker, start)

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
cpu = cpu[:start] + new + cpu[end:]

module_marker = '''#[cfg(all(test, target_arch = "aarch64"))]
mod cache_affinity_tests {
'''
cpu.index(module_marker)
if not cpu.endswith("}\n"):
    raise RuntimeError("cache affinity test module is no longer file-final")

high_cpu_test = '''
    #[test]
    fn test_host_cpus_from_affinity_words_supports_high_cpu_ids() {
        let high_cpu = 1300usize;
        let word_bits = usize::BITS as usize;
        let mut words = vec![0usize; high_cpu / word_bits + 1];
        words[high_cpu / word_bits] |= 1usize << (high_cpu % word_bits);

        assert_eq!(host_cpus_from_affinity_words(&words), vec![high_cpu]);
    }
'''
cpu = cpu[:-2] + high_cpu_test + "}\n"

cpu_file.write_text(cpu)
