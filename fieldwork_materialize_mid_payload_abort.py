from pathlib import Path

p = Path('vmm/src/migration/transport.rs')
text = p.read_text()

old_worker = '''            receive_memory_ranges(guest_memory, &req, socket)?;\n            Response::ok().write_to(socket)?;\n'''
new_worker = '''            if !receive_memory_ranges_abortable(guest_memory, &req, socket, Some(kill_evt))? {\n                debug!("Got signal to tear down connection while receiving memory payload.");\n                return Ok(());\n            }\n            Response::ok().write_to(socket)?;\n'''
if text.count(old_worker) != 1:
    raise SystemExit(f'worker call anchor count={text.count(old_worker)}')
text = text.replace(old_worker, new_worker, 1)

old_sig = '''pub(crate) fn receive_memory_ranges(\n    guest_memory: &GuestMemoryAtomic<GuestMemoryMmap>,\n    req: &Request,\n    socket: &mut SocketStream,\n) -> Result<(), MigratableError> {\n    debug_assert_eq!(req.command(), Command::Memory);\n'''
new_sig = '''pub(crate) fn receive_memory_ranges(\n    guest_memory: &GuestMemoryAtomic<GuestMemoryMmap>,\n    req: &Request,\n    socket: &mut SocketStream,\n) -> Result<(), MigratableError> {\n    receive_memory_ranges_abortable(guest_memory, req, socket, None).map(|_| ())\n}\n\nfn receive_memory_ranges_abortable(\n    guest_memory: &GuestMemoryAtomic<GuestMemoryMmap>,\n    req: &Request,\n    socket: &mut SocketStream,\n    kill_evt: Option<&EventFd>,\n) -> Result<bool, MigratableError> {\n    debug_assert_eq!(req.command(), Command::Memory);\n'''
if text.count(old_sig) != 1:
    raise SystemExit(f'receive signature anchor count={text.count(old_sig)}')
text = text.replace(old_sig, new_sig, 1)

old_read = '''        loop {\n            let bytes_read = mem\n                .read_volatile_from(\n'''
new_read = '''        loop {\n            if let Some(kill_evt) = kill_evt\n                && !wait_for_readable(socket, kill_evt)\n                    .context("Failed to poll memory payload fds")\n                    .map_err(MigratableError::MigrateReceive)?\n            {\n                return Ok(false);\n            }\n\n            let bytes_read = mem\n                .read_volatile_from(\n'''
if text.count(old_read) != 1:
    raise SystemExit(f'payload read anchor count={text.count(old_read)}')
text = text.replace(old_read, new_read, 1)

old_tail = '''    Ok(())\n}\n\n#[cfg(test)]\nmod tests {\n'''
new_tail = '''    Ok(true)\n}\n\n#[cfg(test)]\nmod tests {\n'''
if text.count(old_tail) != 1:
    raise SystemExit(f'receive tail anchor count={text.count(old_tail)}')
text = text.replace(old_tail, new_tail, 1)

marker = 'fn test_memory_worker_abort_interrupts_stalled_payload()'
if marker in text:
    raise SystemExit('regression already present')
text += r'''

#[cfg(test)]
mod migration_payload_abort_tests {
    use std::io::Write;
    use std::os::unix::net::UnixStream;
    use std::sync::mpsc;
    use std::thread;
    use std::time::Duration;

    use vm_memory::{GuestAddress, GuestMemoryAtomic};
    use vm_migration::protocol::{MemoryRange, MemoryRangeTable, Request};
    use vmm_sys_util::eventfd::EventFd;

    use super::{ReceiveAdditionalConnections, SocketStream};
    use crate::GuestMemoryMmap;

    #[test]
    fn test_memory_worker_abort_interrupts_stalled_payload() {
        let memory = GuestMemoryMmap::from_ranges(&[(GuestAddress(0), 0x1000)]).unwrap();
        let guest_memory = GuestMemoryAtomic::new(memory);
        let kill_evt = EventFd::new(0).unwrap();
        let worker_kill_evt = kill_evt.try_clone().unwrap();
        let (mut sender, receiver) = UnixStream::pair().unwrap();
        let (done_tx, done_rx) = mpsc::channel();

        thread::spawn(move || {
            let mut socket = SocketStream::Unix(receiver);
            let result = ReceiveAdditionalConnections::worker_receive_memory(
                &mut socket,
                &worker_kill_evt,
                &guest_memory,
            );
            let _ = done_tx.send(result);
        });

        let mut ranges = MemoryRangeTable::default();
        ranges.push(MemoryRange {
            gpa: 0,
            length: 0x1000,
        });
        Request::memory(ranges.length())
            .write_to(&mut sender)
            .unwrap();
        ranges.write_to(&mut sender).unwrap();
        sender.write_all(&[0x5a]).unwrap();

        thread::sleep(Duration::from_millis(100));
        kill_evt.write(1).unwrap();

        let result = done_rx
            .recv_timeout(Duration::from_millis(750))
            .expect("memory worker did not stop after kill event while payload was stalled");
        assert!(result.is_ok(), "memory worker returned {result:?}");
    }
}
'''
p.write_text(text)
