import http.client
import base64
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from downloader.runtime import Runtime
from downloader.service import Service
from downloader.receiver import local_address, Receiver

READY = {"flatpak": False, "varia": False, "aria2": "native", "video": "native", "ffmpeg": True}


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = patch.object(Runtime, 'detect', return_value=READY)
        self.runtime.start()
        self.service = Service(self.root / 'home', self.root / 'state')
        self.service.stopping.set()
        self.service.scheduler.join(2)
        self.service.stopping.clear()
        self.receiver = self.service.receiver
        self.key = 'test'
        self.receiver.set_password(self.key)
        # Port zero is internal test allocation; settings only allow explicit ports.
        self.receiver.configure('local', 0)
        self.port = self.receiver.port

    def tearDown(self):
        self.service.shutdown()
        self.runtime.stop()
        self.temp.cleanup()

    def request(self, path='/api/downloads', data=None, key=True, headers=None, method=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        values = {'Content-Type': 'application/json'}
        if key:
            values['Authorization'] = 'Basic ' + base64.b64encode(('downloader:' + (self.key if key is True else key)).encode('utf-8')).decode()
        values.update(headers or {})
        raw = data if isinstance(data, bytes) else json.dumps(data) if data is not None else None
        connection.request(method or ('POST' if data is not None else 'GET'), path, raw, values)
        response = connection.getresponse()
        body, status, response_headers = response.read(), response.status, dict(response.getheaders())
        connection.close()
        return status, body, response_headers

    def test_receiver_defaults_off_and_key_not_in_state(self):
        self.assertEqual(self.service.store.settings()['receiver_mode'], 'off')
        self.assertNotIn(self.key, json.dumps(self.service.state()))
        status, page, headers = self.request('/', key=False)
        self.assertEqual(status, 200)
        self.assertNotIn(self.key.encode(), page)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])

    def control(self, method, args=None, **kwargs):
        return self.request('/api/control', {'method': method, 'args': args or {}}, **kwargs)

    def test_remote_actions_preserve_files_and_use_service_state_rules(self):
        job = self.service.add('https://example.org/actions.bin')
        target = Path(self.service.store.get(job)['directory']); target.mkdir()
        payload = target / 'keep.bin'; payload.write_bytes(b'keep me')
        self.assertEqual(self.control('action', {'job_id': job, 'action': 'remove'})[0], 400)
        for action in ('first', 'pause', 'resume', 'cancel', 'retry', 'pause', 'remove'):
            self.assertEqual(self.control('action', {'job_id': job, 'action': action})[0], 200, action)
        self.assertEqual(payload.read_bytes(), b'keep me')
        self.assertEqual(self.service.store.jobs(), [])
        self.assertEqual(self.control('action', {'job_id': job, 'action': 'remove'})[0], 400)

    def test_remote_queue_bulk_actions_and_full_history(self):
        jobs = [self.service.add(f'https://example.org/{i}.bin') for i in range(55)]
        snapshot = json.loads(self.request('/api/status')[1])
        self.assertEqual(len(snapshot['jobs']), 55)
        self.assertEqual(snapshot['api'], 4)
        self.assertEqual(self.control('pause_all')[0], 200)
        self.assertTrue(all(j['status'] == 'paused' for j in self.service.store.jobs()))
        self.assertEqual(self.control('resume_all')[0], 200)
        self.service.store.update(jobs[0], status='complete')
        self.service.store.update(jobs[1], status='error')
        self.service.store.update(jobs[2], status='cancelled')
        self.assertEqual(json.loads(self.control('resume_interrupted')[1])['result'], 2)
        self.assertEqual(json.loads(self.control('clear_completed')[1])['result'], 1)
        self.assertEqual(len(self.service.store.jobs()), 54)
        detail = json.loads(self.request('/api/job?job_id=' + jobs[1])[1])
        self.assertEqual(detail['source'], 'https://example.org/1.bin')
        self.assertEqual(self.request('/api/job?job_id=x&job_id=y')[0], 400)

    def test_remote_settings_validation_engine_commands_and_password_rotation(self):
        self.service.store.save_settings({'receiver_mode': 'local', 'receiver_port': self.port})
        changes = dict(parallel=3, bt_seed=True, bt_seed_ratio=2, video_auto_update=True, torrent_ports='51413-51416')
        self.assertEqual(self.control('settings', {'changes': changes})[0], 200)
        state = json.loads(self.request('/api/state')[1])
        self.assertNotIn('jobs', state)
        for key, value in changes.items(): self.assertEqual(state['settings'][key], value)
        for changes in ({'parallel': 8}, {'video_auto_update': 'true'}, {'bt_seed_ratio': 0}, {'shell': 'bad'}):
            self.assertEqual(self.control('settings', {'changes': changes})[0], 400)
        for method in ('install_runtime', 'update_video_engine'):
            with patch.object(self.service, method, return_value=True) as operation:
                self.assertEqual(self.control(method)[0], 200)
                operation.assert_called_once_with()
        self.assertEqual(self.control('receiver_password', {'password': 'next-pass'})[0], 200)
        self.assertEqual(self.request('/api/state')[0], 401)
        self.assertEqual(self.request('/api/state', key='next-pass')[0], 200)

    def test_management_auth_origin_and_explicit_command_allowlist(self):
        for path in ('/api/state', '/api/job?job_id=missing'):
            self.assertEqual(self.request(path, key=False)[0], 401)
        for method in ('pause_all', 'clear_completed', 'settings', 'receiver_password', 'install_runtime', 'update_video_engine'):
            self.assertEqual(self.control(method, key=False)[0], 401)
            self.assertEqual(self.control(method, headers={'Origin': 'https://evil.example'})[0], 403)
        for method, args in (('shutdown', {}), ('add', {}), ('action', {'job_id': [], 'action': 'remove'}), ('pause_all', {'extra': True})):
            self.assertEqual(self.control(method, args)[0], 400)
        for data in ([], {'method':'pause_all'}, {'method': [], 'args': {}}, {'method':'pause_all','args': []}):
            self.assertEqual(self.request('/api/control', data)[0], 400)

    def test_remote_receiver_stop_returns_response_and_settings_persist(self):
        self.service.store.save_settings({'receiver_mode': 'local', 'receiver_port': self.port})
        result = self.control('settings', {'changes': {'receiver_mode': 'off'}})
        self.assertEqual(result[0], 200, result[1])
        self.assertFalse(json.loads(result[1])['receiver']['running'])
        self.assertEqual(self.service.store.settings()['receiver_mode'], 'off')

    def test_device_torrent_picker_only_lists_and_imports_torrent_metadata(self):
        folder = Path(self.service.store.settings()['directory']); folder.mkdir(parents=True)
        torrent = folder / 'device.torrent'; torrent.write_bytes(self.torrent_bytes())
        (folder / 'private.txt').write_text('not a torrent')
        endpoint = '/api/device-torrents?' + urlencode({'path': str(folder)})
        self.assertEqual(self.request(endpoint, key=False)[0], 401)
        entries = json.loads(self.request(endpoint)[1])['entries']
        self.assertEqual([item['name'] for item in entries], ['device.torrent'])
        self.assertEqual(self.control('device_torrent', {'source': str(torrent), 'directory': None}, key=False)[0], 401)
        result = self.control('device_torrent', {'source': str(torrent), 'directory': None})
        self.assertEqual(result[0], 200, result[1])
        self.assertEqual(self.service.store.get(json.loads(result[1])['result'])['kind'], 'torrent-file')
        for source in (str(folder / 'private.txt'), str(folder / 'missing.torrent'), [], 'relative.torrent'):
            self.assertEqual(self.control('device_torrent', {'source': source, 'directory': None})[0], 400)

    def torrent_bytes(self):
        return b'd4:infod6:lengthi3e4:name5:a.bin12:piece lengthi4e6:pieces20:' + b'x' * 20 + b'ee'

    def test_uploaded_torrent_auth_validation_destination_and_duplicates(self):
        data = self.torrent_bytes()
        headers = {'Content-Type': 'application/x-bittorrent'}
        self.assertEqual(self.request('/api/torrents', data, key=False, headers=headers)[0], 401)
        self.assertEqual(self.request('/api/torrents', data)[0], 415)
        self.assertEqual(self.request('/api/torrents', b'<html>not a torrent</html>', headers=headers)[0], 400)
        self.assertEqual(self.request('/api/torrents', b'', headers=dict(headers, **{'Content-Length': str(20 * 1024 * 1024 + 1)}))[0], 413)
        self.assertEqual(self.service.store.jobs(), [])
        destination = self.root / 'external-drive'
        destination.mkdir()
        endpoint = '/api/torrents?' + urlencode({'directory': str(destination)})
        status, body, _ = self.request(endpoint, data, headers=headers)
        self.assertEqual(status, 201, body)
        job = self.service.store.get(json.loads(body)['id'])
        self.assertEqual(job['name'], 'a.bin')
        self.assertEqual(job['selection_mode'], 'ask')
        self.assertEqual(Path(job['source']).read_bytes(), data)
        self.assertTrue(Path(job['source']).is_relative_to(self.service.store.root / 'uploads'))
        self.assertTrue(Path(job['directory']).is_relative_to(destination))
        self.assertEqual(self.request(endpoint, data, headers=headers)[0], 400)
        self.assertEqual(len(list((self.service.store.root / 'uploads').glob('*'))), 1)
        self.assertEqual(len(self.service.store.jobs()), 1)
        Path(job['directory']).mkdir()
        payload = Path(job['directory']) / 'downloaded.bin'
        payload.write_bytes(b'keep')
        self.service.store.update(job['id'], status='complete')
        self.assertEqual(self.service.clear_completed(), 1)
        self.assertFalse(Path(job['source']).exists())
        self.assertEqual(payload.read_bytes(), b'keep')
        with patch.object(self.service, 'add', side_effect=ValueError('Queue unavailable')):
            self.assertEqual(self.request(endpoint, data, headers=headers)[0], 400)
        self.assertEqual(list((self.service.store.root / 'uploads').iterdir()), [])

    def test_upload_rejects_unsafe_metadata_and_missing_destination(self):
        headers = {'Content-Type': 'application/x-bittorrent'}
        valid = self.torrent_bytes()
        for data in (valid + b'junk', valid.replace(b'5:a.bin', b'6:../bad'),
                     valid.replace(b'i3e', b'i-3e'), valid[:-1], b'l' * 40 + b'e' * 40,
                     valid.replace(b'20:', b'19:')[:-3] + b'ee'):
            self.assertEqual(self.request('/api/torrents', data, headers=headers)[0], 400)
        for query in ({'directory': str(self.root / 'missing')}, {'filename': '../../bad'}, {'directory': ''}):
            self.assertEqual(self.request('/api/torrents?' + urlencode(query), valid, headers=headers)[0], 400)
        self.assertFalse((self.root / 'missing').exists())
        self.assertEqual(self.service.store.jobs(), [])

    def test_remote_torrent_catalogue_selection_pause_and_stale_requests(self):
        job = self.service.add('magnet:?xt=urn:btih:' + 'a' * 40)
        files = [dict(index=i, name=f'file-{i}.bin', length=1) for i in range(1, 10001)]
        self.service.store.save_torrent(job, 'a' * 40, files)
        self.service.store.update(job, status='selecting')
        endpoint = '/api/torrent-files?job_id=' + job
        self.assertEqual(self.request(endpoint, key=False)[0], 401)
        self.assertEqual(self.request('/api/torrent-selection', {'job_id': job, 'indices': [2]}, key=False)[0], 401)
        self.assertTrue(json.loads(self.request(endpoint)[1])['editable'])
        for indices in ([], [0], [1, 1], [True], ['2']):
            self.assertEqual(self.request('/api/torrent-selection', {'job_id': job, 'indices': indices})[0], 400)
        # A complete 10000-file selection exceeds the normal 32 KiB JSON limit.
        self.assertEqual(self.request('/api/torrent-selection', {'job_id': job, 'indices': list(range(1, 10001))})[0], 200)
        self.assertEqual(self.service.store.get(job)['status'], 'queued')
        self.assertFalse(json.loads(self.request(endpoint)[1])['editable'])
        self.assertEqual(self.request('/api/torrent-selection', {'job_id': job, 'indices': [2]})[0], 400)
        self.assertEqual(self.request('/api/torrent-pause', {'job_id': job})[0], 200)
        self.assertEqual(self.request('/api/torrent-selection', {'job_id': job, 'indices': [2]})[0], 200)
        self.assertEqual(json.loads(self.request(endpoint)[1])['selection'], [2])
        self.assertEqual(self.request('/api/torrent-files?job_id=missing')[0], 400)
        self.assertEqual(self.request('/api/torrent-files?job_id=x&job_id=y')[0], 400)
        self.assertEqual(self.request('/api/torrent-pause', {'job_id': job, 'action': 'remove'})[0], 400)

    def test_key_required_for_status_and_post(self):
        for key in (False, 'wrong'):
            self.assertEqual(self.request('/api/status', key=key)[0], 401)
            self.assertEqual(self.request(data={'source': 'https://example.org/a'}, key=key)[0], 401)
        self.assertEqual(self.service.store.jobs(), [])

    def test_http_and_magnet_go_to_existing_queue(self):
        for link in ('https://example.org/a.zip', 'magnet:?xt=urn:btih:' + 'a' * 40):
            status, body, _ = self.request(data={'source': link})
            self.assertEqual(status, 201, body)
            job = self.service.store.get(json.loads(body)['id'])
            self.assertEqual(job['source'], link)
            self.assertEqual(job['status'], 'queued')
            self.assertTrue(Path(job['directory']).is_relative_to(Path(self.service.store.settings()['directory'])))
        self.assertEqual(len(json.loads(self.request('/api/status')[1])['jobs']), 2)

    def test_video_and_audio_use_correct_kind_and_quality(self):
        for kind in ('video', 'audio'):
            status, body, _ = self.request(data={'source': f'https://example.org/{kind}', 'kind': kind, 'quality': '720'})
            self.assertEqual(status, 201, body)
            job = self.service.store.get(json.loads(body)['id'])
            self.assertEqual((job['kind'], job['quality']), (kind, '720'))

    def test_duplicates_are_not_acknowledged_as_new_jobs(self):
        data = {'source': 'https://example.org/file'}
        self.assertEqual(self.request(data=data)[0], 201)
        self.assertEqual(self.request(data=data)[0], 400)
        self.assertEqual(len(self.service.store.jobs()), 1)

    def test_remote_requests_cannot_read_files_or_select_engine_options(self):
        for data in ({'source': '/etc/passwd', 'kind': 'torrent-file'}, {'source': 'file:///etc/passwd'},
                     {'source': 'https://example.org/a', 'directory': str(self.root / 'missing')},
                     {'source': 'https://example.org/a', 'out': 'anything'},
                     {'source': ['https://example.org/a']}, {'source': 'https://example.org/a', 'quality': {}}, []):
            self.assertEqual(self.request(data=data)[0], 400, data)
        self.assertEqual(self.service.store.jobs(), [])

    def test_remote_folder_browser_creation_and_destination(self):
        destination = self.root / 'storage'
        destination.mkdir()
        (destination / 'private.txt').write_text('not remotely readable')
        (destination / 'existing').mkdir()
        query = '/api/folders?' + urlencode({'path': str(destination)})
        self.assertEqual(self.request(query, key=False)[0], 401)
        result = json.loads(self.request(query)[1])
        self.assertEqual([e['name'] for e in result['entries']], ['existing'])
        self.assertTrue(json.loads(self.request('/api/locations')[1])['locations'])
        status, body, _ = self.request('/api/folders', {'parent': str(destination), 'name': 'New folder ą'})
        self.assertEqual(status, 201, body)
        selected = json.loads(body)['path']
        status, body, _ = self.request(data={'source': 'https://example.org/custom.zip', 'directory': selected})
        self.assertEqual(status, 201, body)
        job = self.service.store.get(json.loads(body)['id'])
        self.assertTrue(Path(job['directory']).is_relative_to(Path(selected)))
        self.assertNotEqual(self.service.store.settings()['directory'], selected)
        for name in ('../escape', 'a/b', ''):
            self.assertEqual(self.request('/api/folders', {'parent': selected, 'name': name})[0], 400)
        self.assertEqual(self.request('/api/folders', {'parent': str(destination), 'name': 'existing'})[0], 400)
        for params in ({'path': str(destination), 'torrents': 'true'}, {'path': 'relative'},
                       {'path': str(destination / 'private.txt')}, {'path': str(destination), 'offset': '-1'}):
            self.assertEqual(self.request('/api/folders?' + urlencode(params))[0], 400)

    def test_removed_or_read_only_destination_is_not_silently_recreated(self):
        missing = self.root / 'removed-drive'
        self.assertEqual(self.request(data={'source': 'https://example.org/x', 'directory': str(missing)})[0], 400)
        self.assertFalse(missing.exists())
        with patch('downloader.folders.folder_status', return_value={'writable': False, 'free': 0}):
            self.assertEqual(self.request(data={'source': 'https://example.org/x', 'directory': str(self.root)})[0], 400)
        self.assertEqual(self.service.store.jobs(), [])

    def event_connection(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=4)
        auth = 'Basic ' + base64.b64encode(('downloader:' + self.key).encode()).decode()
        connection.request('GET', '/api/events', headers={'Authorization': auth})
        return connection, connection.getresponse()

    def test_live_events_update_progress_and_password_change_closes_session(self):
        self.assertEqual(self.request('/api/events', key=False)[0], 401)
        job_id = json.loads(self.request(data={'source': 'https://example.org/live'})[1])['id']
        connection, response = self.event_connection()
        try:
            self.assertEqual(response.status, 200)
            self.assertIn('text/event-stream', response.getheader('Content-Type'))
            first = json.loads(response.readline()[6:]); response.readline()
            self.assertEqual(first['jobs'][0]['completed'], 0)
            self.service.store.update(job_id, status='active', completed=123, total=456, speed=12)
            updated = json.loads(response.readline()[6:]); response.readline()
            self.assertEqual((updated['jobs'][0]['completed'], updated['jobs'][0]['speed']), (123, 12))
            self.receiver.set_password('new1')
            self.assertEqual(response.read(), b'')
        finally:
            connection.close()

    def test_stream_capacity_leaves_commands_available_and_stop_closes_streams(self):
        streams = [self.event_connection() for _ in range(4)]
        try:
            for _, response in streams:
                self.assertEqual(response.status, 200)
                response.readline(); response.readline()
            self.assertEqual(self.request('/api/events')[0], 503)
            self.assertEqual(self.request(data={'source': 'https://example.org/while-streaming'})[0], 201)
            self.receiver.stop()
            for _, response in streams:
                response.read()  # Must reach EOF within the socket timeout.
        finally:
            for connection, _ in streams:
                connection.close()

    def test_cross_origin_and_rebinding_refused(self):
        data = {'source': 'https://example.org/a'}
        for headers in ({'Origin': 'https://evil.example'}, {'Origin': 'null'},
                        {'Host': f'evil.example:{self.port}'}, {'Host': f'8.8.8.8:{self.port}'}):
            self.assertEqual(self.request(data=data, headers=headers)[0], 403)
        self.assertEqual(self.service.store.jobs(), [])

    def test_same_origin_web_and_firefox_origins(self):
        for origin in (f'http://127.0.0.1:{self.port}', 'moz-extension://1234-abcd'):
            status, _, headers = self.request('/api/status', headers={'Origin': origin})
            self.assertEqual(status, 200)
            if origin.startswith('moz-'):
                self.assertEqual(headers['Access-Control-Allow-Origin'], origin)
        self.assertEqual(self.request('/api/status', key=False, headers={'Origin': 'moz-extension://1234-abcd'})[0], 401)

    def test_payload_limits_and_json_content_type(self):
        self.assertEqual(self.request(data={'source': 'x' * 33000})[0], 413)
        self.assertEqual(self.request(data={'source': 'https://example.org'}, headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request(data={'source': 'https://example.org'}, headers={'Transfer-Encoding': 'chunked'})[0], 400)

    def test_unknown_routes_do_not_expose_files(self):
        for route in ('/receiver-key', '/../../etc/passwd', '/api/settings', '/api/status?token=' + self.key):
            self.assertEqual(self.request(route)[0], 404)

    def test_rotation_revokes_existing_key_without_restart(self):
        new = 'nowe-hasło'
        self.receiver.set_password(new)
        self.assertNotEqual(self.key, new)
        self.assertEqual(self.request('/api/status')[0], 401)
        self.assertEqual(self.request('/api/status', key=new)[0], 200)

    def test_key_persists_across_receiver_restart(self):
        self.receiver.stop()
        self.receiver.configure('local', self.port)
        self.assertTrue(self.receiver.status()['password_set'])
        self.assertEqual(self.request('/api/status')[0], 200)

    def test_password_is_hashed_and_never_returned(self):
        password = 'Moje:hasło ąę👍'
        result = self.receiver.set_password(password)
        self.assertNotIn(password, json.dumps(result))
        self.assertNotIn(password, json.dumps(self.service.state()))
        stored = (self.root / 'state/receiver-password.json').read_text()
        self.assertNotIn(password, stored)
        self.assertNotIn(self.key, stored)
        self.assertIn('salt', json.loads(stored))
        self.assertEqual(self.request('/api/status', key=password)[0], 200)
        self.receiver.stop()
        self.receiver.configure('local', self.port)
        self.assertEqual(self.request('/api/status', key=password)[0], 200)

    def test_password_validation_preserves_previous_password(self):
        for password in ('', 'abc', '    ', 'a' * 129, 'test\n', None, 1234):
            with self.assertRaises(ValueError):
                self.receiver.set_password(password)
        self.assertEqual(self.request('/api/status')[0], 200)

    def test_bad_password_attempts_are_limited_and_change_resets_limit(self):
        for _ in range(10):
            self.assertEqual(self.request('/api/status', key='wrong')[0], 401)
        self.assertEqual(self.request('/api/status', key='wrong')[0], 429)
        self.receiver.set_password('new1')
        self.assertEqual(self.request('/api/status', key='new1')[0], 200)

    def test_old_pairing_migrates_then_is_revoked_by_new_password(self):
        self.receiver.stop()
        (self.root / 'state/receiver-password.json').unlink()
        legacy = 'a' * 43
        (self.root / 'state/receiver-key').write_text(legacy)
        self.receiver = self.service.receiver = Receiver(self.service)
        self.receiver.configure('local', self.port)
        headers = {'Authorization': 'Bearer ' + legacy}
        self.assertEqual(self.request('/api/status', key=False, headers=headers)[0], 200)
        self.assertFalse((self.root / 'state/receiver-key').exists())
        self.assertNotIn(legacy, (self.root / 'state/receiver-password.json').read_text())
        self.receiver.set_password('1234')
        self.assertEqual(self.request('/api/status', key=False, headers=headers)[0], 401)
        self.assertEqual(self.request('/api/status', key='1234')[0], 200)

    def test_new_install_requires_a_password_before_listening(self):
        service = Service(self.root / 'new-home', self.root / 'new-state')
        try:
            self.assertFalse(service.receiver.status()['password_set'])
            with self.assertRaisesRegex(ValueError, 'Set a receiver password'):
                service.receiver.configure('local', 0)
            self.assertFalse(service.receiver.status()['running'])
        finally:
            service.shutdown()

    def test_settings_enable_disable_and_reject_bad_values(self):
        self.service.settings({'receiver_mode': 'local', 'receiver_port': self.port})
        self.assertTrue(self.service.state()['receiver']['running'])
        self.service.settings({'receiver_mode': 'off'})
        self.assertFalse(self.service.state()['receiver']['running'])
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', self.port), timeout=.2)
        for changes in ({'receiver_mode': 'internet'}, {'receiver_port': 80}, {'receiver_port': True}, {'receiver_port': 65536}):
            with self.assertRaises(ValueError):
                self.service.settings(changes)

    def test_bind_failure_restores_previous_receiver_and_settings(self):
        self.service.settings({'receiver_mode': 'local', 'receiver_port': self.port})
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            with self.assertRaises(ValueError):
                self.service.settings({'receiver_port': occupied.getsockname()[1]})
        self.assertEqual(self.service.store.settings()['receiver_port'], self.port)
        self.assertEqual(self.request('/api/status')[0], 200)

    def test_shutdown_closes_listener(self):
        self.service.shutdown()
        self.assertFalse(self.receiver.status()['running'])
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', self.port), timeout=.2)

    def test_client_network_boundary(self):
        for address in ('192.168.1.50', '10.1.2.3', '172.16.1.1', '127.0.0.1'):
            self.assertTrue(local_address(address))
        for address in ('8.8.8.8', '172.32.0.1', '::1', '0.0.0.0', 'evil.example', '169.254.169.254'):
            self.assertFalse(local_address(address))


if __name__ == '__main__':
    unittest.main()
