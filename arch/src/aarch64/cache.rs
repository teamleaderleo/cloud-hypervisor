// Copyright 2020 Arm Limited (or its affiliates). All rights reserved.
// Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
//
// Portions Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the THIRD-PARTY file.

use std::num::ParseIntError;
use std::path::{Path, PathBuf};
use std::{fs, io, result};

use log::warn;
use thiserror::Error;

const CACHE_SYSFS_PATH: &str = "/sys/devices/system/cpu/cpu0/cache";

#[derive(Debug, Error)]
pub enum Error {
    #[error("Failed to access cache topology path {path:?}")]
    AccessCacheTopology {
        path: PathBuf,
        #[source]
        source: io::Error,
    },

    #[error("Failed to read cache property {path:?}")]
    ReadCacheProperty {
        path: PathBuf,
        #[source]
        source: io::Error,
    },

    #[error("Failed to parse cache property {path:?}")]
    ParseCacheProperty {
        path: PathBuf,
        #[source]
        source: ParseIntError,
    },

    #[error("Invalid cache size format in {path:?}")]
    InvalidCacheSize { path: PathBuf },

    #[error("Cache size in {path:?} exceeds u32 bytes")]
    CacheSizeOverflow { path: PathBuf },
}

pub type Result<T> = result::Result<T, Error>;

#[derive(Copy, Clone)]
pub enum CacheLevel {
    /// L1 data cache
    L1D = 0,
    /// L1 instruction cache
    L1I = 1,
    /// L2 cache
    L2 = 2,
    /// L3 cache
    L3 = 3,
}

impl CacheLevel {
    fn index(self) -> u8 {
        self as u8
    }
}

fn cache_property_path(cache_path: &Path, cache_level: CacheLevel, property: &str) -> PathBuf {
    cache_path
        .join(format!("index{}", cache_level.index()))
        .join(property)
}

fn read_optional_property(path: &Path) -> Result<Option<String>> {
    match fs::read_to_string(path) {
        Ok(value) => Ok(Some(value)),
        Err(source) if source.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(source) => Err(Error::ReadCacheProperty {
            path: path.to_path_buf(),
            source,
        }),
    }
}

fn get_cache_size_from(cache_path: &Path, cache_level: CacheLevel) -> Result<u32> {
    let path = cache_property_path(cache_path, cache_level, "size");
    let Some(src) = read_optional_property(&path)? else {
        return Ok(0);
    };
    let src = src.trim();

    let (digits, multiplier) = if let Some(digits) = src.strip_suffix('K') {
        (digits, 1u32 << 10)
    } else if let Some(digits) = src.strip_suffix('M') {
        (digits, 1u32 << 20)
    } else if let Some(digits) = src.strip_suffix('G') {
        (digits, 1u32 << 30)
    } else {
        return Err(Error::InvalidCacheSize { path });
    };

    let value = digits
        .parse::<u32>()
        .map_err(|source| Error::ParseCacheProperty {
            path: path.clone(),
            source,
        })?;

    value
        .checked_mul(multiplier)
        .ok_or(Error::CacheSizeOverflow { path })
}

/// NOTE: cache size file directory example,
/// "/sys/devices/system/cpu/cpu0/cache/index0/size".
pub fn get_cache_size(cache_level: CacheLevel) -> Result<u32> {
    get_cache_size_from(Path::new(CACHE_SYSFS_PATH), cache_level)
}

fn get_cache_u32_from(cache_path: &Path, cache_level: CacheLevel, property: &str) -> Result<u32> {
    let path = cache_property_path(cache_path, cache_level, property);
    let Some(src) = read_optional_property(&path)? else {
        return Ok(0);
    };

    src.trim()
        .parse::<u32>()
        .map_err(|source| Error::ParseCacheProperty { path, source })
}

/// NOTE: coherency_line_size file directory example,
/// "/sys/devices/system/cpu/cpu0/cache/index0/coherency_line_size".
pub fn get_cache_coherency_line_size(cache_level: CacheLevel) -> Result<u32> {
    get_cache_u32_from(
        Path::new(CACHE_SYSFS_PATH),
        cache_level,
        "coherency_line_size",
    )
}

