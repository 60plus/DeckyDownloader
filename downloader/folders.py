"""Folder browsing, creation and mounted storage discovery for the picker."""
import os
import re
import shutil
from pathlib import Path


def mounted_paths(text):
    """Read mountinfo, including escaped whitespace and bind mount targets."""
    paths = set()
    for line in text.splitlines():
        fields = line.split()
        try:
            separator = fields.index("-")
            if separator < 6:
                continue
            target = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4])
            source = fields[separator + 2]
            # Omit OS pseudo-filesystems and system partitions. Include mounts
            # below standard removable/custom storage paths even for FUSE/NFS.
            storage = any(target.startswith(prefix) for prefix in ("/run/media/", "/media/", "/mnt/"))
            block = source.startswith("/dev/") and not any(
                target == prefix or target.startswith(prefix + "/")
                for prefix in ("/boot", "/efi", "/etc", "/usr", "/var", "/run", "/dev", "/sys", "/proc"))
            if target.startswith("/") and (storage or block or target == "/home"):
                paths.add(target)
        except (ValueError, IndexError):
            continue
    return sorted(paths)


def folder_status(path):
    writable = os.access(path, os.W_OK | os.X_OK)
    try:
        free = shutil.disk_usage(path).free
        if hasattr(os, "statvfs"):
            writable = writable and not bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except OSError:
        free = None
        writable = False
    return {"writable": writable, "free": free}


def locations(home):
    home = Path(home)
    candidates = [(str(home), "home"), (str(home / "Downloads"), "downloads"), (str(home.anchor), "root")]
    try:
        mounts = Path("/proc/self/mountinfo").read_text()
    except OSError:
        mounts = ""
    candidates.extend((path, "drive") for path in mounted_paths(mounts))
    result, seen = [], set()
    for value, kind in candidates:
        path = Path(value)
        try:
            if not path.is_dir() or not os.access(path, os.R_OK | os.X_OK):
                continue
            canonical = str(path.resolve())
            if canonical in seen:
                continue
            seen.add(canonical)
            result.append({"path": canonical, "name": path.name or canonical,
                           "kind": kind, **folder_status(canonical)})
        except OSError:
            continue
    return result


def browse(path, offset=0, fallback=False, torrents=False):
    if not isinstance(path, str) or not path or any(ord(c) < 32 for c in path):
        raise ValueError("Choose an absolute folder path.")
    target = Path(path).expanduser()
    if not target.is_absolute():
        raise ValueError("Choose an absolute folder path.")
    if type(offset) is not int or offset < 0 or type(fallback) is not bool or type(torrents) is not bool:
        raise ValueError("Invalid folder request.")
    # A default download directory may not exist yet. Open its nearest existing
    # parent on initial entry without creating anything merely by browsing.
    if fallback:
        while not target.exists() and target != target.parent:
            target = target.parent
    target = target.resolve(strict=True)
    entries = []
    with os.scandir(target) as children:
        for child in children:
            try:
                directory = child.is_dir()
                if directory or torrents and child.name.lower().endswith('.torrent') and child.is_file():
                    entries.append({"name": child.name, "path": child.path, "directory": directory})
            except OSError:
                continue  # A removable device or symlink may disappear.
    entries.sort(key=lambda entry: (not entry["directory"], entry["name"].casefold(), entry["name"]))
    end = offset + 200
    return {"path": str(target), "parent": str(target.parent),
            "entries": entries[offset:end], "next": end if len(entries) > end else None,
            **folder_status(target)}


def create_folder(parent, name):
    if not isinstance(parent, str) or not parent or any(ord(c) < 32 for c in parent):
        raise ValueError("Choose an existing absolute parent folder.")
    if (not isinstance(name, str) or not name.strip() or name in (".", "..")
            or any(c in name for c in '/\\:') or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise ValueError("Enter a folder name without path separators or control characters.")
    path = Path(parent).expanduser()
    if not path.is_absolute():
        raise ValueError("Choose an existing absolute parent folder.")
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise ValueError("The parent is not a folder.")
    if not folder_status(path)["writable"]:
        raise ValueError("The parent folder is not writable.")
    destination = path / name
    # A single mkdir never replaces an existing file, folder or symlink and
    # never creates missing parents (e.g. after removable media disappears).
    destination.mkdir()
    return {"path": str(destination)}
