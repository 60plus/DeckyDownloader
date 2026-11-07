import json
import os
import queue
import secrets
import shutil
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from .ports import DEFAULT_TORRENT_PORTS, normalize_ports, reserve_port, release_port
from .upnp import Lease
from .torrent import catalogue, cache_metadata, selected_progress


class Stopped(Exception):
    pass


class SelectFiles(Exception):
    pass


def stop_process(process):
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=2)
    except ProcessLookupError:
        pass


def spawn(command, env, lock_path=None, **kwargs):
    options = {"start_new_session": True} if os.name == "posix" else {"creationflags": subprocess.CREATE_NO_WINDOW}
    if os.name == "posix":
        python = shutil.which('python3')
        if not python:
            raise RuntimeError('Python 3 is required to supervise download engines.')
        command = [python, str(Path(__file__).with_name('child.py')), str(os.getpid()), str(lock_path or '-'), *command]
    return subprocess.Popen(command, stdin=subprocess.DEVNULL, env=env, **options, **kwargs)


class Transfer:
    def __init__(self, job, store, runtime, settings, stop):
        self.job, self.store, self.runtime, self.settings, self.stop = job, store, runtime, settings, stop
        self.process = None
        self.mapping = None
        self.reserved_port = None
        self.report_network = lambda value: None
        self.report_seeding = lambda: None
        self.work = store.root / "tasks" / job["id"]
        self.work.mkdir(parents=True, exist_ok=True, mode=0o700)

    def check(self):
        if self.stop.is_set():
            raise Stopped()

    def progress(self, **values):
        self.check()
        self.store.update(self.job["id"], **values)

    def run(self):
        self.check()
        Path(self.job["directory"]).mkdir(parents=True, exist_ok=True)
        try:
            if self.job["kind"] in ("video", "audio"):
                self.video()
            else:
                self.aria()
        finally:
            try:
                if self.process:
                    stop_process(self.process)
            finally:
                try:
                    if self.mapping:
                        self.mapping.close()
                finally:
                    if self.reserved_port is not None:
                        release_port(self.reserved_port)

    def aria(self):
        torrent_ports = normalize_ports(self.settings.get('torrent_ports', DEFAULT_TORRENT_PORTS))
        if self.settings.get('bt_upnp', False):
            self.reserved_port = reserve_port(torrent_ports)
            torrent_ports = str(self.reserved_port)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        token = secrets.token_hex(24)
        config = self.work / "aria2.conf"
        config.write_text(f"rpc-secret={token}\n", encoding="utf-8")
        os.chmod(config, 0o600)
        source = self.job["source"]
        paths = [self.work, self.job["directory"]]
        if self.job["kind"] == "torrent-file":
            paths.append(Path(source).parent)
        cmd = self.runtime.command("aria2c", paths)
        cmd += [f"--conf-path={config}", "--enable-rpc=true", "--rpc-listen-all=false",
                "--rpc-allow-origin-all=false", f"--rpc-listen-port={port}",
                "--continue=true", "--check-integrity=true", "--allow-overwrite=false", "--auto-file-renaming=false",
                "--file-allocation=none", "--max-connection-per-server=4", "--split=4",
                "--max-tries=5", "--retry-wait=3", "--connect-timeout=20", "--timeout=30",
                "--check-certificate=true", "--summary-interval=0", "--console-log-level=warn",
                "--enable-color=false", "--download-result=hide", "--seed-ratio=0.0",
                "--pause-metadata=true", "--bt-remove-unselected-file=false",
                "--bt-save-metadata=true", "--bt-metadata-only=false", "--follow-torrent=true",
                f"--enable-dht={str(self.settings.get('bt_dht', True)).lower()}", "--enable-dht6=false", "--disable-ipv6=false",
                f"--enable-peer-exchange={str(self.settings.get('bt_pex', True)).lower()}",
                f"--bt-enable-lpd={str(self.settings.get('bt_lpd', False)).lower()}",
                f"--bt-force-encryption={str(self.settings.get('bt_encryption', False)).lower()}",
                f"--bt-max-peers={self.settings.get('bt_max_peers', 55)}",
                f"--max-upload-limit={self.settings.get('upload_limit_kib', 0)}K",
                f"--listen-port={torrent_ports}", f"--dht-listen-port={torrent_ports}",
                f"--dht-file-path={self.work / 'dht.dat'}", "--rpc-max-request-size=32M",
                f"--dir={self.job['directory']}",
                f"--max-download-limit={self.settings['limit_kib']}K"]
        # RPC submissions keep URLs/passwords out of the process list and allow
        # following the metadata GID into the actual magnet/torrent transfer.
        log_path = self.work / "engine.log"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def rpc(method, *params):
            self.check()
            payload = json.dumps({"jsonrpc": "2.0", "id": "decky", "method": "aria2." + method,
                                  "params": ["token:" + token, *params]}).encode()
            request = urllib.request.Request(f"http://127.0.0.1:{port}/jsonrpc", data=payload,
                                             headers={"Content-Type": "application/json"})
            with opener.open(request, timeout=1) as response:
                result = json.load(response)
            if "error" in result:
                raise RuntimeError(result["error"].get("message", "aria2 request failed"))
            return result["result"]

        with log_path.open("w", encoding="utf-8") as log:
            self.process = spawn(cmd, self.runtime.env, lock_path=self.work / 'engine.lock', stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 30
            while True:
                self.check()
                if self.process.poll() is not None:
                    raise RuntimeError("aria2 could not start. " + log_path.read_text(errors="replace")[-1500:])
                try:
                    rpc("getVersion")
                    break
                except (OSError, ValueError):
                    if time.monotonic() > deadline:
                        raise RuntimeError("aria2 did not open its local control connection.")
                    self.stop.wait(.2)
            cached = self.work / 'source.torrent'
            details = self.store.torrent(self.job['id'])
            selection = details['selection'] if details else None
            options = {'pause': 'true'}
            if selection:
                options['select-file'] = ','.join(map(str, selection))
            if self.job["kind"] == "torrent-file" or cached.is_file():
                import base64
                with (cached if cached.is_file() else Path(source)).open("rb") as torrent:
                    data = torrent.read(20 * 1024 * 1024 + 1)
                if len(data) > 20 * 1024 * 1024:
                    raise ValueError("Torrent file exceeds 20 MiB.")
                gid = rpc("addTorrent", base64.b64encode(data).decode(), [], options)
            else:
                gid = rpc("addUri", [source], {})
            failures = 0
            torrent_ready = False
            metadata_parent = None
            uploaded_before = self.job.get('uploaded', 0)
            upload_start = 0
            while True:
                self.check()
                if self.process.poll() is not None:
                    raise RuntimeError("aria2 stopped unexpectedly. " + log_path.read_text(errors="replace")[-1500:])
                try:
                    data = rpc("tellStatus", gid)
                    failures = 0
                except OSError:
                    failures += 1
                    if failures >= 5:
                        raise RuntimeError("Lost the connection to aria2. Resume to retry.")
                    self.stop.wait(.5)
                    continue
                if data.get("followedBy"):
                    if data.get('files'):
                        parent = Path(data['files'][0].get('path', '')).resolve()
                        if parent.is_relative_to(Path(self.job['directory']).resolve()):
                            metadata_parent = parent
                    gid = data["followedBy"][0]
                    continue
                if not torrent_ready and data.get('bittorrent', {}).get('info') and data.get('files'):
                    infohash, files = catalogue(data, self.job['directory'])
                    self.store.save_torrent(self.job['id'], infohash, files)
                    cache_metadata(cached, [Path(source) if self.job['kind'] == 'torrent-file' else None,
                                           Path(self.job['directory']) / (infohash + '.torrent'), metadata_parent])
                    torrent_ready = True
                    upload_start = int(data.get('uploadLength', 0))
                    if self.job.get('selection_mode') == 'ask' and selection is None:
                        self.progress(total=sum(f['length'] for f in files), completed=0, speed=0,
                                      name=data['bittorrent']['info'].get('name', self.job['name']))
                        raise SelectFiles()
                    # The payload is paused until metadata and the persisted
                    # selection have been verified, even on resume.
                    if data['status'] == 'paused':
                        rpc('unpause', gid)
                        continue
                elif data['status'] == 'paused' and not data.get('bittorrent'):
                    rpc('unpause', gid)
                    continue
                if self.reserved_port is not None and not self.mapping and ('bittorrent' in data or self.job['kind'].startswith('torrent')) and self.store.settings().get('bt_upnp'):
                    self.mapping = Lease(self.reserved_port, self.report_network)
                    self.mapping.start()
                if self.mapping and not self.store.settings().get('bt_upnp') and not self.mapping.stop.is_set():
                    self.mapping.close()
                    self.report_network({'status': 'disabled'})
                total, completed = int(data.get("totalLength", 0)), int(data.get("completedLength", 0))
                if torrent_ready:
                    total, completed = selected_progress(data)
                name = data.get("bittorrent", {}).get("info", {}).get("name")
                if not name and data.get("files"):
                    name = Path(data["files"][0].get("path", "")).name
                update = dict(total=total, completed=completed, speed=int(data.get("downloadSpeed", 0)),
                              phase="metadata" if not total and self.job["kind"] == "torrent" else "downloading")
                if name:
                    update["name"] = name
                if torrent_ready:
                    uploaded = uploaded_before + max(0, int(data.get('uploadLength', 0)) - upload_start)
                    current_settings = self.store.settings()
                    limit = current_settings['bt_seed_ratio']
                    update.update(uploaded=uploaded, upload_speed=int(data.get('uploadSpeed', 0)), ratio_limit=limit)
                self.progress(**update)
                if torrent_ready and data['status'] in ('active', 'complete') and (data.get('seeder') == 'true' or
                        data['status'] == 'complete' or total > 0 and completed >= total and
                        not data.get('verifyIntegrityPending') and 'verifiedLength' not in data):
                    if not current_settings['bt_seed'] or total == 0 or uploaded >= total * limit:
                        return
                    self.report_seeding()
                if data["status"] == "complete":
                    return
                if data["status"] in ("error", "removed"):
                    raise RuntimeError(data.get("errorMessage") or "Download stopped. Check the source and free space.")
                self.stop.wait(.5)

    def video(self):
        cmd = self.runtime.command("yt-dlp", [self.work, self.job["directory"]])
        cmd += ["--ignore-config", "--no-playlist", "--newline", "--no-colors", "--progress", "--no-overwrites",
                "--continue", "--socket-timeout", "20", "--retries", "5", "--no-mtime",
                "--paths", self.job["directory"], "--output", "%(title).180B [%(id)s].%(ext)s",
                "--progress-template", 'download:DD_PROGRESS %(progress)j',
                "--print", 'before_dl:DD_INFO {"title":%(title)j}',
                "--print", 'after_move:DD_FILE %(filepath)j']
        if self.settings["limit_kib"]:
            cmd += ["--limit-rate", f"{self.settings['limit_kib']}K"]
        if self.job["kind"] == "audio":
            cmd += ["--format", "bestaudio/best", "--extract-audio", "--audio-format", "mp3"]
        elif self.runtime.detect()["ffmpeg"]:
            quality = self.job["quality"]
            selection = "bv*+ba/b" if quality == "best" else f"bv*[height<={quality}]+ba/b[height<={quality}]"
            cmd += ["--format", selection, "--merge-output-format", "mkv"]
        else:
            cmd += ["--format", "best"]
        cmd += ["--", self.job["source"]]
        self.process = spawn(cmd, self.runtime.env, lock_path=self.work / 'engine.lock', stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", bufsize=1)
        lines = queue.Queue(maxsize=256)
        finished = threading.Event()

        def read():
            try:
                for line in self.process.stdout:
                    while not self.stop.is_set():
                        try:
                            lines.put(line, timeout=.2)
                            break
                        except queue.Full:
                            pass
            finally:
                self.process.stdout.close()
                finished.set()

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        tail = []
        while not (finished.is_set() and lines.empty()):
            self.check()
            try:
                line = lines.get(timeout=.3).strip()
            except queue.Empty:
                continue
            if line.startswith("DD_PROGRESS "):
                try:
                    data = json.loads(line[12:])
                    self.progress(completed=int(data.get("downloaded_bytes") or 0),
                                  total=int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0),
                                  speed=int(data.get("speed") or 0),
                                  phase="processing" if data.get("status") == "finished" else "downloading")
                except (ValueError, TypeError):
                    pass
            elif line.startswith("DD_INFO "):
                try:
                    self.progress(name=str(json.loads(line[8:])["title"]))
                except (ValueError, KeyError):
                    pass
            elif line.startswith("DD_FILE "):
                self.progress(phase="processing", speed=0)
            else:
                tail = (tail + [line])[-8:]
        self.check()
        if self.process.wait(timeout=5):
            message = "\n".join(tail)[-1500:] or "Video download failed."
            if 'HTTP Error 403' in message:
                message = 'The video server refused the download (HTTP 403). Update yt-dlp in Settings > Download engines, then retry. If it still fails, the video or connection may require additional access.\n\n' + message
            raise RuntimeError(message)
