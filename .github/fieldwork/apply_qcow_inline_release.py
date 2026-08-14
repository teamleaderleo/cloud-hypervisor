from pathlib import Path

path = Path("block/src/formats/qcow/metadata.rs")
text = path.read_text()

old = """        let mut deferred_unrefs = Vec::new();

        self.cache_l2_cluster_alloc(l1_index, l2_addr_disk)?;
"""
new = """        self.cache_l2_cluster_alloc(l1_index, l2_addr_disk)?;
"""
assert old in text
text = text.replace(old, new, 1)

old = """            let decompressed_cluster = self.decompress_l2_cluster(l2_entry)?;
            let cluster_addr = self.append_data_cluster(None)?;
            self.update_cluster_addr(l1_index, l2_index, cluster_addr, &mut deferred_unrefs)?;
            let nwritten = self
                .raw_file
                .file_mut()
                .write_at(&decompressed_cluster, cluster_addr)?;
            if nwritten != decompressed_cluster.len() {
                self.set_corrupt_bit_best_effort();
                return Err(io::Error::from_raw_os_error(EIO));
            }
            self.deallocate_compressed_cluster(l2_entry)?;
"""
new = """            let decompressed_cluster = self.decompress_l2_cluster(l2_entry)?;
            let cluster_addr = self.append_data_cluster(None)?;
            let nwritten = self
                .raw_file
                .file_mut()
                .write_at(&decompressed_cluster, cluster_addr)?;
            if nwritten != decompressed_cluster.len() {
                self.set_corrupt_bit_best_effort();
                return Err(io::Error::from_raw_os_error(EIO));
            }
            self.update_cluster_addr(l1_index, l2_index, cluster_addr)?;
            self.deallocate_compressed_cluster(l2_entry)?;
"""
assert old in text
text = text.replace(old, new, 1)

old_call = "self.update_cluster_addr(l1_index, l2_index, cluster_addr, &mut deferred_unrefs)?;"
assert text.count(old_call) == 1
text = text.replace(old_call, "self.update_cluster_addr(l1_index, l2_index, cluster_addr)?;", 1)

old = """        // Apply deferred L2 releases
        for addr in deferred_unrefs {
            self.set_cluster_refcount_track_freed(addr, 0)?;
        }

"""
assert old in text
text = text.replace(old, "", 1)

start = text.index("    fn update_cluster_addr(\n")
end = text.index("\n    /// Resizes the image", start)
replacement = """    fn update_cluster_addr(
        &mut self,
        l1_index: usize,
        l2_index: usize,
        cluster_addr: u64,
    ) -> io::Result<()> {
        let relocation = if self.l2_cache.get(l1_index).unwrap().dirty() {
            None
        } else {
            // Allocate the new cluster for the relocated L2 table before
            // releasing the old one: if this allocation fails (ENOSPC at
            // allocator exhaustion) the old table must stay off the free
            // lists, or a later allocation would hand it out and overwrite a
            // live L2 table (issue #8606). The cluster will be written when
            // the cache is flushed.
            let new_addr = self.get_new_cluster(None)?;
            self.set_cluster_refcount_track_freed(new_addr, 1)?;
            Some((self.l1_table[l1_index], new_addr))
        };

        // Prepare the replacement L2 contents before switching L1. If the
        // old-table refcount drop then fails, sync_caches() can still write a
        // complete replacement table rather than publishing an empty cluster.
        self.l2_cache.get_mut(l1_index).unwrap()[l2_index] = l2_entry_make_std(cluster_addr);

        if let Some((old_l2, new_addr)) = relocation {
            self.l1_table[l1_index] = new_addr; // marks l1_table dirty via IndexMut
            if old_l2 != 0 {
                self.set_cluster_refcount_track_freed(old_l2, 0)?;
                self.unref_clusters.push(old_l2);
            }
        }
        Ok(())
    }
"""
text = text[:start] + replacement + text[end:]

test_start = text.index(
    "    #[test]\n    fn relocated_l2_dropped_deferred_updates_keeps_refcount_owner() {"
)
test_end = text.index(
    "    #[test]\n    fn successful_l2_relocation_releases_old_table() {",
    test_start,
)
text = text[:test_start] + text[test_end:]

assert "deferred_unrefs" not in text
path.write_text(text)
