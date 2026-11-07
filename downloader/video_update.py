"""Install official yt-dlp releases without modifying Varia or system files."""
import hashlib
import json
import math
import os
import platform
import re
import time
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlsplit

RELEASE_API = 'https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest'
RELEASE_BASE = 'https://github.com/yt-dlp/yt-dlp/releases/download/'
HOSTS = {'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
CHECK_INTERVAL = 24 * 60 * 60
RETRY_INTERVAL = 60 * 60


def next_check(root, now):
    try:
        with (Path(root) / 'video-engine/auto-check.json').open('rb') as stream:
            record = json.loads(stream.read(4096))
        due = record['next_check']
        if type(due) not in (int, float) or not math.isfinite(due) or due < 0:
            return 0
        # A clock correction must not postpone checks indefinitely.
        return min(due, now + CHECK_INTERVAL)
    except (OSError, ValueError, TypeError, KeyError):
        return 0


def save_check(root, due):
    folder = Path(root) / 'video-engine'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = folder / (uuid.uuid4().hex + '.check.tmp')
    try:
        with temp.open('x', encoding='utf-8') as stream:
            os.chmod(temp, 0o600)
            json.dump({'next_check': due}, stream)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, folder / 'auto-check.json')
    finally:
        temp.unlink(missing_ok=True)


class ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urlsplit(newurl)
        if url.scheme != 'https' or url.hostname not in HOSTS or url.username or url.password:
            raise ValueError('Unexpected video-engine download redirect.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, limit, stop, destination=None):
    opener = urllib.request.build_opener(ReleaseRedirect())
    request = urllib.request.Request(url, headers={'User-Agent': 'DeckyDownloader', 'Accept': 'application/octet-stream' if destination else '*/*'})
    total, chunks, deadline = 0, [], time.monotonic() + 180
    with opener.open(request, timeout=10) as response:
        while True:
            if stop.is_set() or time.monotonic() > deadline:
                raise RuntimeError('Video-engine update stopped or timed out.')
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ValueError('Video-engine download exceeds its size limit.')
            if destination:
                destination.write(chunk)
            else:
                chunks.append(chunk)
    return b''.join(chunks)


def install(root, runtime, stop, probe, only_newer=False):
    machine = platform.machine().lower()
    asset = {'x86_64': 'yt-dlp_linux', 'amd64': 'yt-dlp_linux', 'aarch64': 'yt-dlp_linux_aarch64'}.get(machine)
    if platform.system() != 'Linux' or not asset:
        raise ValueError('Video-engine updates support Linux x86_64 and aarch64.')
    release = json.loads(download(RELEASE_API, 1024 * 1024, stop))
    version = release.get('tag_name', '')
    if not re.fullmatch(r'\d{4}\.\d{2}\.\d{2}(?:\.\d+)?', version) or release.get('draft') or release.get('prerelease'):
        raise ValueError('Unexpected official yt-dlp release.')
    if only_newer:
        current = runtime.detect().get('video_version', '')
        if re.fullmatch(r'\d{4}\.\d{2}\.\d{2}(?:\.\d+)?', current):
            parts = lambda value: tuple(map(int, value.split('.'))) + ((0,) if len(value.split('.')) == 3 else ())
            if parts(current) >= parts(version):
                return current
    base = RELEASE_BASE + version + '/'
    checksums = download(base + 'SHA2-256SUMS', 65536, stop).decode('ascii')
    matches = [line.split()[0] for line in checksums.splitlines()
               if len(line.split()) == 2 and line.split()[1].lstrip('*') == asset]
    if len(matches) != 1 or not re.fullmatch(r'[0-9a-f]{64}', matches[0]):
        raise ValueError('Official yt-dlp checksum is missing or invalid.')
    folder = Path(root) / 'video-engine' / version
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    binary = folder / 'yt-dlp'
    temp = folder / (uuid.uuid4().hex + '.part')
    manifest = folder.parent / (uuid.uuid4().hex + '.json.tmp')
    try:
        if not binary.is_file() or hashlib.sha256(binary.read_bytes()).hexdigest() != matches[0]:
            with temp.open('xb') as stream:
                download(base + asset, 96 * 1024 * 1024, stop, stream)
                stream.flush(); os.fsync(stream.fileno())
            if hashlib.sha256(temp.read_bytes()).hexdigest() != matches[0]:
                raise ValueError('yt-dlp checksum verification failed. Previous engine kept.')
            os.chmod(temp, 0o700)
            # Version directories keep already running downloads on their engine.
            os.replace(temp, binary)
        if stop.is_set():
            raise RuntimeError('Video-engine update stopped.')
        probe(runtime.command('yt-dlp', [folder], video_path=binary), version)
        if stop.is_set():
            raise RuntimeError('Video-engine update stopped.')
        with manifest.open('x', encoding='utf-8') as stream:
            os.chmod(manifest, 0o600)
            json.dump({'version': version, 'sha256': matches[0]}, stream)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(manifest, folder.parent / 'current.json')
        runtime.detect(force=True)
        return version
    finally:
        temp.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
