"""Disposable HTTP fixture for browser tests; no external downloads."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from downloader.service import Service
from downloader.runtime import Runtime

with tempfile.TemporaryDirectory() as temp, patch.object(Runtime, 'detect', return_value={
        'aria2': 'native', 'video': 'native', 'ffmpeg': True, 'flatpak': False, 'varia': False}):
    service = Service(Path(temp) / 'home', Path(temp) / 'settings')
    try:
        (Path(temp) / 'home' / 'Downloads').mkdir(parents=True, exist_ok=True)
        service.stopping.set()
        service.scheduler.join(2)
        service.stopping.clear()
        service.receiver.set_password('test')
        service.receiver.configure('local', 0)
        service.store.save_settings({'receiver_mode': 'local', 'receiver_port': service.receiver.port})
        for index in range(55):
            job = service.add(f'https://example.org/history-{index}.bin')
            service.store.update(job, status='complete', completed=1024, total=1024)
        (Path(service.store.settings()['directory']) / 'on-handheld.torrent').write_bytes(
            b'd4:infod6:lengthi3e4:name12:handheld.bin12:piece lengthi4e6:pieces20:' + b'x' * 20 + b'ee')
        # Browser-only metadata adapter. Actual torrent parsing/downloads are
        # separately exercised with native aria2 in test_integration.py.
        done = threading.Event()
        def metadata():
            while not done.wait(.1):
                with service.lock:
                    for job in service.store.jobs():
                        if not job['file_count'] and (job['kind'] == 'torrent-file' or job['source'].endswith('.torrent')):
                            service.store.save_torrent(job['id'], 'a' * 40,
                                [dict(index=i, name=f'file-{i}.bin', length=i * 1024) for i in range(1, 206)])
                            service.store.update(job['id'], status='selecting')
        worker = threading.Thread(target=metadata, daemon=True)
        worker.start()
        print(json.dumps(dict(service.receiver.status(), password='test')), flush=True)
        sys.stdin.readline()
    finally:
        if 'done' in locals():
            done.set(); worker.join(2)
        service.shutdown()
