// Copyright © 2024 Microsoft Corporation
//
// SPDX-License-Identifier: Apache-2.0

use std::convert::TryFrom;
#[cfg(test)]
use std::env;
#[cfg(test)]
use std::fs::{self, File, OpenOptions};
use std::io::Error as IoError;
#[cfg(test)]
use std::io::{ErrorKind, Read};
use std::path::Path;
#[cfg(test)]
use std::path::PathBuf;
#[cfg(test)]
use std::thread;

#[cfg(test)]
use block::async_io::OwnedIoBuffer;
#[cfg(test)]
use block::disk_file::AsyncDiskFile;
#[cfg(test)]
use block::error::BlockErrorKind;
#[cfg(test)]
use block::formats::qcow::{Error as QcowError, QcowDisk};
#[cfg(test)]
use landlock::make_bitflags;
use landlock::{
    ABI, Access, AccessFs, BitFlags, Compatible, Ruleset, RulesetAttr, RulesetCreated,
    RulesetCreatedAttr, RulesetError, path_beneath_rules,
};
use thiserror::Error;
#[cfg(test)]
use vmm_sys_util::tempdir::TempDir;

#[derive(Debug, Error)]
pub enum LandlockError {
    /// All RulesetErrors from Landlock library are wrapped in this error
    #[error("Error creating/adding/restricting ruleset")]
    ManageRuleset(#[source] RulesetError),

    /// Error opening path
    #[error("Error opening path")]
    OpenPath(#[source] IoError),

    /// Invalid Landlock access
    #[error("Invalid Landlock access: {0}")]
    InvalidLandlockAccess(String),

    /// Invalid Path
    #[error("Invalid path")]
    InvalidPath,
}

// https://docs.rs/landlock/latest/landlock/enum.ABI.html for more info on ABI
static ABI: ABI = ABI::V3;

#[derive(Debug)]
pub(crate) struct LandlockAccess {
    access: BitFlags<AccessFs>,
}

impl TryFrom<&str> for LandlockAccess {
    type Error = LandlockError;

    fn try_from(s: &str) -> Result<LandlockAccess, LandlockError> {
        if s.is_empty() {
            return Err(LandlockError::InvalidLandlockAccess(
                "Access cannot be empty".to_string(),
            ));
        }

        let mut access = BitFlags::<AccessFs>::empty();
        for c in s.chars() {
            match c {
                'r' => access |= AccessFs::from_read(ABI),
                'w' => access |= AccessFs::from_write(ABI),
                _ => {
                    return Err(LandlockError::InvalidLandlockAccess(
                        format!("Invalid access: {c}").to_string(),
                    ));
                }
            }
        }
        Ok(LandlockAccess { access })
    }
}
pub struct Landlock {
    ruleset: RulesetCreated,
}

impl Landlock {
    pub fn new() -> Result<Landlock, LandlockError> {
        let file_access = AccessFs::from_all(ABI);

        let def_ruleset = Ruleset::default()
            .set_compatibility(landlock::CompatLevel::HardRequirement)
            .handle_access(file_access)
            .map_err(LandlockError::ManageRuleset)?
            .set_compatibility(landlock::CompatLevel::HardRequirement);

        // By default, rulesets are created in `BestEffort` mode. This lets Landlock
        // to enable all the supported rules and silently ignore the unsupported ones.
        let ruleset = def_ruleset.create().map_err(LandlockError::ManageRuleset)?;

        Ok(Landlock { ruleset })
    }

    pub(crate) fn add_rule(
        &mut self,
        path: &Path,
        access: BitFlags<AccessFs>,
    ) -> Result<(), LandlockError> {
        // path_beneath_rules in landlock crate handles file and directory access rules.
        // Incoming path/s are passed to path_beneath_rules, so that we don't
        // have to worry about the type of the path.
        let paths = vec![&path];
        let path_beneath_rules = path_beneath_rules(paths, access);
        self.ruleset
            .as_mut()
            .add_rules(path_beneath_rules)
            .map_err(LandlockError::ManageRuleset)?;
        Ok(())
    }

    pub(crate) fn add_rule_with_access(
        &mut self,
        path: &Path,
        access: &str,
    ) -> Result<(), LandlockError> {
        self.add_rule(path, LandlockAccess::try_from(access)?.access)?;
        Ok(())
    }

    pub fn restrict_self(self) -> Result<(), LandlockError> {
        self.ruleset
            .restrict_self()
            .map_err(LandlockError::ManageRuleset)?;
        Ok(())
    }
}

#[test]
fn test_try_from_access() {
    // These access rights could change in future versions of Landlock. Listing
    // them here explicitly to raise their visibility during code reviews.
    let read_access = make_bitflags!(AccessFs::{
        Execute
        | ReadFile
        | ReadDir
    });
    let write_access = make_bitflags!(AccessFs::{
        WriteFile
        | RemoveDir
        | RemoveFile
        | MakeChar
        | MakeDir
        | MakeReg
        | MakeSock
        | MakeFifo
        | MakeBlock
        | MakeSym
        | Refer
        | Truncate
    });
    let landlock_access = LandlockAccess::try_from("rw").unwrap();
    assert!(landlock_access.access == read_access | write_access);

    let landlock_access = LandlockAccess::try_from("r").unwrap();
    assert!(landlock_access.access == read_access);

    let landlock_access = LandlockAccess::try_from("w").unwrap();
    assert!(landlock_access.access == write_access);

    LandlockAccess::try_from("").unwrap_err();
}

#[test]
fn test_preopened_file_remains_usable_after_restriction() {
    let allowed = TempDir::new().unwrap();
    let denied = TempDir::new().unwrap();
    let allowed_path = allowed.as_path().join("allowed");
    let denied_path = denied.as_path().join("denied");

    fs::write(&allowed_path, b"allowed").unwrap();
    fs::write(&denied_path, b"preopened").unwrap();

    let preopened = File::open(&denied_path).unwrap();
    let allowed_dir = allowed.as_path().to_path_buf();

    thread::spawn(move || {
        let mut preopened = preopened;
        let mut landlock = Landlock::new().unwrap();
        landlock.add_rule_with_access(&allowed_dir, "r").unwrap();
        landlock.restrict_self().unwrap();

        File::open(&allowed_path).unwrap();

        let error = File::open(&denied_path).unwrap_err();
        assert_eq!(error.kind(), ErrorKind::PermissionDenied);

        let mut contents = String::new();
        preopened.read_to_string(&mut contents).unwrap();
        assert_eq!(contents, "preopened");
    })
    .join()
    .unwrap();
}

fn fieldwork_qcow_fixture() -> (PathBuf, PathBuf, PathBuf) {
    let overlay = PathBuf::from(env::var_os("FIELDWORK_QCOW_OVERLAY").unwrap());
    let allowed_dir = PathBuf::from(env::var_os("FIELDWORK_QCOW_ALLOWED_DIR").unwrap());
    let denied_backing = PathBuf::from(env::var_os("FIELDWORK_QCOW_DENIED_BACKING").unwrap());
    (overlay, allowed_dir, denied_backing)
}

#[test]
#[ignore = "requires an external Fieldwork QCOW backing fixture"]
fn test_qcow_backing_open_respects_landlock_order() {
    const MARKER: &[u8] = b"LFQCOW42";

    let (overlay, allowed_dir, denied_backing) = fieldwork_qcow_fixture();
    assert!(overlay.starts_with(&allowed_dir));
    assert!(!denied_backing.starts_with(&allowed_dir));

    let late_overlay = overlay.clone();
    let late_allowed_dir = allowed_dir.clone();
    let late_denied_backing = denied_backing.clone();
    thread::spawn(move || {
        let mut landlock = Landlock::new().unwrap();
        landlock
            .add_rule_with_access(&late_allowed_dir, "rw")
            .unwrap();
        landlock.restrict_self().unwrap();

        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .open(&late_overlay)
            .unwrap();
        let error = QcowDisk::new(file, false, true, true, false).unwrap_err();
        assert_eq!(error.kind(), BlockErrorKind::Io);
        match error.downcast_ref::<QcowError>() {
            Some(QcowError::BackingFileIo(path, source)) => {
                assert_eq!(Path::new(path), late_denied_backing);
                assert_eq!(source.kind(), ErrorKind::PermissionDenied);
            }
            other => panic!("expected denied QCOW backing-file open, got {other:?}"),
        }
    })
    .join()
    .unwrap();

    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .open(&overlay)
        .unwrap();
    let disk = QcowDisk::new(file, false, true, true, false).unwrap();
    thread::spawn(move || {
        let mut landlock = Landlock::new().unwrap();
        landlock.add_rule_with_access(&allowed_dir, "rw").unwrap();
        landlock.restrict_self().unwrap();

        let mut io = disk.create_async_io(1).unwrap();
        io.read_to_vec(0, OwnedIoBuffer::new(MARKER.len(), 1).unwrap(), 0)
            .unwrap();
        let completion = io.next_completed_request().unwrap();
        assert_eq!(completion.result, MARKER.len() as i32);
        assert_eq!(completion.buffer.unwrap().as_slice(), MARKER);
    })
    .join()
    .unwrap();
}
