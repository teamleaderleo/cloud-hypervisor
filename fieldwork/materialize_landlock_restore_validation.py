from pathlib import Path

path = Path("cloud-hypervisor/tests/integration.rs")
text = path.read_text()


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    text = text.replace(old, new, 1)


test_anchor = """    #[test]\n    fn test_snapshot_restore_basic() {\n        snapshot_restore_common::_test_snapshot_restore(\n            snapshot_restore_common::SnapshotRestoreTest::default(),\n        );\n    }\n\n"""
test_insert = test_anchor + """    #[test]\n    #[cfg(all(not(feature = \"mshv\"), target_arch = \"x86_64\"))]\n    fn test_snapshot_restore_landlock_qcow_backing() {\n        snapshot_restore_common::_test_snapshot_restore_landlock_qcow_backing();\n    }\n\n"""
replace_once(test_anchor, test_insert, "snapshot test")

import_anchor = """mod snapshot_restore_common {\n    use std::fs::remove_dir_all;\n    use std::process::Command;\n\n    use crate::*;\n"""
import_insert = """mod snapshot_restore_common {\n    use std::fs::remove_dir_all;\n    #[cfg(target_arch = \"x86_64\")]\n    use std::fs;\n    #[cfg(target_arch = \"x86_64\")]\n    use std::path::Path;\n    use std::process::Command;\n\n    #[cfg(target_arch = \"x86_64\")]\n    use serde_json::{Value, json};\n\n    use crate::*;\n"""
replace_once(import_anchor, import_insert, "snapshot imports")