/// NOTE: number_of_sets file directory example,
/// "/sys/devices/system/cpu/cpu0/cache/index0/number_of_sets".
pub fn get_cache_number_of_sets(cache_level: CacheLevel) -> Result<u32> {
    get_cache_u32_from(Path::new(CACHE_SYSFS_PATH), cache_level, "number_of_sets")
}

fn get_cache_shared_from(cache_path: &Path, cache_level: CacheLevel) -> Result<bool> {
    if matches!(cache_level, CacheLevel::L1D | CacheLevel::L1I) {
        return Ok(false);
    }

    let path = cache_property_path(cache_path, cache_level, "shared_cpu_list");
    let Some(src) = read_optional_property(&path)? else {
        return Ok(false);
    };
    let src = src.trim();

    Ok(!src.is_empty() && (src.contains('-') || src.contains(',')))
}

/// NOTE: shared_cpu_list file directory example,
/// "/sys/devices/system/cpu/cpu0/cache/index0/shared_cpu_list".
pub fn get_cache_shared(cache_level: CacheLevel) -> Result<bool> {
    get_cache_shared_from(Path::new(CACHE_SYSFS_PATH), cache_level)
}

#[derive(Default, Copy, Clone, Debug)]
pub struct CacheTopologyInfo {
    pub l1_d_cache_size: u32,
    pub l1_d_cache_line_size: u32,
    pub l1_d_cache_sets: u32,

    pub l1_i_cache_size: u32,
    pub l1_i_cache_line_size: u32,
    pub l1_i_cache_sets: u32,

    pub l2_cache_size: u32,
    pub l2_cache_line_size: u32,
    pub l2_cache_sets: u32,

    pub l3_cache_size: u32,
    pub l3_cache_line_size: u32,
    pub l3_cache_sets: u32,

    pub l2_cache_shared: bool,
    pub l3_cache_shared: bool,
}

fn read_cache_topology_from(cache_path: &Path) -> Result<Option<CacheTopologyInfo>> {
    match fs::metadata(cache_path) {
        Ok(_) => {}
        Err(source) if source.kind() == io::ErrorKind::NotFound => {
            warn!("Cache topology information is not available in sysfs.");
            return Ok(None);
        }
        Err(source) => {
            return Err(Error::AccessCacheTopology {
                path: cache_path.to_path_buf(),
                source,
            });
        }
    }

    let mut info = CacheTopologyInfo {
        l1_d_cache_size: get_cache_size_from(cache_path, CacheLevel::L1D)?,
        l1_d_cache_line_size: get_cache_u32_from(
            cache_path,
            CacheLevel::L1D,
            "coherency_line_size",
        )?,
        l1_d_cache_sets: get_cache_u32_from(cache_path, CacheLevel::L1D, "number_of_sets")?,

        l1_i_cache_size: get_cache_size_from(cache_path, CacheLevel::L1I)?,
        l1_i_cache_line_size: get_cache_u32_from(
            cache_path,
            CacheLevel::L1I,
            "coherency_line_size",
        )?,
        l1_i_cache_sets: get_cache_u32_from(cache_path, CacheLevel::L1I, "number_of_sets")?,

        l2_cache_size: get_cache_size_from(cache_path, CacheLevel::L2)?,
        l2_cache_line_size: get_cache_u32_from(cache_path, CacheLevel::L2, "coherency_line_size")?,
        l2_cache_sets: get_cache_u32_from(cache_path, CacheLevel::L2, "number_of_sets")?,

        l3_cache_size: get_cache_size_from(cache_path, CacheLevel::L3)?,
        l3_cache_line_size: get_cache_u32_from(cache_path, CacheLevel::L3, "coherency_line_size")?,
        l3_cache_sets: get_cache_u32_from(cache_path, CacheLevel::L3, "number_of_sets")?,

        l2_cache_shared: false,
        l3_cache_shared: false,
    };

    if info.l2_cache_size != 0 {
        info.l2_cache_shared = get_cache_shared_from(cache_path, CacheLevel::L2)?;
    }
    if info.l3_cache_size != 0 {
        info.l3_cache_shared = get_cache_shared_from(cache_path, CacheLevel::L3)?;
    }

    Ok(Some(info))
}

