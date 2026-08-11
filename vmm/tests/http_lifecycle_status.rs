// Copyright 2026 The Cloud Hypervisor Authors. All rights reserved.
//
// SPDX-License-Identifier: Apache-2.0

use std::io;

use micro_http::StatusCode;
use vmm::api::ApiError;
use vmm::api::http::{HttpError, error_response};
use vmm::vm::{Error as VmError, VmState};

fn status(error: ApiError) -> StatusCode {
    error_response(HttpError::ApiError(error)).status()
}

#[test]
fn lifecycle_state_conflicts_map_to_conflict() {
    assert_eq!(
        status(ApiError::VmPause(VmError::VmNotRunning)),
        StatusCode::Conflict
    );
    assert_eq!(
        status(ApiError::VmCreate(VmError::VmAlreadyCreated)),
        StatusCode::Conflict
    );
    assert_eq!(
        status(ApiError::VmRemoveDevice(VmError::VmMigrating)),
        StatusCode::Conflict
    );
    assert_eq!(
        status(ApiError::VmSnapshot(VmError::VmRestoring)),
        StatusCode::Conflict
    );
    assert_eq!(
        status(ApiError::VmShutdown(VmError::InvalidStateTransition(
            VmState::Running,
            VmState::Running,
        ))),
        StatusCode::Conflict
    );
}

#[test]
fn missing_vm_remains_not_found() {
    assert_eq!(
        status(ApiError::VmInfo(VmError::VmNotCreated)),
        StatusCode::NotFound
    );
}

#[test]
fn internal_vm_failures_remain_internal_server_error() {
    assert_eq!(
        status(ApiError::VmPause(VmError::EventFdClone(io::Error::other(
            "synthetic internal failure",
        )))),
        StatusCode::InternalServerError
    );
}
