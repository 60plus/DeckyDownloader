import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from .ports import DEFAULT_TORRENT_PORTS


DEFAULTS = {"parallel": 2, "limit_kib": 0, "display": "auto", "language": "en", "torrent_ports": DEFAULT_TORRENT_PORTS,
            "upload_limit_kib": 0, "bt_max_peers": 55, "bt_dht": True, "bt_pex": True,
            "bt_lpd": False, "bt_encryption": False, "bt_upnp": False,
            "receiver_mode": "off", "receiver_port": 6802,
            "bt_select_files": True, "bt_seed": False, "bt_seed_ratio": 1.0,
            "video_auto_update": False}


class Store:
    """Short transactions; each thread owns its connection. No shared cursor."""

    def __init__(self, root, home):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "downloads.sqlite3"
        self.home = Path(home)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL,
                  name TEXT NOT NULL, directory TEXT NOT NULL, status TEXT NOT NULL,
                  completed INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
                  speed INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
                  created REAL NOT NULL, position REAL NOT NULL, quality TEXT NOT NULL,
                  updated REAL NOT NULL, phase TEXT NOT NULL DEFAULT ''
                );
            ''')
            # Existing transfers keep their original all-files behavior.
            columns = {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}
            for name, definition in {'selection_mode': "TEXT NOT NULL DEFAULT 'all'",
                                     'file_count': 'INTEGER NOT NULL DEFAULT 0',
                                     'uploaded': 'INTEGER NOT NULL DEFAULT 0',
                                     'upload_speed': 'INTEGER NOT NULL DEFAULT 0',
                                     'ratio_limit': 'REAL NOT NULL DEFAULT 0'}.items():
                if name not in columns:
                    db.execute(f'ALTER TABLE jobs ADD COLUMN {name} {definition}')
            db.execute('CREATE TABLE IF NOT EXISTS torrent_details (job_id TEXT PRIMARY KEY, infohash TEXT NOT NULL, files TEXT NOT NULL, selection TEXT)')
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self):
        values = dict(DEFAULTS, directory=str(self.home / "Downloads" / "DeckyDownloader"))
        with self.connect() as db:
            values.update({r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM settings")})
        return values

    def save_settings(self, values):
        with self.connect() as db:
            db.executemany("INSERT OR REPLACE INTO settings VALUES (?, ?)",
                           [(k, json.dumps(v)) for k, v in values.items()])

    def jobs(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY position, created")]

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Download no longer exists.")
        return dict(row)

    def insert(self, job):
        keys = tuple(job)
        with self.connect() as db:
            db.execute(f"INSERT INTO jobs ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                       tuple(job.values()))

    def update(self, job_id, **values):
        allowed = {"status", "completed", "total", "speed", "error", "name", "position", "phase",
                   "selection_mode", "file_count", "uploaded", "upload_speed", "ratio_limit"}
        if not set(values) <= allowed:
            raise ValueError("Invalid job update")
        values["updated"] = time.time()
        with self.connect() as db:
            db.execute(f"UPDATE jobs SET {','.join(k+'=?' for k in values)} WHERE id=?",
                       (*values.values(), job_id))

    def recover(self):
        # Never silently restart a transfer after a loader crash or system reboot.
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='paused', speed=0, upload_speed=0, phase='', "
                       "error='Interrupted by a restart. Resume to continue.' WHERE status IN ('active','queued','seeding','seed_waiting')")

    def delete(self, job_id):
        with self.connect() as db:
            db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            db.execute('DELETE FROM torrent_details WHERE job_id=?', (job_id,))

    def clear_completed(self, running):
        # Delete history only, in one transaction. Never touch download files.
        placeholders = ','.join('?' for _ in running)
        query = "DELETE FROM jobs WHERE status='complete'"
        if running:
            query += f" AND id NOT IN ({placeholders})"
        with self.connect() as db:
            count = db.execute(query, tuple(running)).rowcount
            db.execute('DELETE FROM torrent_details WHERE job_id NOT IN (SELECT id FROM jobs)')
            return count

    def torrent(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM torrent_details WHERE job_id=?', (job_id,)).fetchone()
        return dict(infohash=row['infohash'], files=json.loads(row['files']),
                    selection=json.loads(row['selection']) if row['selection'] else None) if row else None

    def save_torrent(self, job_id, infohash, files):
        with self.connect() as db:
            old = db.execute('SELECT infohash, files FROM torrent_details WHERE job_id=?', (job_id,)).fetchone()
            encoded = json.dumps(files, ensure_ascii=False)
            if old and (old['infohash'] != infohash or old['files'] != encoded):
                raise ValueError('Torrent metadata changed. Add it as a new download.')
            db.execute('INSERT OR IGNORE INTO torrent_details VALUES (?, ?, ?, NULL)', (job_id, infohash, encoded))
            db.execute('UPDATE jobs SET file_count=? WHERE id=?', (len(files), job_id))

    def select_torrent(self, job_id, indices):
        with self.connect() as db:
            db.execute('UPDATE torrent_details SET selection=? WHERE job_id=?', (json.dumps(indices), job_id))
            db.execute("UPDATE jobs SET selection_mode='selected', status='queued', error='', phase='', updated=? WHERE id=?", (time.time(), job_id))
