"""Real engine tests against a local HTTP server; no third-party media."""
import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import socket
import struct
import http.client
import base64
import json
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, quote

from downloader.service import Service
from downloader.engines import stop_process
from downloader.ports import reserve_port, release_port

DATA = (bytes(range(256)) * 32768)


def bencode(value):
    if isinstance(value, int):
        return b'i' + str(value).encode() + b'e'
    if isinstance(value, bytes):
        return str(len(value)).encode() + b':' + value
    if isinstance(value, list):
        return b'l' + b''.join(bencode(item) for item in value) + b'e'
    return b'd' + b''.join(bencode(key) + bencode(value[key]) for key in sorted(value)) + b'e'


class Handler(BaseHTTPRequestHandler):
    ranges = []
    media = b''
    torrent = b''
    peers = set()

    def log_message(self, *args):
        pass

    def do_HEAD(self):
        self.serve(False)

    def do_GET(self):
        self.serve(True)

    def serve(self, body):
        if self.path.startswith('/announce'):
            query = parse_qs(urlsplit(self.path).query)
            port = int(query['port'][0])
            self.peers.add(port)
            peers = b''.join(socket.inet_aton('127.0.0.1') + struct.pack('!H', peer) for peer in self.peers if peer != port)
            response = bencode({b'interval': 1, b'peers': peers})
            self.send_response(200)
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        if self.path == '/missing':
            self.send_error(404)
            return
        data = self.torrent if self.path.endswith('.torrent') else self.media if self.path.endswith('.mp4') else DATA
        start, end = 0, len(data) - 1
        range_value = self.headers.get('Range')
        if range_value:
            self.ranges.append(range_value)
            parts = range_value.replace('bytes=', '').split('-')
            start = int(parts[0])
            end = min(end, int(parts[1])) if parts[1] else end
            if start >= len(data):
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{len(data)}')
                self.end_headers()
                return
        self.send_response(206 if range_value else 200)
        self.send_header('Content-Type', 'video/mp4' if self.path.endswith('.mp4') else 'application/octet-stream')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Accept-Ranges', 'bytes')
        if range_value:
            self.send_header('Content-Range', f'bytes {start}-{end}/{len(data)}')
        self.end_headers()
        if body:
            try:
                for offset in range(start, end + 1, 32768):
                    self.wfile.write(data[offset:min(end + 1, offset + 32768)])
                    self.wfile.flush()
                    time.sleep(.012)
            except (BrokenPipeError, ConnectionResetError):
                pass


