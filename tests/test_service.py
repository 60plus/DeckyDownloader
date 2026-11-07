import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from downloader.engines import Stopped
from downloader.runtime import Runtime
from downloader.service import Service, validate_directory, validate_source
from downloader.store import Store

READY = {"flatpak": True, "varia": True, "aria2": "varia", "video": "varia", "ffmpeg": True}


class ValidationTests(unittest.TestCase):
    def test_http_and_magnet(self):
        self.assertEqual(validate_source(' https://example.org/a?token=one ', 'file'), 'https://example.org/a?token=one')
        self.assertTrue(validate_source('magnet:?xt=urn:btih:' + 'a' * 40, 'file').startswith('magnet:'))

    def test_rejects_unsafe_or_invalid_sources(self):
        for source in ('file:///etc/passwd', '--help', 'javascript:foo', 'https://', 'http://x:bad',
                       'https://x\n--out=file', 'magnet:?dn=nohash', ''):
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate_source(source, 'file')

    def test_video_rejects_magnet(self):
        with self.assertRaises(ValueError):
            validate_source('magnet:?xt=urn:btih:' + 'a' * 40, 'video')

    def test_local_torrent_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'sample.torrent'
            path.write_bytes(b'd4:infodee')
            self.assertEqual(validate_source(str(path), 'torrent-file'), str(path.resolve()))
            with self.assertRaises(ValueError):
                validate_source(str(path.with_suffix('.txt')), 'torrent-file')

    def test_directory_requires_absolute(self):
        for value in ('relative/path', '', '\x00'):
            with self.assertRaises(ValueError):
                validate_directory(value)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = patch.object(Runtime, 'detect', return_value=dict(READY))
        self.runtime.start()
        self.service = Service(self.root / 'home', self.root / 'state')
        # Keep queue tests deterministic; individual lifecycle tests run it again.
        self.service.stopping.set()
        self.service.scheduler.join(2)
        self.service.stopping.clear()

    def tearDown(self):
        self.service.shutdown()
        self.runtime.stop()
        self.temp.cleanup()

    def add(self, source='https://example.org/test.bin', **kwargs):
        return self.service.add(source, **kwargs)

    def test_video_auto_update_is_opt_in_and_boolean(self):
        self.assertFalse(self.service.store.settings()['video_auto_update'])
        for invalid in (1, 'true', None):
            with self.assertRaises(ValueError): self.service.settings({'video_auto_update': invalid})
        with patch('downloader.service.video_update.install') as install:
            self.service._maybe_update_video(self.service.store.settings())
            install.assert_not_called()

    def test_daily_video_check_is_persisted_and_manual_update_can_override(self):
        from downloader.video_update import next_check, CHECK_INTERVAL
        with patch('downloader.service.time.time', return_value=1000), patch('downloader.service.video_update.install', return_value='2026.10.26') as install:
            self.service.settings({'video_auto_update': True})
            self.service._maybe_update_video(self.service.store.settings())
            self.service.video_install_thread.join(2)
            self.assertEqual(install.call_count, 1)
            self.assertTrue(install.call_args.kwargs['only_newer'])
            self.assertEqual(self.service.video_install['status'], 'complete')
            self.assertTrue(self.service.video_install['automatic'])
            self.assertEqual(next_check(self.service.store.root, 1000), 1000 + CHECK_INTERVAL)
            # A fresh process reads the same deadline and does not repeat startup checks.
            restarted = Service(self.root / 'home', self.root / 'state')
            try:
                self.assertEqual(restarted.video_check_due, self.service.video_check_due)
                restarted._maybe_update_video(restarted.store.settings())
                self.assertEqual(install.call_count, 1)
            finally: restarted.shutdown()
            self.service._maybe_update_video(self.service.store.settings())
            self.assertEqual(install.call_count, 1)
            self.service.update_video_engine()
            self.service.video_install_thread.join(2)
            self.assertEqual(install.call_count, 2)
            self.assertFalse(install.call_args.kwargs['only_newer'])

    def test_failed_video_check_retries_after_hour_and_disable_stops_future_checks(self):
        from downloader.video_update import next_check, RETRY_INTERVAL
        with patch('downloader.service.time.time', return_value=1000), patch('downloader.service.video_update.install', side_effect=OSError('offline')) as install:
            self.service.settings({'video_auto_update': True})
            self.service._maybe_update_video(self.service.store.settings())
            self.service.video_install_thread.join(2)
            self.assertEqual(self.service.video_install['status'], 'error')
            self.assertEqual(next_check(self.service.store.root, 1000), 1000 + RETRY_INTERVAL)
            self.service._maybe_update_video(self.service.store.settings())
            self.assertEqual(install.call_count, 1)
            with patch('downloader.service.time.time', return_value=1000 + RETRY_INTERVAL):
                self.service._maybe_update_video(self.service.store.settings())
                self.service.video_install_thread.join(2)
                self.assertEqual(install.call_count, 2)
                self.service.settings({'video_auto_update': False})
                self.service.video_check_due = 0
                self.service._maybe_update_video(self.service.store.settings())
                self.assertEqual(install.call_count, 2)

    def test_video_auto_check_waits_for_other_installs_and_shutdown(self):
        self.service.settings({'video_auto_update': True})
        with patch('downloader.service.video_update.install') as install:
            self.service.install['status'] = 'running'
            self.service._maybe_update_video(self.service.store.settings())
            self.service.install['status'] = 'idle'
            self.service.video_install['status'] = 'running'
            self.service._maybe_update_video(self.service.store.settings())
            self.service.video_install['status'] = 'idle'
            with patch.object(self.service.runtime, 'detect', return_value={'flatpak': True, 'varia': False}):
                self.service._maybe_update_video(self.service.store.settings())
            self.service.stopping.set()
            self.service._maybe_update_video(self.service.store.settings())
            install.assert_not_called()

    def test_queue_scheduler_runs_enabled_video_check_in_background(self):
        checked = threading.Event()
        def update(*args, **kwargs):
            checked.set()
            return '2026.10.26'
        with patch('downloader.service.video_update.install', side_effect=update) as install:
            self.service.settings({'video_auto_update': True})
            self.service.scheduler = threading.Thread(target=self.service._schedule, daemon=True)
            self.service.scheduler.start()
            self.assertTrue(checked.wait(3), 'Background scheduler did not start the update')
            self.service.video_install_thread.join(2)
            self.assertEqual(install.call_count, 1)

    def test_add_has_isolated_destination(self):
        first = self.add()
        second = self.add('https://another.example/test.bin')
        a, b = self.service.store.get(first), self.service.store.get(second)
        self.assertNotEqual(a['directory'], b['directory'])
        self.assertTrue(Path(a['directory']).is_relative_to(self.root / 'home'))

    def test_duplicate_rejected(self):
        self.add()
        with self.assertRaisesRegex(ValueError, 'already'):
            self.add()

    def test_missing_engine_rejected(self):
        with patch.object(self.service.runtime, 'detect', return_value=dict(READY, aria2='missing')):
            with self.assertRaisesRegex(ValueError, 'Install Varia'):
                self.add()

    def test_audio_requires_ffmpeg(self):
        with patch.object(self.service.runtime, 'detect', return_value=dict(READY, ffmpeg=False)):
            with self.assertRaisesRegex(ValueError, 'FFmpeg'):
                self.add(kind='audio')

    def test_pause_resume_cancel_remove_preserves_files(self):
        job_id = self.add()
        path = Path(self.service.store.get(job_id)['directory'])
        path.mkdir(parents=True)
        (path / 'partial').write_bytes(b'keep me')
        self.service.action(job_id, 'pause')
        self.assertEqual(self.service.store.get(job_id)['status'], 'paused')
        self.service.action(job_id, 'resume')
        self.assertEqual(self.service.store.get(job_id)['status'], 'queued')
        self.service.action(job_id, 'cancel')
        self.service.action(job_id, 'remove')
        self.assertEqual((path / 'partial').read_bytes(), b'keep me')

    def test_cannot_remove_queued(self):
        with self.assertRaises(ValueError):
            self.service.action(self.add(), 'remove')

    def test_clear_completed_keeps_files_and_every_other_status(self):
        ids = {}
        for status in ('complete', 'paused', 'error', 'cancelled', 'queued', 'active'):
            job_id = ids[status] = self.add('https://example.org/' + status)
            self.service.store.update(job_id, status=status)
            directory = Path(self.service.store.get(job_id)['directory'])
            directory.mkdir()
            (directory / 'keep.bin').write_bytes(status.encode())
        finished_path = Path(self.service.store.get(ids['complete'])['directory'])
        self.assertEqual(self.service.clear_completed(), 1)
        self.assertEqual({job['status'] for job in self.service.store.jobs()}, {'paused', 'error', 'cancelled', 'queued', 'active'})
        self.assertEqual((finished_path / 'keep.bin').read_bytes(), b'complete')
        self.assertEqual(self.service.clear_completed(), 0)

    def test_clear_completed_skips_worker_still_cleaning_up(self):
        job_id = self.add()
        self.service.store.update(job_id, status='complete')
        self.service.running[job_id] = (threading.Event(), None)
        try:
            self.assertEqual(self.service.clear_completed(), 0)
            self.assertEqual(self.service.store.get(job_id)['status'], 'complete')
        finally:
            self.service.running.pop(job_id)
        self.assertEqual(self.service.clear_completed(), 1)

    def test_resume_interrupted_preserves_destination_and_progress(self):
        originals = {}
        for status in ('paused', 'error', 'cancelled', 'complete', 'active', 'queued'):
            job_id = self.add('https://example.org/' + status)
            self.service.store.update(job_id, status=status, completed=123, total=456, error='interrupted')
            originals[job_id] = self.service.store.get(job_id)
        self.assertEqual(self.service.resume_interrupted(), 3)
        for job_id, old in originals.items():
            current = self.service.store.get(job_id)
            self.assertEqual(current['directory'], old['directory'])
            self.assertEqual(current['completed'], 123)
            self.assertEqual(current['status'], 'queued' if old['status'] in ('paused', 'error', 'cancelled') else old['status'])
        self.assertEqual(self.service.resume_interrupted(), 0)

    def test_resume_interrupted_waits_for_stopping_worker(self):
        job_id = self.add()
        self.service.store.update(job_id, status='paused')
        self.service.running[job_id] = (threading.Event(), None)
        try:
            self.assertEqual(self.service.resume_interrupted(), 0)
            self.assertEqual(self.service.store.get(job_id)['status'], 'paused')
        finally:
            self.service.running.pop(job_id)

    def test_cancel_wins_over_late_completion(self):
        job_id = self.add()
        self.service.store.update(job_id, status='active')
        with patch('downloader.service.Transfer') as engine:
            engine.return_value.run.side_effect = lambda: self.service.action(job_id, 'cancel')
            self.service._run(self.service.store.get(job_id), self.service.store.settings(), threading.Event())
        self.assertEqual(self.service.store.get(job_id)['status'], 'cancelled')

    def test_worker_exception_is_visible(self):
        job_id = self.add()
        self.service.store.update(job_id, status='active')
        with patch('downloader.service.Transfer') as engine:
            engine.return_value.run.side_effect = OSError('Disk full')
            self.service._run(self.service.store.get(job_id), self.service.store.settings(), threading.Event())
        job = self.service.store.get(job_id)
        self.assertEqual((job['status'], job['error']), ('error', 'Disk full'))

    def test_queue_order(self):
        self.add()
        second = self.add('https://example.org/second')
        self.service.action(second, 'first')
        self.assertEqual(self.service.store.jobs()[0]['id'], second)

    def test_pause_all_resume_all_excludes_cancelled(self):
        first, second = self.add(), self.add('https://example.org/second')
        self.service.action(second, 'cancel')
        self.service.pause_all()
        self.service.resume_all()
        self.assertEqual(self.service.store.get(first)['status'], 'queued')
        self.assertEqual(self.service.store.get(second)['status'], 'cancelled')

    def test_restart_recovers_without_auto_download(self):
        first, second = self.add(), self.add('https://example.org/second')
        self.service.store.update(first, status='active', completed=1000, total=2000)
        Store(self.root / 'state', self.root / 'home').recover()
        self.assertEqual(self.service.store.get(first)['completed'], 1000)
        self.assertEqual(self.service.store.get(first)['status'], 'paused')
        self.assertEqual(self.service.store.get(second)['status'], 'paused')

    def test_settings_validation(self):
        for changes in ({'parallel': 0}, {'parallel': True}, {'limit_kib': -1}, {'display': 'foo'}, {'language': 'xx'}, {'shell': 'id'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.service.settings(changes)

    def test_settings_persist(self):
        self.service.settings({'parallel': 4, 'language': 'pl', 'torrent_ports': '51413-51416', 'bt_upnp': True, 'upload_limit_kib': 128})
        fresh = Store(self.root / 'state', self.root / 'home')
        self.assertEqual(fresh.settings()['parallel'], 4)
        self.assertEqual(fresh.settings()['language'], 'pl')
        self.assertEqual(fresh.settings()['torrent_ports'], '51413-51416')
        self.assertTrue(fresh.settings()['bt_upnp'])
        self.assertEqual(fresh.settings()['upload_limit_kib'], 128)

    def test_network_settings_default_and_validation(self):
        self.assertFalse(self.service.store.settings()['bt_upnp'])
        for changes in ({'torrent_ports': '80'}, {'torrent_ports': '65536'}, {'bt_upnp': 'false'},
                        {'bt_dht': 1}, {'bt_pex': None}, {'bt_lpd': 'true'}, {'bt_encryption': 0},
                        {'upload_limit_kib': -1}, {'upload_limit_kib': True}, {'bt_max_peers': 10001}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.service.settings(changes)

    def test_single_port_serializes_aria_but_not_video(self):
        started = []
        def transfer(job, store, runtime, settings, stop):
            class Fake:
                def run(self):
                    started.append(job['id'])
                    stop.wait(5)
                    raise Stopped()
            return Fake()
        self.service.settings({'parallel': 4, 'torrent_ports': '51413'})
        first, second = self.add(), self.add('https://example.org/second')
        video = self.add('https://example.org/video', kind='video')
        with patch('downloader.service.Transfer', side_effect=transfer):
            self.service.scheduler = threading.Thread(target=self.service._schedule, daemon=True)
            self.service.scheduler.start()
            time.sleep(.7)
            self.assertEqual(started, [first, video])
            self.service.action(first, 'pause')
            time.sleep(.7)
            self.assertEqual(started, [first, video, second])
            self.service.shutdown()

    def test_first_start_installs_varia_even_when_native_engines_exist(self):
        with patch.object(self.service.runtime, 'detect', return_value=dict(READY, varia=False, aria2='native', video='native')):
            with patch.object(self.service, 'install_runtime') as install:
                self.service.ensure_runtime()
                install.assert_called_once()

    def test_existing_varia_not_reinstalled(self):
        with patch.object(self.service, 'install_runtime') as install:
            self.service.ensure_runtime()
            install.assert_not_called()

    def test_missing_flatpak_is_actionable(self):
        with patch.object(self.service.runtime, 'detect', return_value=dict(READY, flatpak=False, varia=False)):
            self.service.ensure_runtime()
        self.assertEqual(self.service.install['status'], 'error')

    def test_scheduler_respects_parallel_limit_and_shutdown(self):
        started = []

        def transfer(job, store, runtime, settings, stop):
            class Fake:
                def run(self):
                    started.append(job['id'])
                    stop.wait(5)
                    raise Stopped()
            return Fake()

        self.service.settings({'parallel': 1})
        first, second = self.add(), self.add('https://example.org/second')
        with patch('downloader.service.Transfer', side_effect=transfer):
            self.service.scheduler = threading.Thread(target=self.service._schedule, daemon=True)
            self.service.scheduler.start()
            time.sleep(.7)
            self.assertEqual(started, [first])
            self.service.action(first, 'pause')
            time.sleep(.7)
            self.assertEqual(started, [first, second])
            self.service.shutdown()
            self.assertEqual(self.service.running, {})
            self.assertEqual(self.service.store.get(second)['status'], 'paused')


if __name__ == '__main__':
    unittest.main()
