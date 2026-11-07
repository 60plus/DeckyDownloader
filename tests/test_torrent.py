import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from downloader.engines import SelectFiles, Stopped
from downloader.service import Service
from downloader.store import Store
from downloader.runtime import Runtime
from downloader.torrent import catalogue, selected_progress


class TorrentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.detect = patch.object(Runtime, 'detect', return_value={'aria2': 'native', 'video': 'native', 'ffmpeg': True})
        self.detect.start()
        self.service = Service(self.root / 'home', self.root / 'state')
        self.service.stopping.set(); self.service.scheduler.join(2); self.service.stopping.clear()

    def tearDown(self):
        self.service.shutdown(); self.detect.stop(); self.temp.cleanup()

    def job(self, suffix='a'):
        job = self.service.add('magnet:?xt=urn:btih:' + suffix * 40)
        self.service.store.save_torrent(job, suffix * 40, [dict(index=1, name='a.bin', length=100), dict(index=2, name='b.bin', length=200)])
        self.service.store.update(job, status='selecting')
        return job

    def test_selection_validation_and_persistence(self):
        job = self.job()
        for indices in ([], [0], [3], [True], [1, 1], '1', None):
            with self.subTest(indices=indices), self.assertRaises(ValueError):
                self.service.torrent_select(job, indices)
        self.assertEqual(self.service.store.get(job)['status'], 'selecting')
        self.service.torrent_select(job, [2])
        self.assertEqual(self.service.store.get(job)['status'], 'queued')
        fresh = Store(self.root / 'state', self.root / 'home')
        self.assertEqual(fresh.torrent(job)['selection'], [2])
        with self.assertRaises(ValueError):
            self.service.torrent_select(job, [1])
        self.service.action(job, 'pause')
        self.service.torrent_select(job, [1, 2])
        self.assertEqual(fresh.torrent(job)['selection'], [1, 2])

    def test_metadata_change_does_not_reuse_indices(self):
        job = self.job()
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.service.store.save_torrent(job, 'b' * 40, [dict(index=1, name='evil', length=100)])
        self.assertEqual(self.service.torrent_files(job)['infohash'], 'a' * 40)

    def test_pause_resume_pending_selection_does_not_download_all(self):
        job = self.job()
        self.service.action(job, 'pause'); self.service.action(job, 'resume')
        self.assertEqual(self.service.store.get(job)['status'], 'selecting')
        self.service.action(job, 'cancel'); self.service.resume_interrupted()
        self.assertEqual(self.service.store.get(job)['status'], 'selecting')

    def test_seed_settings_and_recovery(self):
        self.assertFalse(self.service.store.settings()['bt_seed'])
        for value in (0, -.1, 101, True, float('nan'), float('inf'), '2'):
            with self.assertRaises(ValueError): self.service.settings({'bt_seed_ratio': value})
        for key in ('bt_seed', 'bt_select_files'):
            with self.assertRaises(ValueError): self.service.settings({key: 1})
        self.service.settings({'bt_seed': True, 'bt_seed_ratio': 2.5})
        job = self.job()
        self.service.torrent_select(job, [1])
        self.service.store.update(job, status='seeding', uploaded=70, upload_speed=12)
        self.service.store.recover()
        recovered = self.service.store.get(job)
        self.assertEqual((recovered['status'], recovered['uploaded'], recovered['upload_speed']), ('paused', 70, 0))
        self.assertEqual(self.service.clear_completed(), 0)
        self.assertEqual(self.service.store.settings()['bt_seed_ratio'], 2.5)

    def test_catalogue_rejects_escaping_paths_and_counts_selected_bytes(self):
        valid = dict(infoHash='a'*40, files=[dict(index='1', path=str(self.root/'a.bin'), length='100', completedLength='100', selected='true'),
                                          dict(index='2', path=str(self.root/'b.bin'), length='200', completedLength='50', selected='false')])
        self.assertEqual(selected_progress(valid), (100, 100))
        self.assertEqual(catalogue(valid, self.root)[1][0]['name'], 'a.bin')
        valid['files'][0]['path'] = str(self.root.parent/'escape')
        with self.assertRaises(ValueError): catalogue(valid, self.root)

    def test_explicit_cancel_wins_over_metadata_and_seed_completion(self):
        for outcome in ('select', 'seed'):
            job = self.job('a' if outcome == 'select' else 'b')
            self.service.store.update(job, status='active')
            def run():
                self.service.action(job, 'cancel')
                if outcome == 'select': raise SelectFiles()
            with patch('downloader.service.Transfer') as transfer:
                transfer.return_value.run.side_effect = run
                self.service._run(self.service.store.get(job), self.service.store.settings(), threading.Event())
            self.assertEqual(self.service.store.get(job)['status'], 'cancelled')

    def test_seeding_yields_single_port_to_queued_download(self):
        self.service.settings({'parallel': 1, 'torrent_ports': '51413', 'bt_seed': True})
        seed = self.job()
        self.service.store.update(seed, status='seeding')
        stop = threading.Event()
        self.service.running[seed] = (stop, None)
        queued = self.service.add('https://example.org/later')
        self.service.scheduler = threading.Thread(target=self.service._schedule, daemon=True)
        self.service.scheduler.start()
        try:
            self.assertTrue(stop.wait(2))
            self.assertEqual(self.service.store.get(seed)['status'], 'seed_waiting')
            self.assertEqual(self.service.store.get(queued)['status'], 'queued')
        finally:
            self.service.stopping.set(); self.service.scheduler.join(2)
            self.service.running.pop(seed, None)

    def test_migration_keeps_existing_downloads_on_all_files(self):
        job = self.job()
        # Simulate the pre-feature schema by dropping new fields and metadata.
        with self.service.store.connect() as db:
            db.execute('DROP TABLE torrent_details')
            for field in ('selection_mode', 'file_count', 'uploaded', 'upload_speed', 'ratio_limit'):
                db.execute('ALTER TABLE jobs DROP COLUMN ' + field)
        migrated = Store(self.root/'state', self.root/'home')
        self.assertEqual(migrated.get(job)['selection_mode'], 'all')
        self.assertEqual(migrated.get(job)['uploaded'], 0)


if __name__ == '__main__': unittest.main()