@unittest.skipUnless(shutil.which('aria2c'), 'Install aria2c to run real engine tests')
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = Service(self.root / 'home', self.root / 'state')
        self.service.settings({'bt_select_files': False})

    def tearDown(self):
        self.service.shutdown()
        self.temp.cleanup()

    def wait(self, job_id, condition, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.service.store.get(job_id)
            if condition(job):
                return job
            if job['status'] == 'error':
                self.fail(job['error'])
            time.sleep(.1)
        self.fail(f'Timed out: {self.service.store.get(job_id)}')

    def test_http_download_hash(self):
        job_id = self.service.add(self.base + '/payload.bin')
        job = self.wait(job_id, lambda j: j['status'] == 'complete')
        result = Path(job['directory']) / 'payload.bin'
        self.assertEqual(hashlib.sha256(result.read_bytes()).digest(), hashlib.sha256(DATA).digest())
        self.assertEqual(job['total'], len(DATA))

    def test_receiver_link_downloads_through_real_engine(self):
        self.service.receiver.set_password('test')
        self.service.receiver.configure('local', 0)
        access = self.service.receiver.status()
        client = http.client.HTTPConnection('127.0.0.1', access['port'], timeout=10)
        client.request('POST', '/api/downloads', json.dumps({'source': self.base + '/sent-from-pc.bin'}),
                       {'Content-Type': 'application/json', 'Authorization': 'Basic ' + base64.b64encode(b'downloader:test').decode()})
        response = client.getresponse()
        self.assertEqual(response.status, 201)
        job_id = json.loads(response.read())['id']
        client.close()
        job = self.wait(job_id, lambda j: j['status'] == 'complete')
        self.assertEqual((Path(job['directory']) / 'sent-from-pc.bin').read_bytes(), DATA)

    def test_pause_resume_uses_http_range_and_preserves_hash(self):
        self.service.settings({'limit_kib': 1024})
        job_id = self.service.add(self.base + '/resume.bin')
        self.wait(job_id, lambda j: j['completed'] > 1024 * 1024)
        self.service.action(job_id, 'pause')
        deadline = time.monotonic() + 8
        while job_id in self.service.running and time.monotonic() < deadline:
            time.sleep(.1)
        self.assertEqual(self.service.store.get(job_id)['status'], 'paused')
        Handler.ranges.clear()
        self.service.action(job_id, 'resume')
        job = self.wait(job_id, lambda j: j['status'] == 'complete')
        self.assertTrue(any(not value.startswith('bytes=0-') for value in Handler.ranges), Handler.ranges)
        self.assertEqual((Path(job['directory']) / 'resume.bin').read_bytes(), DATA)

    def test_restart_resume(self):
        self.service.settings({'limit_kib': 1024})
        job_id = self.service.add(self.base + '/restart.bin')
        self.wait(job_id, lambda j: j['completed'] > 512 * 1024)
        self.service.shutdown()
        self.service = Service(self.root / 'home', self.root / 'state')
        self.assertEqual(self.service.store.get(job_id)['status'], 'paused')
        self.service.action(job_id, 'resume')
        job = self.wait(job_id, lambda j: j['status'] == 'complete')
        self.assertEqual((Path(job['directory']) / 'restart.bin').read_bytes(), DATA)

    def test_http_failure(self):
        job_id = self.service.add(self.base + '/missing')
        job = self.wait(job_id, lambda j: j['status'] == 'error')
        self.assertTrue(job['error'])

    def test_cancel_retains_partial_data(self):
        self.service.settings({'limit_kib': 512})
        job_id = self.service.add(self.base + '/cancel.bin')
        self.wait(job_id, lambda j: j['completed'] > 100000)
        self.service.action(job_id, 'cancel')
        self.service.shutdown()
        job = self.service.store.get(job_id)
        self.assertEqual(job['status'], 'cancelled')
        self.assertTrue((Path(job['directory']) / 'cancel.bin').exists())

    def test_torrent_and_magnet_from_local_seed(self):
        client_port = reserve_port('49152-65535')
        release_port(client_port)
        self.service.settings({'torrent_ports': str(client_port), 'bt_upnp': True, 'limit_kib': 1024})
        mapped, removed = [], []
        class SimulatedGateway:
            def add(self, port, protocol, token):
                mapped.append((port, protocol))
            def remove(self, port, protocol, token):
                removed.append((port, protocol))
        gateway = patch('downloader.upnp.discover', return_value=SimulatedGateway())
        gateway.start()
        self.addCleanup(gateway.stop)
        seed_dir = self.root / 'seed'
        seed_dir.mkdir()
        (seed_dir / 'payload.bin').write_bytes(DATA)
        piece_size = 262144
        info = {b'name': b'payload.bin', b'length': len(DATA), b'piece length': piece_size,
                b'pieces': b''.join(hashlib.sha1(DATA[i:i + piece_size]).digest() for i in range(0, len(DATA), piece_size)), b'private': 1}
        info_hash = hashlib.sha1(bencode(info)).hexdigest()
        tracker = self.base + '/announce'
        torrent = self.root / 'local.torrent'
        torrent.write_bytes(bencode({b'announce': tracker.encode(), b'info': info}))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        Handler.peers.clear()
        seed_log = self.root / 'seed.log'
        log = seed_log.open('w')
        process = subprocess.Popen(['aria2c', '--seed-time=5', '--seed-ratio=100.0', '--check-integrity=true', '--enable-dht=false',
                                    '--enable-dht6=false', '--enable-peer-exchange=false', f'--listen-port={port}',
                                    '--console-log-level=error', f'--dir={seed_dir}', str(torrent)],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 10
            while port not in Handler.peers and time.monotonic() < deadline:
                time.sleep(.1)
            self.assertIn(port, Handler.peers, 'Local seed did not register: ' + seed_log.read_text())
            job_id = self.service.add(str(torrent), kind='torrent-file')
            self.wait(job_id, lambda j: j['completed'] > 1024 * 1024 and (client_port, 'UDP') in mapped)
            self.service.settings({'bt_upnp': False})
            active = self.wait(job_id, lambda j: (client_port, 'UDP') in removed)
            self.assertEqual(active['status'], 'active', 'Disabling UPnP removes mappings while transfer continues')
            job = self.wait(job_id, lambda j: j['status'] == 'complete', timeout=60)
            self.assertEqual((Path(job['directory']) / 'payload.bin').read_bytes(), DATA)
            self.assertIn(client_port, Handler.peers, 'Tracker sees the configured incoming torrent port')
            self.assertIn((client_port, 'TCP'), mapped)
            self.assertIn((client_port, 'UDP'), mapped)
            self.assertIn((client_port, 'TCP'), removed)
            self.assertIn((client_port, 'UDP'), removed)
            self.service.settings({'bt_upnp': True, 'limit_kib': 0})
            magnet = f'magnet:?xt=urn:btih:{info_hash}&dn=LocalTest&tr={quote(tracker, safe="")}'
            job_id = self.service.add(magnet)
            job = self.wait(job_id, lambda j: j['status'] == 'complete', timeout=60)
            self.assertEqual((Path(job['directory']) / 'payload.bin').read_bytes(), DATA)
        finally:
            stop_process(process)
            log.close()

    def test_selected_torrent_files_and_seed_ratio(self):
        self.service.settings({'bt_select_files': True, 'bt_seed': True, 'bt_seed_ratio': .1, 'parallel': 1})
        seed_dir = self.root / 'seed-multi'
        folder = seed_dir / 'collection'
        folder.mkdir(parents=True)
        first, second = DATA[:2 * 1024 * 1024], b'Z' * (2 * 1024 * 1024)
        (folder / 'first.bin').write_bytes(first)
        (folder / 'second.bin').write_bytes(second)
        combined, piece = first + second, 262144
        info = {b'name': b'collection', b'files': [{b'length': len(first), b'path': [b'first.bin']},
                {b'length': len(second), b'path': [b'second.bin']}], b'piece length': piece,
                b'pieces': b''.join(hashlib.sha1(combined[i:i + piece]).digest() for i in range(0, len(combined), piece)), b'private': 1}
        info_hash = hashlib.sha1(bencode(info)).hexdigest()
        tracker = self.base + '/announce'
        torrent_data = bencode({b'announce': tracker.encode(), b'info': info})
        torrent = self.root / 'multi.torrent'
        torrent.write_bytes(torrent_data)
        seed_port = reserve_port('49152-65535'); release_port(seed_port)
        Handler.peers.clear()
        seed = subprocess.Popen(['aria2c', '--seed-ratio=100', '--check-integrity=true', '--enable-dht=false', '--enable-dht6=false',
                                 '--enable-peer-exchange=false', f'--listen-port={seed_port}', f'--dir={seed_dir}',
                                 '--console-log-level=error', str(torrent)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        leecher = None
        try:
            deadline = time.monotonic() + 10
            while seed_port not in Handler.peers and time.monotonic() < deadline:
                time.sleep(.1)
            self.assertIn(seed_port, Handler.peers)
            self.service.receiver.set_password('test')
            self.service.receiver.configure('local', 0)
            def remote(path, data=None):
                client = http.client.HTTPConnection('127.0.0.1', self.service.receiver.port, timeout=10)
                raw = isinstance(data, bytes)
                client.request('POST' if data is not None else 'GET', path,
                               data if raw else json.dumps(data) if data is not None else None,
                               {'Content-Type': 'application/x-bittorrent' if raw else 'application/json',
                                'Authorization': 'Basic ' + base64.b64encode(b'downloader:test').decode()})
                response = client.getresponse()
                result = json.loads(response.read()); client.close()
                self.assertIn(response.status, (200, 201), result)
                return result
            # The entire first transfer is submitted and selected via the LAN API.
            local = remote('/api/torrents', torrent_data)['id']
            self.wait(local, lambda j: j['status'] == 'selecting' and local not in self.service.running)
            remote_files = remote('/api/torrent-files?job_id=' + local)
            self.assertTrue(remote_files['editable'])
            self.assertEqual(len(remote_files['files']), 2)
            remote('/api/torrent-selection', {'job_id': local, 'indices': [2]})
            local_job = self.wait(local, lambda j: j['status'] == 'seeding')
            self.assertEqual((Path(local_job['directory']) / 'collection/second.bin').read_bytes(), second)
            remote('/api/torrent-pause', {'job_id': local})
            self.wait(local, lambda j: local not in self.service.running)
            self.assertEqual(remote('/api/torrent-files?job_id=' + local)['selection'], [2])
            self.service.action(local, 'cancel')
            self.wait(local, lambda j: local not in self.service.running)
            Handler.torrent = torrent_data
            remote = self.service.add(self.base + '/collection.torrent')
            self.wait(remote, lambda j: j['status'] == 'selecting' and remote not in self.service.running)
            self.assertEqual(self.service.torrent_files(remote)['infohash'], info_hash)
            self.service.action(remote, 'cancel')
            magnet = f'magnet:?xt=urn:btih:{info_hash}&dn=Collection&tr={quote(tracker, safe="")}'
            job_id = self.service.add(magnet)
            job = self.wait(job_id, lambda j: j['status'] == 'selecting' and job_id not in self.service.running, timeout=60)
            self.assertEqual(job['completed'], 0)
            details = self.service.torrent_files(job_id)
            self.assertEqual([f['name'] for f in details['files']], ['collection/first.bin', 'collection/second.bin'])
            self.assertFalse((Path(job['directory']) / 'collection/first.bin').exists())
            self.service.torrent_select(job_id, [1])
            job = self.wait(job_id, lambda j: j['status'] == 'seeding', timeout=60)
            self.assertEqual(job['total'], len(first))
            self.assertEqual((Path(job['directory']) / 'collection/first.bin').read_bytes(), first)
            excluded = Path(job['directory']) / 'collection/second.bin'
            self.assertTrue(not excluded.exists() or excluded.stat().st_size == 0)
            # Seeders do not occupy the only parallel download slot.
            http_job = self.service.add(self.base + '/alongside-seed.bin')
            self.wait(http_job, lambda j: j['status'] == 'complete')
            self.assertEqual(self.service.store.get(job_id)['status'], 'seeding')
            # Cached metadata and selection survive a loader restart.
            self.service.shutdown()
            self.service = Service(self.root / 'home', self.root / 'state')
            self.assertEqual(self.service.store.get(job_id)['status'], 'paused')
            self.assertEqual(self.service.torrent_files(job_id)['selection'], [1])
            stop_process(seed)
            self.service.action(job_id, 'resume')
            self.wait(job_id, lambda j: j['status'] == 'seeding')
            leech_dir = self.root / 'leecher'
            leech_dir.mkdir()
            leecher = subprocess.Popen(['aria2c', '--seed-time=0', '--select-file=1', '--enable-dht=false',
                                       '--enable-dht6=false', '--enable-peer-exchange=false', '--bt-stop-timeout=30',
                                       '--console-log-level=error', f'--dir={leech_dir}', str(torrent)],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            done = self.wait(job_id, lambda j: j['status'] == 'complete', timeout=70)
            self.assertGreaterEqual(done['uploaded'], len(first) * .1)
            self.assertEqual(done['upload_speed'], 0)
            self.assertEqual(self.service.torrent_files(job_id)['selection'], [1])
        finally:
            stop_process(seed)
            if leecher:
                stop_process(leecher)

    @unittest.skipUnless(shutil.which('yt-dlp') and shutil.which('ffmpeg'), 'Requires yt-dlp and FFmpeg')
    def test_video_and_audio(self):
        path = self.root / 'sample.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=green:s=160x90:r=10',
                        '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '2', '-c:v', 'mpeg4',
                        '-c:a', 'aac', str(path)], check=True, timeout=30)
        Handler.media = path.read_bytes()
        video = self.service.add(self.base + '/sample.mp4', kind='video')
        audio = self.service.add(self.base + '/sample.mp4', kind='audio')
        video_job = self.wait(video, lambda j: j['status'] == 'complete')
        audio_job = self.wait(audio, lambda j: j['status'] == 'complete')
        self.assertTrue(list(Path(video_job['directory']).glob('*.mp4')))
        self.assertTrue(list(Path(audio_job['directory']).glob('*.mp3')))


if __name__ == '__main__':
    unittest.main()