/// Reads cache topology information from sysfs for cpu0.
pub fn read_cache_topology() -> Result<Option<CacheTopologyInfo>> {
    read_cache_topology_from(Path::new(CACHE_SYSFS_PATH))
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::{env, process};

    use super::*;

    static NEXT_TEST_DIR: AtomicUsize = AtomicUsize::new(0);

    struct TestDir(PathBuf);

    impl TestDir {
        fn new() -> Self {
            let path = env::temp_dir().join(format!(
                "cloud-hypervisor-cache-test-{}-{}",
                process::id(),
                NEXT_TEST_DIR.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }

        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for TestDir {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }

    fn write_property(cache_path: &Path, index: u8, property: &str, value: &str) {
        let index_path = cache_path.join(format!("index{index}"));
        fs::create_dir_all(&index_path).unwrap();
        fs::write(index_path.join(property), value).unwrap();
    }

    #[test]
    fn test_missing_cache_root() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("missing");

        assert!(read_cache_topology_from(&cache_path).unwrap().is_none());
    }

    #[test]
    fn test_missing_cache_properties_use_defaults() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();

        let info = read_cache_topology_from(&cache_path).unwrap().unwrap();

        assert_eq!(info.l1_d_cache_size, 0);
        assert_eq!(info.l1_d_cache_line_size, 0);
        assert_eq!(info.l1_d_cache_sets, 0);
        assert_eq!(info.l2_cache_size, 0);
        assert!(!info.l2_cache_shared);
    }

    #[test]
    fn test_valid_cache_properties() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();

        write_property(&cache_path, 0, "size", "32K\n");
        write_property(&cache_path, 0, "coherency_line_size", "64\n");
        write_property(&cache_path, 0, "number_of_sets", "128\n");
        write_property(&cache_path, 2, "size", "1024K\n");
        write_property(&cache_path, 2, "coherency_line_size", "64\n");
        write_property(&cache_path, 2, "number_of_sets", "2048\n");
        write_property(&cache_path, 2, "shared_cpu_list", "0-3\n");

        let info = read_cache_topology_from(&cache_path).unwrap().unwrap();

        assert_eq!(info.l1_d_cache_size, 32 * 1024);
        assert_eq!(info.l1_d_cache_line_size, 64);
        assert_eq!(info.l1_d_cache_sets, 128);
        assert_eq!(info.l2_cache_size, 1024 * 1024);
        assert_eq!(info.l2_cache_line_size, 64);
        assert_eq!(info.l2_cache_sets, 2048);
        assert!(info.l2_cache_shared);
    }

    #[test]
    fn test_malformed_cache_size_is_error() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_property(&cache_path, 0, "size", "32Q\n");

        assert!(matches!(
            read_cache_topology_from(&cache_path),
            Err(Error::InvalidCacheSize { .. })
        ));
    }

    #[test]
    fn test_malformed_decimal_is_error() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_property(&cache_path, 0, "coherency_line_size", "invalid\n");

        assert!(matches!(
            read_cache_topology_from(&cache_path),
            Err(Error::ParseCacheProperty { .. })
        ));
    }

    #[test]
    fn test_cache_property_io_error_is_error() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir_all(cache_path.join("index0/size")).unwrap();

        assert!(matches!(
            read_cache_topology_from(&cache_path),
            Err(Error::ReadCacheProperty { .. })
        ));
    }

    #[test]
    fn test_cache_size_overflow_is_error() {
        let temp = TestDir::new();
        let cache_path = temp.path().join("cache");
        fs::create_dir(&cache_path).unwrap();
        write_property(&cache_path, 0, "size", "4194304K\n");

        assert!(matches!(
            read_cache_topology_from(&cache_path),
            Err(Error::CacheSizeOverflow { .. })
        ));
    }
}
