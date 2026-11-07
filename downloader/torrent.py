"""Bounded torrent metadata and selection, using aria2's one-based file IDs."""
import os
import re
from pathlib import Path

MAX_TORRENT = 20 * 1024 * 1024


def validate_upload(data):
    """Validate bounded v1/hybrid metainfo before retaining a remote upload."""
    if not data or len(data) > MAX_TORRENT:
        raise ValueError('Choose a .torrent file up to 20 MiB.')
    position, nodes = 0, 0

    def read(depth=0):
        nonlocal position, nodes
        nodes += 1
        if depth > 32 or nodes > 200000 or position >= len(data):
            raise ValueError('Invalid or overly complex torrent metadata.')
        token = data[position:position + 1]
        if token == b'i':
            end = data.find(b'e', position + 1, position + 24)
            number = data[position + 1:end]
            if end < 0 or not re.fullmatch(rb'0|-?[1-9][0-9]*', number):
                raise ValueError('Invalid torrent integer.')
            position = end + 1
            return int(number)
        if token in (b'd', b'l'):
            position += 1
            result = {} if token == b'd' else []
            while position < len(data) and data[position:position + 1] != b'e':
                value = read(depth + 1)
                if token == b'd':
                    if not isinstance(value, bytes) or value in result:
                        raise ValueError('Invalid torrent dictionary.')
                    result[value] = read(depth + 1)
                else:
                    result.append(value)
            if position >= len(data):
                raise ValueError('Incomplete torrent metadata.')
            position += 1
            return result
        end = data.find(b':', position, position + 10)
        number = data[position:end]
        if end < 0 or not re.fullmatch(rb'0|[1-9][0-9]*', number):
            raise ValueError('Choose a valid .torrent file, not a web page.')
        length = int(number)
        position = end + 1 + length
        if position > len(data):
            raise ValueError('Incomplete torrent metadata.')
        return data[end + 1:position]

    result = read()
    info = result.get(b'info') if isinstance(result, dict) else None
    if position != len(data) or not isinstance(info, dict):
        raise ValueError('Missing torrent info dictionary.')

    def segment(value):
        if (not isinstance(value, bytes) or not value or value in (b'.', b'..') or
                len(value) > 1024 or any(c < 32 for c in value) or any(c in value for c in (b'/', b'\\', b':'))):
            raise ValueError('Invalid torrent file name.')

    segment(info.get(b'name'))
    if b'name.utf-8' in info:
        segment(info[b'name.utf-8'])
    piece = info.get(b'piece length')
    pieces = info.get(b'pieces')
    if type(piece) is not int or piece <= 0 or not isinstance(pieces, bytes) or len(pieces) % 20:
        raise ValueError('A v1 or hybrid torrent with valid pieces is required.')
    files = info.get(b'files', [{b'length': info.get(b'length')}])
    if not isinstance(files, list) or not 1 <= len(files) <= 10000:
        raise ValueError('Torrent must contain between 1 and 10000 files.')
    total = 0
    for entry in files:
        if not isinstance(entry, dict) or type(entry.get(b'length')) is not int or entry[b'length'] < 0:
            raise ValueError('Invalid torrent file length.')
        total += entry[b'length']
        for key in ((b'path', b'path.utf-8') if b'files' in info else ()):
            path = entry.get(key)
            if path is None and key == b'path.utf-8':
                continue
            if not isinstance(path, list) or not 1 <= len(path) <= 64:
                raise ValueError('Invalid torrent file path.')
            for part in path:
                segment(part)
    if len(pieces) != ((total + piece - 1) // piece) * 20:
        raise ValueError('Torrent piece count does not match its files.')
    return info[b'name'].decode('utf-8', errors='replace')[:240]


def catalogue(data, directory):
    infohash = data.get('infoHash', '').lower()
    if not re.fullmatch(r'[0-9a-f]{40}', infohash):
        raise ValueError('Unsupported or missing torrent info hash.')
    source = data.get('files', [])
    if not source or len(source) > 10000:
        raise ValueError('Torrent must contain between 1 and 10000 files.')
    root = Path(directory).resolve()
    files, seen = [], set()
    for item in source:
        index, length = int(item['index']), int(item['length'])
        path = Path(item['path']).resolve()
        if index < 1 or index in seen or length < 0 or not path.is_relative_to(root):
            raise ValueError('Invalid torrent file metadata.')
        name = path.relative_to(root).as_posix()
        if len(name) > 2048 or any(ord(c) < 32 for c in name):
            raise ValueError('Unsupported torrent file name.')
        files.append({'index': index, 'name': name, 'length': length})
        seen.add(index)
    return infohash, files


def cache_metadata(destination, candidates):
    if destination.is_file():
        return
    for path in candidates:
        if path is None:
            continue
        try:
            with Path(path).open('rb') as stream:
                data = stream.read(20 * 1024 * 1024 + 1)
            if not data.startswith(b'd') or len(data) > 20 * 1024 * 1024:
                continue
            temp = destination.with_suffix('.tmp')
            temp.write_bytes(data)
            os.chmod(temp, 0o600)
            os.replace(temp, destination)
            return
        except OSError:
            continue
    raise ValueError('Could not save torrent metadata. Retry the download.')


def selected_progress(data):
    files = [f for f in data.get('files', []) if f.get('selected', 'true') == 'true']
    return (sum(int(f['length']) for f in files),
            sum(min(int(f.get('completedLength', 0)), int(f['length'])) for f in files))
