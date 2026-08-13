from pathlib import Path

p = Path('vmm/src/lib.rs')
text = p.read_text()

marker = 'fn test_receive_request_eof_emits_failure_event()'
if marker in text:
    raise SystemExit('test already present')
insert = r'''

    #[test]
    fn test_receive_request_eof_emits_failure_event() {
        use std::env;
        use std::fs;
        use std::os::unix::net::UnixStream;
        use std::process;
        use std::thread;
        use std::time::{Duration, SystemTime, UNIX_EPOCH};

        let monitor = event_monitor::set_monitor(None).unwrap();
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let socket_path = env::temp_dir().join(format!(
            "cloud-hypervisor-migration-eof-{}-{unique}.sock",
            process::id()
        ));

        let client_path = socket_path.clone();
        let connector = thread::spawn(move || {
            for _ in 0..500 {
                if client_path.exists() {
                    let stream = UnixStream::connect(&client_path).unwrap();
                    drop(stream);
                    return;
                }
                thread::sleep(Duration::from_millis(2));
            }
            panic!("migration listener did not become ready");
        });

        let mut vmm = create_dummy_vmm();
        let mut data = receive_data(None, None);
        data.receiver_url = format!("unix:{}", socket_path.display());

        let result = vmm.vm_receive_migration(data);
        connector.join().unwrap();
        let _ = fs::remove_file(&socket_path);
        assert!(result.is_err(), "peer EOF should fail the receive attempt");

        let events: Vec<String> = monitor.rx.try_iter().collect();
        let joined = events.join("\n");
        assert!(
            joined.contains("\"event\": \"migration-receive-ready\""),
            "missing ready event: {joined}"
        );
        assert!(
            joined.contains("\"event\": \"migration-receive-started\""),
            "missing started event: {joined}"
        );
        assert!(
            joined.contains("\"event\": \"migration-receive-failed\""),
            "receive attempt returned an error without a failure event: {joined}"
        );
    }
'''
needle = '\n    #[test]\n    fn test_vmm_vm_create() {'
if text.count(needle) != 1:
    raise SystemExit(f'unit-test insertion anchor count={text.count(needle)}')
text = text.replace(needle, insert + needle, 1)

start_marker = '        // Accept the connection and get the socket\n'
end_marker = '        Ok(())\n    }\n\n    /// Dispatches a migration.\n'
if text.count(start_marker) != 1 or text.count(end_marker) != 1:
    raise SystemExit(
        f'anchors start={text.count(start_marker)} end={text.count(end_marker)}'
    )
start = text.index(start_marker)
end = text.index(end_marker, start)
block = text[start:end]
failed_event = '                event!("vm", "migration-receive-failed");\n'
if block.count(failed_event) != 1:
    raise SystemExit(f'failed-event owner count={block.count(failed_event)}')
block = block.replace(failed_event, '', 1)
indented = ''.join('    ' + line if line.strip() else line for line in block.splitlines(True))
replacement = (
    '        let receive_result: result::Result<(), MigratableError> = (|| {\n'
    + indented
    + '            Ok(())\n'
    + '        })();\n\n'
    + '        if receive_result.is_err() {\n'
    + '            event!("vm", "migration-receive-failed");\n'
    + '        }\n\n'
    + '        receive_result\n'
)
text = text[:start] + replacement + text[end + len('        Ok(())\n'):]
p.write_text(text)
