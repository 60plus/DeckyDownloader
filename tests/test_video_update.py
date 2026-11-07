import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from downloader.runtime import Runtime, APP_ID
from downloader.video_update import install, ReleaseRedirect, next_check, save_check, CHECK_INTERVAL


class VideoUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = Runtime(self.root, self.root)
        self.stop = threading.Event()
        self.payload = b'official executable fixture'
        self.digest = hashlib.sha256(self.payload).hexdigest()
        self.version = '2026.10.26'
        self.probes = []
        self.downloads = []
        self.patches = [patch('downloader.video_update.platform.system', return_value='Linux'),
                        patch('downloader.video_update.platform.machine', return_value='x86_64'),
                        patch.object(self.runtime, 'detect', return_value={'varia': False}),
                        patch('downloader.video_update.download', side_effect=self.download)]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def download(self, url, limit, stop, destination=None):
        self.downloads.append(url)
        if url.endswith('/latest'): return json.dumps({'tag_name': self.version}).encode()
        if url.endswith('SHA2-256SUMS'): return f'{self.digest}  yt-dlp_linux\n'.encode()
        destination.write(self.payload)
        return b''

    def probe(self, command, version):
        self.probes.append((command, version))

    def run_install(self):
        return install(self.root, self.runtime, self.stop, self.probe)

    def test_verified_install_is_persistent_and_reused(self):
        self.assertEqual(self.run_install(), self.version)
        version, binary = self.runtime.video_override()
        self.assertEqual(version, self.version)
        self.assertEqual(binary.read_bytes(), self.payload)
        self.assertEqual(self.runtime.command('yt-dlp', []), [str(binary)])
        self.assertEqual(self.probes, [([str(binary)], self.version)])
        self.run_install()
        self.assertEqual(sum(url.endswith('/yt-dlp_linux') for url in self.downloads), 1)
        self.assertFalse(list((self.root / 'video-engine').rglob('*.part')))

    def test_hash_failure_preserves_previous_selection(self):
        self.run_install()
        before = (self.root / 'video-engine/current.json').read_bytes()
        self.version = '2026.11.01'; self.payload = b'corrupt download'
        with self.assertRaisesRegex(ValueError, 'checksum verification failed'): self.run_install()
        self.assertEqual((self.root / 'video-engine/current.json').read_bytes(), before)
        self.assertEqual(self.runtime.video_override()[0], '2026.10.26')
        self.assertFalse(list((self.root / 'video-engine').rglob('*.part')))

    def test_failed_probe_does_not_activate_new_engine(self):
        def broken(*args): raise RuntimeError('Engine did not start')
        with self.assertRaisesRegex(RuntimeError, 'did not start'):
            install(self.root, self.runtime, self.stop, broken)
        self.assertIsNone(self.runtime.video_override())

    def test_cancellation_does_not_activate(self):
        self.stop.set()
        with self.assertRaisesRegex(RuntimeError, 'stopped'): self.run_install()
        self.assertIsNone(self.runtime.video_override())

    def test_release_tag_cannot_escape_cache(self):
        for version in ('../../escape', 'nightly', '2026.10.26/evil'):
            self.version = version
            with self.assertRaisesRegex(ValueError, 'Unexpected'): self.run_install()
        self.assertFalse((self.root / 'video-engine').exists())

    def test_flatpak_keeps_ffmpeg_environment_and_grants_engine_access(self):
        self.run_install()
        binary = self.runtime.video_override()[1]
        with patch.object(self.runtime, 'detect', return_value={'varia': True}), patch('downloader.runtime.shutil.which', return_value='/usr/bin/flatpak'):
            command = self.runtime.command('yt-dlp', [self.root / 'downloads'])
        self.assertEqual(command[:2], ['/usr/bin/flatpak', 'run'])
        self.assertIn('--filesystem=' + str(binary.parent.resolve()), command)
        self.assertEqual(command[-2:], ['--command=' + str(binary), APP_ID])

    def test_manifest_path_injection_is_ignored(self):
        folder = self.root / 'video-engine'; folder.mkdir()
        (folder / 'current.json').write_text(json.dumps({'version': '../../evil'}))
        self.assertIsNone(self.runtime.video_override())

    def test_redirect_rejects_downgrade_and_unexpected_host(self):
        for url in ('http://github.com/file', 'https://example.org/file', 'https://user:pass@github.com/file'):
            with self.assertRaisesRegex(ValueError, 'redirect'):
                ReleaseRedirect().redirect_request(None, None, 302, '', {}, url)

    def test_automatic_check_skips_equal_or_newer_installed_versions(self):
        for current in ('2026.10.26', '2026.10.26.1', '2026.11.01'):
            self.downloads.clear()
            with patch.object(self.runtime, 'detect', return_value={'video_version': current}):
                self.assertEqual(install(self.root, self.runtime, self.stop, self.probe, only_newer=True), current)
            self.assertEqual(len(self.downloads), 1)
            self.assertTrue(self.downloads[0].endswith('/latest'))
        self.assertFalse((self.root / 'video-engine').exists())

    def test_automatic_check_installs_a_newer_release(self):
        with patch.object(self.runtime, 'detect', return_value={'varia': False, 'video_version': '2026.07.04'}):
            self.assertEqual(install(self.root, self.runtime, self.stop, self.probe, only_newer=True), self.version)
        self.assertEqual(self.runtime.video_override()[0], self.version)

    def test_schedule_survives_reload_and_handles_invalid_clock_data(self):
        save_check(self.root, 1500)
        self.assertEqual(next_check(self.root, 1000), 1500)
        save_check(self.root, 1000 + CHECK_INTERVAL * 5)
        self.assertEqual(next_check(self.root, 1000), 1000 + CHECK_INTERVAL)
        for invalid in ('bad', True, -1, float('inf')):
            (self.root / 'video-engine/auto-check.json').write_text(json.dumps({'next_check': invalid}))
            self.assertEqual(next_check(self.root, 1000), 0)


if __name__ == '__main__': unittest.main()