helper_anchor = """    pub(crate) const CLOCK_DOWNTIME_SECS: u64 = 30;\n    pub(crate) const CLOCK_SKEW_TOLERANCE_SECS: i64 = 15;\n\n"""
helper = r'''    #[cfg(target_arch = "x86_64")]
    fn set_snapshot_landlock(snapshot_dir: &str, backing_path: Option<&Path>) {
        let config_path = Path::new(snapshot_dir).join("config.json");
        let mut config: Value = serde_json::from_slice(&fs::read(&config_path).unwrap()).unwrap();
        config["landlock_enable"] = Value::Bool(true);
        config["landlock_rules"] = match backing_path {
            Some(path) => json!([{
                "path": path.to_str().unwrap(),
                "access": "r",
            }]),
            None => Value::Null,
        };
        fs::write(config_path, serde_json::to_vec_pretty(&config).unwrap()).unwrap();
    }

    #[cfg(target_arch = "x86_64")]
    pub(crate) fn _test_snapshot_restore_landlock_qcow_backing() {
        let disk_config = UbuntuDiskConfig::new(JAMMY_IMAGE_NAME.to_string());
        let guest = Guest::new(Box::new(disk_config));
        let kernel_path = direct_kernel_boot_path();
        let backing_path = Path::new(
            guest
                .disk_config
                .disk(DiskType::OperatingSystem)
                .unwrap(),
        )
        .to_path_buf();
        let overlay_path = guest.tmp_dir.as_path().join("landlock-overlay.qcow2");

        assert!(
            Command::new("qemu-img")
                .args(["create", "-f", "qcow2", "-F", "raw", "-b"])
                .arg(&backing_path)
                .arg(&overlay_path)
                .status()
                .unwrap()
                .success()
        );

        let api_socket_source = format!("{}.landlock-source", temp_api_path(&guest.tmp_dir));
        let event_path_source =
            format!("{}.landlock-source", temp_event_monitor_path(&guest.tmp_dir));
        let snapshot_dir = temp_snapshot_dir_path(&guest.tmp_dir);
        let overlay_params = format!(
            "path={},image_type=qcow2,backing_files=on",
            overlay_path.to_str().unwrap()
        );
        let cloudinit_params = format!(
            "path={},image_type=raw",
            guest.disk_config.disk(DiskType::CloudInit).unwrap()
        );

        let mut child = GuestCommand::new(&guest)
            .args(["--api-socket", &api_socket_source])
            .args([
                "--event-monitor",
                format!("path={event_path_source}").as_str(),
            ])
            .args(["--cpus", "boot=2"])
            .args(["--memory", "size=1G"])
            .args(["--kernel", kernel_path.to_str().unwrap()])
            .args(["--cmdline", DIRECT_KERNEL_BOOT_CMDLINE])
            .args(["--disk", overlay_params.as_str(), cloudinit_params.as_str()])
            .args(["--net", guest.default_net_string().as_str()])
            .capture_output()
            .spawn()
            .unwrap();

        let r = panic::catch_unwind(|| {
            guest.wait_vm_boot().unwrap();
            snapshot_and_check_events(&api_socket_source, &snapshot_dir, &event_path_source);
        });
        kill_child(&mut child);
        let output = child.wait_with_output().unwrap();
        handle_child_output(r, &output);

        set_snapshot_landlock(&snapshot_dir, None);

        let api_socket_denied = format!("{}.landlock-denied", temp_api_path(&guest.tmp_dir));
        let event_path_denied =
            format!("{}.landlock-denied", temp_event_monitor_path(&guest.tmp_dir));
        let mut denied = GuestCommand::new(&guest)
            .args(["--api-socket", &api_socket_denied])
            .args([
                "--event-monitor",
                format!("path={event_path_denied}").as_str(),
            ])
            .args([
                "--restore",
                format!("source_url=file://{snapshot_dir}").as_str(),
            ])
            .capture_output()
            .spawn()
            .unwrap();

        let denied_exited = wait_until(Duration::from_secs(15), || {
            denied.try_wait().unwrap().is_some()
        });
        if !denied_exited {
            kill_child(&mut denied);
        }
        let denied_output = denied.wait_with_output().unwrap();
        let denied_logs = format!(
            "{}\n{}",
            String::from_utf8_lossy(&denied_output.stdout),
            String::from_utf8_lossy(&denied_output.stderr)
        );
        assert!(
            denied_exited,
            "restore retained an unlisted QCOW backing path: {denied_logs}"
        );
        assert!(
            denied_logs.contains("Permission denied"),
            "restore failed for the wrong reason: {denied_logs}"
        );
        assert!(
            denied_logs.contains(backing_path.to_str().unwrap()),
            "denied backing path missing from error chain: {denied_logs}"
        );

        set_snapshot_landlock(&snapshot_dir, Some(&backing_path));

        let api_socket_allowed = format!("{}.landlock-allowed", temp_api_path(&guest.tmp_dir));
        let event_path_allowed =
            format!("{}.landlock-allowed", temp_event_monitor_path(&guest.tmp_dir));
        let mut allowed = GuestCommand::new(&guest)
            .args(["--api-socket", &api_socket_allowed])
            .args([
                "--event-monitor",
                format!("path={event_path_allowed}").as_str(),
            ])
            .args([
                "--restore",
                format!("source_url=file://{snapshot_dir}").as_str(),
            ])
            .capture_output()
            .spawn()
            .unwrap();

        let r = panic::catch_unwind(|| {
            let restored = [&MetaEvent {
                event: "restored".to_string(),
                device_id: None,
            }];
            assert!(wait_for_latest_events_exact(
                Duration::from_secs(30),
                &restored,
                &event_path_allowed
            ));
            assert!(wait_until(Duration::from_secs(30), || remote_command(
                &api_socket_allowed,
                "info",
                None
            )));
        });
        kill_child(&mut allowed);
        let output = allowed.wait_with_output().unwrap();
        handle_child_output(r, &output);

        let api_socket_uffd = format!("{}.landlock-uffd", temp_api_path(&guest.tmp_dir));
        let event_path_uffd =
            format!("{}.landlock-uffd", temp_event_monitor_path(&guest.tmp_dir));
        let mut uffd = GuestCommand::new(&guest)
            .args(["--api-socket", &api_socket_uffd])
            .args([
                "--event-monitor",
                format!("path={event_path_uffd}").as_str(),
            ])
            .args([
                "--restore",
                format!(
                    "source_url=file://{snapshot_dir},memory_restore_mode=ondemand"
                )
                .as_str(),
            ])
            .capture_output()
            .spawn()
            .unwrap();

        let r = panic::catch_unwind(|| {
            let restored = [&MetaEvent {
                event: "restored".to_string(),
                device_id: None,
            }];
            assert!(wait_for_latest_events_exact(
                Duration::from_secs(30),
                &restored,
                &event_path_uffd
            ));
            assert!(wait_until(Duration::from_secs(30), || remote_command(
                &api_socket_uffd,
                "info",
                None
            )));
        });
        kill_child(&mut uffd);
        let output = uffd.wait_with_output().unwrap();
        handle_child_output(r, &output);
        let logs = format!(
            "{}\n{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        assert!(
            logs.contains("UFFD restore: demand-paged restore enabled"),
            "expected UFFD restore path: {logs}"
        );
    }

'''
replace_once(helper_anchor, helper_anchor + helper, "snapshot helper")

path.write_text(text)
