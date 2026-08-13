// Copyright © 2026 Contributors to the Cloud Hypervisor project
//
// SPDX-License-Identifier: Apache-2.0

pub(crate) const DEFAULT_SYSTEM_MANUFACTURER: &str = "Cloud Hypervisor";
pub(crate) const DEFAULT_SYSTEM_PRODUCT_NAME: &str = "cloud-hypervisor";

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SmbiosConfig {
    pub system: Option<SmbiosSystem>,
    pub chassis: Option<SmbiosChassisConfig>,
    pub oem_strings: Box<[String]>,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SmbiosSystem {
    pub manufacturer: Option<String>,
    pub product_name: Option<String>,
    pub version: Option<String>,
    pub serial_number: Option<String>,
    pub uuid: Option<String>,
    pub sku_number: Option<String>,
    pub family: Option<String>,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SmbiosChassisConfig {
    pub asset_tag: Option<String>,
}

impl SmbiosConfig {
    pub fn is_empty(&self) -> bool {
        *self == Self::default()
    }
}
