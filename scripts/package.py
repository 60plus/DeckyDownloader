"""Create a loader-compatible ZIP using only the Python standard library."""
import hashlib
import json
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
package = json.loads((ROOT / 'package.json').read_text())
manifest = json.loads((ROOT / 'plugin.json').read_text())
assert manifest['api_version'] == 1 and manifest['flags'] == []
assert (ROOT / 'dist/index.js').is_file(), 'Build the frontend first'
files = [ROOT / name for name in ('main.py', 'plugin.json', 'package.json', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md')]
files += sorted((ROOT / 'downloader').glob('*.py'))
files += sorted((ROOT / 'downloader').glob('*.js'))
files += sorted((ROOT / 'licenses').glob('*.txt'))
files += sorted(p for p in (ROOT / 'dist').rglob('*') if p.is_file() and p.suffix != '.map')
output = ROOT / 'out'
output.mkdir(exist_ok=True)
archive = output / f'decky-downloader-{package["version"]}.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
    for file in files:
        name = 'DeckyDownloader/' + file.relative_to(ROOT).as_posix()
        entry = zipfile.ZipInfo(name, date_time=(2026, 11, 6, 0, 0, 0))
        entry.create_system = 3
        entry.external_attr = (stat.S_IFREG | 0o644) << 16
        entry.compress_type = zipfile.ZIP_DEFLATED
        zip_file.writestr(entry, file.read_bytes())
with zipfile.ZipFile(archive) as zip_file:
    assert zip_file.testzip() is None
    assert all(name.startswith('DeckyDownloader/') and '..' not in name for name in zip_file.namelist())
    assert 'DeckyDownloader/dist/index.js' in zip_file.namelist()
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n')
print(f'{archive}\nSHA-256: {checksum}\n{len(files)} files; {archive.stat().st_size:,} bytes')
