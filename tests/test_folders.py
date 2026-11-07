import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from downloader.folders import browse, create_folder, folder_status, locations, mounted_paths


class FolderTests(unittest.TestCase):
    def test_mountinfo_unescapes_deduplicates_and_filters_system_mounts(self):
        text = r'''24 1 8:1 / / rw - ext4 /dev/sda1 rw
25 1 8:2 / /home rw - ext4 /dev/sda2 rw
26 1 8:3 / /run/media/deck/My\040SD rw - exfat /dev/mmcblk0p1 rw
27 1 8:4 / /mnt/USB\134backup rw - ext4 /dev/sdb1 rw
28 1 0:1 / /proc rw - proc proc rw
29 1 8:5 / /boot rw - vfat /dev/sda5 rw
30 1 0:2 / /mnt/NAS rw - cifs //nas/downloads rw
31 1 8:2 / /home rw - ext4 /dev/sda2 rw
malformed
32 1 1:2 / /bad rw -'''
        self.assertEqual(mounted_paths(text), ['/', '/home', '/mnt/NAS', '/mnt/USB\\backup', '/run/media/deck/My SD'])

    def test_browse_is_read_only_sorts_and_paginates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for n in range(205):
                (root / f'Folder {n:03}').mkdir()
            (root / '.hidden').mkdir()
            (root / 'not-a-folder').write_text('test')
            first = browse(temp)
            self.assertEqual(len(first['entries']), 200)
            self.assertEqual(first['entries'][0]['name'], '.hidden')
            second = browse(temp, first['next'])
            self.assertEqual(len(second['entries']), 6)
            self.assertIsNone(second['next'])
            self.assertEqual(first['path'], str(root.resolve()))
            self.assertEqual(first['parent'], str(root.parent.resolve()))
            missing = root / 'missing' / 'child'
            self.assertEqual(browse(str(missing), fallback=True)['path'], str(root.resolve()))
            self.assertFalse(missing.parent.exists())
            with self.assertRaises(FileNotFoundError):
                browse(str(missing))

    def test_invalid_requests(self):
        for path in ('', 'relative', '/bad\x00path'):
            with self.assertRaises(ValueError):
                browse(path)
        for offset in (-1, True, '0'):
            with self.assertRaises(ValueError):
                browse(str(Path.cwd()), offset)

    def test_torrent_mode_lists_only_directories_and_torrents(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'Z directory').mkdir()
            (root / 'A.TORRENT').write_bytes(b'de')
            (root / 'other.txt').write_text('test')
            self.assertEqual([e['name'] for e in browse(temp)['entries']], ['Z directory'])
            entries = browse(temp, torrents=True)['entries']
            self.assertEqual([e['name'] for e in entries], ['Z directory', 'A.TORRENT'])
            self.assertTrue(entries[0]['directory'])
            self.assertFalse(entries[1]['directory'])

    def test_locations_include_media_and_deduplicate_home(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home, media = root / 'home', root / 'My SD'
            (home / 'Downloads').mkdir(parents=True)
            media.mkdir()
            with patch('downloader.folders.mounted_paths', return_value=[str(home), str(media), str(root / 'missing')]):
                result = locations(home)
            paths = [place['path'] for place in result]
            self.assertEqual(paths.count(str(home.resolve())), 1)
            self.assertIn(str(media.resolve()), paths)
            self.assertEqual(next(p for p in result if p['path'] == str(media.resolve()))['kind'], 'drive')

    def test_permission_and_read_only_status(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('downloader.folders.os.access', return_value=False):
                self.assertFalse(folder_status(temp)['writable'])
            if hasattr(os, 'statvfs'):
                with patch('downloader.folders.os.statvfs') as stat:
                    stat.return_value.f_flag = os.ST_RDONLY
                    self.assertFalse(folder_status(temp)['writable'])

    def test_browse_error_is_not_an_empty_success(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('downloader.folders.os.scandir', side_effect=PermissionError('denied')):
                with self.assertRaises(PermissionError):
                    browse(temp)

    def test_create_folder_and_reject_existing_or_escaping_names(self):
        with tempfile.TemporaryDirectory() as temp:
            result = create_folder(temp, 'New folder żółć')
            self.assertTrue(Path(result['path']).is_dir())
            self.assertEqual(Path(result['path']).parent, Path(temp).resolve())
            for name in ('New folder żółć', 'file'):
                if name == 'file':
                    (Path(temp) / name).write_text('keep')
                with self.assertRaises(FileExistsError):
                    create_folder(temp, name)
            for name in ('', ' ', '.', '..', '../escape', '/absolute', 'a/b', 'a\\b', 'a:b', 'a\n', 'a\x7f'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    create_folder(temp, name)
            self.assertEqual((Path(temp) / 'file').read_text(), 'keep')
            with patch('downloader.folders.folder_status', return_value={'writable': False}):
                with self.assertRaisesRegex(ValueError, 'not writable'):
                    create_folder(temp, 'forbidden')
            with self.assertRaises(FileNotFoundError):
                create_folder(str(Path(temp) / 'missing'), 'child')
            self.assertFalse((Path(temp) / 'missing').exists())


if __name__ == '__main__':
    unittest.main()
