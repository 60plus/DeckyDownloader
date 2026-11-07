import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from downloader.engines import spawn, stop_process


@unittest.skipUnless(sys.platform == 'linux', 'Linux process supervision')
class SupervisorTests(unittest.TestCase):
    def wait_file(self, path):
        deadline = time.monotonic() + 5
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue(path.exists())

    def test_backend_crash_terminates_engine_and_releases_lock(self):
        import fcntl
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine_pid = root / 'engine.pid'
            guard_pid = root / 'guard.pid'
            lock = root / 'engine.lock'
            engine_code = f"import os,time;from pathlib import Path;Path({str(engine_pid)!r}).write_text(str(os.getpid()));time.sleep(60)"
            parent_code = ("import os,time;from pathlib import Path;from downloader.engines import spawn;"
                           f"p=spawn([{sys.executable!r},'-c',{engine_code!r}],dict(os.environ),lock_path={str(lock)!r});"
                           f"Path({str(guard_pid)!r}).write_text(str(p.pid));time.sleep(60)")
            parent = subprocess.Popen([sys.executable, '-c', parent_code])
            try:
                self.wait_file(engine_pid)
                parent.kill()
                parent.wait(5)
                pid = int(engine_pid.read_text())
                deadline = time.monotonic() + 7
                while time.monotonic() < deadline:
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        break
                    time.sleep(.1)
                else:
                    self.fail('Engine survived backend crash')
                with lock.open('a') as handle:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(5)
                if guard_pid.exists():
                    try:
                        os.killpg(int(guard_pid.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_lock_prevents_duplicate_writers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker, lock = root / 'started', root / 'engine.lock'
            code = f"import time;from pathlib import Path;Path({str(marker)!r}).write_text('yes');time.sleep(30)"
            first = spawn([sys.executable, '-c', code], dict(os.environ), lock_path=lock)
            try:
                self.wait_file(marker)
                second = spawn([sys.executable, '-c', 'raise RuntimeError("must not execute")'],
                               dict(os.environ), lock_path=lock, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                output = second.communicate(timeout=5)[0].decode()
                self.assertEqual(second.returncode, 1)
                self.assertIn('still stopping', output)
                self.assertNotIn('must not execute', output)
            finally:
                stop_process(first)


if __name__ == '__main__':
    unittest.main()
