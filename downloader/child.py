"""Linux child supervisor: stop the engine if the loader backend disappears.

Runs in a fresh interpreter, avoiding preexec_fn in the threaded backend.
The per-transfer lock remains held until the engine has exited and flushed
its resume data, including during an unexpected backend crash.
"""
import ctypes
import fcntl
import os
import signal
import subprocess
import sys
import time


def main():
    parent, lock_path, *command = sys.argv[1:]
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'Cannot set engine parent-death signal')
    if os.getppid() != int(parent):
        return 1
    lock = None
    if lock_path != '-':
        lock = open(lock_path, 'a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Previous transfer is still stopping. Retry in a moment.', file=sys.stderr, flush=True)
            return 1
    if stopping:
        return 1
    child = subprocess.Popen(command)
    try:
        while child.poll() is None:
            if stopping:
                # Includes Flatpak's descendants. Ignore our own group signal.
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                os.killpg(os.getpgrp(), signal.SIGTERM)
                try:
                    child.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgrp(), signal.SIGKILL)
                break
            time.sleep(.1)
        return child.wait()
    finally:
        if lock:
            lock.close()


if __name__ == '__main__':
    sys.exit(main())
