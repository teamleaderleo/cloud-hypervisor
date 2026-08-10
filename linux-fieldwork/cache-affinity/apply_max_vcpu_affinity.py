#!/usr/bin/env python3
from pathlib import Path

cpu_file = Path("vmm/src/cpu.rs")
cpu = cpu_file.read_text()

cpu = cpu.replace(
    '''fn cache_host_cpus_from_affinity(
    boot_vcpus: u32,
    affinity: &BTreeMap<u32, Box<[usize]>>,
    default_host_cpus: &[usize],
) -> Vec<usize> {
    let mut host_cpus = BTreeSet::new();
    for vcpu_id in 0..boot_vcpus {
''',
    '''fn cache_host_cpus_from_affinity(
    vcpu_count: u32,
    affinity: &BTreeMap<u32, Box<[usize]>>,
    default_host_cpus: &[usize],
) -> Vec<usize> {
    let mut host_cpus = BTreeSet::new();
    for vcpu_id in 0..vcpu_count {
''',
    1,
)

old_method = '''        let needs_default =
            (0..self.config.boot_vcpus).any(|vcpu_id| !self.affinity.contains_key(&vcpu_id));
'''
new_method = '''        let needs_default =
            (0..self.config.max_vcpus).any(|vcpu_id| !self.affinity.contains_key(&vcpu_id));
'''
if old_method not in cpu:
    raise RuntimeError("cache_host_cpus needs_default anchor changed")
cpu = cpu.replace(old_method, new_method, 1)

old_call = '''        Ok(cache_host_cpus_from_affinity(
            self.config.boot_vcpus,
            &self.affinity,
            &default_host_cpus,
        ))
'''
new_call = '''        Ok(cache_host_cpus_from_affinity(
            self.config.max_vcpus,
            &self.affinity,
            &default_host_cpus,
        ))
'''
if old_call not in cpu:
    raise RuntimeError("cache_host_cpus helper call anchor changed")
cpu = cpu.replace(old_call, new_call, 1)

module_end = '''    #[test]
    fn test_host_cpus_from_affinity_words_supports_high_cpu_ids() {
        let high_cpu = 1300usize;
        let word_bits = usize::BITS as usize;
        let mut words = vec![0usize; high_cpu / word_bits + 1];
        words[high_cpu / word_bits] |= 1usize << (high_cpu % word_bits);

        assert_eq!(host_cpus_from_affinity_words(&words), vec![high_cpu]);
    }
}
'''
module_replacement = '''    #[test]
    fn test_host_cpus_from_affinity_words_supports_high_cpu_ids() {
        let high_cpu = 1300usize;
        let word_bits = usize::BITS as usize;
        let mut words = vec![0usize; high_cpu / word_bits + 1];
        words[high_cpu / word_bits] |= 1usize << (high_cpu % word_bits);

        assert_eq!(host_cpus_from_affinity_words(&words), vec![high_cpu]);
    }

    #[test]
    fn test_cache_host_cpus_includes_hotpluggable_vcpus() {
        let affinity = BTreeMap::from([
            (0, vec![4].into_boxed_slice()),
            (1, vec![4].into_boxed_slice()),
            (2, vec![6].into_boxed_slice()),
            (3, vec![6].into_boxed_slice()),
        ]);

        assert_eq!(
            cache_host_cpus_from_affinity(4, &affinity, &[0, 1, 2, 3]),
            vec![4, 6]
        );
    }
}
'''
if module_end not in cpu:
    raise RuntimeError("dynamic affinity test module ending changed")
cpu = cpu.replace(module_end, module_replacement, 1)

cpu_file.write_text(cpu)
