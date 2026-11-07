import os
import math
import hashlib
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .engines import Stopped, SelectFiles, Transfer, spawn, stop_process
from .runtime import APP_ID, Runtime, handheld
from .store import Store
from .ports import normalize_ports, port_bounds
from .torrent import validate_upload
from .receiver import Receiver
from . import video_update


def validate_source(source, kind):
    if not isinstance(source, str) or not source.strip() or len(source) > 16384:
        raise ValueError("Enter a download link.")
    source = source.strip()
    if any(ord(c) < 32 for c in source):
        raise ValueError("Use one link per download, without control characters.")
    if kind == "torrent-file":
        path = Path(source)
        if not path.is_absolute() or path.suffix.lower() != ".torrent" or not path.is_file():
            raise ValueError("Choose an existing .torrent file.")
        if path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Torrent file exceeds 20 MiB.")
        return str(path.resolve())
    url = urlsplit(source)
    if url.scheme == "magnet" and kind == "file":
        if not any(v.startswith("urn:btih:") for v in parse_qs(url.query).get("xt", [])):
            raise ValueError("This magnet must include a BitTorrent v1 info hash (btih).")
        return source
    if url.scheme not in ("http", "https") or not url.hostname:
        raise ValueError("Use an HTTP(S) link or a BitTorrent magnet link.")
    # Force port parsing now, before a job is accepted.
    _ = url.port
    return source


def validate_directory(value):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError("Choose an absolute download folder.")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Choose an absolute download folder.")
    path = path.resolve()
    # Flatpak's --filesystem syntax uses ':' for access modes.
    if ":" in str(path) and os.name != "nt":
        raise ValueError("Folder names containing ':' are not supported by the Varia runtime.")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir() or not os.access(path, os.W_OK):
        raise ValueError("The download folder is not writable.")
    return str(path)


class Service:
    def __init__(self, home, root):
        self.store = Store(root, home)
        self.runtime = Runtime(home, root)
        self.lock = threading.RLock()
        self.settings_lock = threading.RLock()
        self.stopping = threading.Event()
        self.running = {}
        self.network = {}
        self.install = {"status": "idle", "error": ""}
        self.installer = None
        self.install_thread = None
        self.video_install = {'status': 'idle', 'error': ''}
        self.video_install_thread = None
        self.video_check_due = video_update.next_check(self.store.root, time.time())
        self.store.recover()
        self.receiver = Receiver(self)
        settings = self.store.settings()
        try:
            self.receiver.configure(settings["receiver_mode"], settings["receiver_port"])
        except ValueError:
            pass  # Keep the plugin usable; show the bind/key error in Settings.
        self.scheduler = threading.Thread(target=self._schedule, daemon=True)
        self.scheduler.start()

    def state(self):
        settings = self.store.settings()
        try:
            free = shutil.disk_usage(settings["directory"]).free
        except OSError:
            free = None
        with self.lock:
            install = dict(self.install)
            video_install = dict(self.video_install)
            network = [dict(value, job_id=key) for key, value in self.network.items()]
        return {"settings": settings, "jobs": self.store.jobs(), "runtime": self.runtime.detect(),
                "install": install, "handheld": handheld(), "free": free, "network": network,
                "receiver": self.receiver.status(), "video_install": video_install}

    def settings(self, changes):
        if not isinstance(changes, dict) or set(changes) - {"directory", "parallel", "limit_kib", "display", "language", "torrent_ports",
                "upload_limit_kib", "bt_max_peers", "bt_dht", "bt_pex", "bt_lpd", "bt_encryption", "bt_upnp",
                "receiver_mode", "receiver_port", "bt_select_files", "bt_seed", "bt_seed_ratio", "video_auto_update"}:
            raise ValueError("Unknown setting.")
        values = dict(changes)
        for key, lower, upper in (("parallel", 1, 4), ("limit_kib", 0, 1024000), ("upload_limit_kib", 0, 1024000), ("bt_max_peers", 0, 10000)):
            if key in values and (type(values[key]) is not int or not lower <= values[key] <= upper):
                raise ValueError(f"Invalid {key} value.")
        for key in ("bt_dht", "bt_pex", "bt_lpd", "bt_encryption", "bt_upnp", "bt_select_files", "bt_seed", "video_auto_update"):
            if key in values and type(values[key]) is not bool:
                raise ValueError(f"Invalid {key} value.")
        if 'bt_seed_ratio' in values and (type(values['bt_seed_ratio']) not in (int, float) or
                not math.isfinite(values['bt_seed_ratio']) or not 0.1 <= values['bt_seed_ratio'] <= 100):
            raise ValueError('Seed ratio must be between 0.1 and 100.')
        if "display" in values and values["display"] not in ("auto", "window", "fullscreen"):
            raise ValueError("Invalid display mode.")
        if "language" in values and values["language"] not in ("en", "pl"):
            raise ValueError("Invalid language.")
        if "torrent_ports" in values:
            values["torrent_ports"] = normalize_ports(values["torrent_ports"])
        if "receiver_mode" in values and values["receiver_mode"] not in ("off", "local", "lan"):
            raise ValueError("Invalid receiver mode.")
        if "receiver_port" in values and (type(values["receiver_port"]) is not int or not 1024 <= values["receiver_port"] <= 65535):
            raise ValueError("Receiver port must be between 1024 and 65535.")
        if "directory" in values:
            values["directory"] = validate_directory(values["directory"])
        with self.settings_lock:
            if self.stopping.is_set():
                raise RuntimeError("Plugin is stopping.")
            previous = self.store.settings()
            updated = dict(previous, **values)
            try:
                self.receiver.configure(updated["receiver_mode"], updated["receiver_port"])
                self.store.save_settings(values)
            except Exception:
                try:
                    self.receiver.configure(previous["receiver_mode"], previous["receiver_port"])
                except ValueError:
                    pass
                raise
        return True

    def add(self, source, kind="file", directory=None, quality="best"):
        if kind not in ("file", "torrent-file", "video", "audio"):
            raise ValueError("Unknown download type.")
        if quality not in ("best", "1080", "720", "480"):
            raise ValueError("Unknown video quality.")
        source = validate_source(source, kind)
        runtime = self.runtime.detect()
        engine = "video" if kind in ("video", "audio") else "aria2"
        if runtime[engine] == "missing":
            raise ValueError("Install Varia in Settings first.")
        if kind == "audio" and not runtime["ffmpeg"]:
            raise ValueError("Audio conversion requires FFmpeg. Install Varia in Settings.")
        directory = validate_directory(directory or self.store.settings()["directory"])
        url = urlsplit(source) if kind != "torrent-file" else None
        if url and url.scheme == "magnet":
            name = parse_qs(url.query).get("dn", ["Torrent"])[0]
            kind = "torrent"
        else:
            name = Path(unquote(url.path if url else source)).name or (url.hostname if url else "Download")
        name = name[:240]
        job_id = uuid.uuid4().hex
        safe_name = re.sub(r"[^\w .-]", "_", name, flags=re.UNICODE).strip(" .")[:60] or "download"
        # Each transfer owns a separate directory, so two equal filenames and
        # retries cannot overwrite another transfer's files.
        target = str(Path(directory) / f"{safe_name}-{job_id[:8]}")
        with self.lock:
            if self.stopping.is_set():
                raise RuntimeError("Plugin is stopping.")
            jobs = self.store.jobs()
            if len(jobs) >= 1000:
                raise ValueError("Queue history is full. Remove old entries first.")
            if any(j["source"] == source and j["kind"] == kind and j["status"] in ("active", "queued", "paused", "selecting", "seeding", "seed_waiting") for j in jobs):
                raise ValueError("This link is already in the queue.")
            self.store.insert(dict(id=job_id, source=source, kind=kind, name=name, directory=target,
                                   status="queued", quality=quality, created=time.time(), position=time.time(), updated=time.time(),
                                   selection_mode='ask' if self.store.settings()['bt_select_files'] else 'all'))
        return job_id

    def upload_torrent(self, data, directory=None):
        name = validate_upload(data)
        # Hash-named metainfo prevents user filenames from becoming server paths
        # and lets the existing duplicate check recognize repeated uploads.
        with self.lock:
            folder = self.store.root / 'uploads'
            folder.mkdir(mode=0o700, exist_ok=True)
            path = folder / (hashlib.sha256(data).hexdigest() + '.torrent')
            created = not path.exists()
            if created:
                temp = folder / (uuid.uuid4().hex + '.tmp')
                try:
                    with temp.open('xb') as stream:
                        os.chmod(temp, 0o600)
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temp, path)
                finally:
                    temp.unlink(missing_ok=True)
            try:
                job_id = self.add(str(path), kind='torrent-file', directory=directory)
            except Exception:
                if created:
                    path.unlink(missing_ok=True)
                raise
            self.store.update(job_id, name=name)
            return job_id

    def action(self, job_id, action):
        with self.lock:
            job = self.store.get(job_id)
            running = self.running.get(job_id)
            if action in ("pause", "cancel"):
                if job["status"] not in ("active", "queued", "paused", "error", "selecting", "seeding", "seed_waiting"):
                    raise ValueError("This download is already finished.")
                if running:
                    running[0].set()
                self.store.update(job_id, status="paused" if action == "pause" else "cancelled", speed=0, upload_speed=0, phase="")
            elif action in ("resume", "retry"):
                if running:
                    raise ValueError("The download is still stopping. Try again in a moment.")
                if job["status"] not in ("paused", "error", "cancelled"):
                    raise ValueError("This download cannot be resumed.")
                self.store.update(job_id, status='selecting' if job['file_count'] and job['selection_mode'] == 'ask' else 'queued', error="", speed=0, upload_speed=0, phase="")
            elif action == "remove":
                if running or job["status"] in ("active", "queued", "seeding", "seed_waiting"):
                    raise ValueError("Pause or cancel this download before removing it.")
                self.store.delete(job_id)
                self._remove_unused_upload(job['source'])
            elif action == "first":
                if job["status"] != "queued":
                    raise ValueError("Only queued downloads can be moved.")
                self.store.update(job_id, position=min(j["position"] for j in self.store.jobs()) - 1)
            else:
                raise ValueError("Unknown download action.")
        return True

    def pause_all(self):
        with self.lock:
            for job in self.store.jobs():
                if job["status"] in ("active", "queued", "seeding", "seed_waiting"):
                    self.action(job["id"], "pause")
        return True

    def resume_all(self):
        with self.lock:
            for job in self.store.jobs():
                if job["status"] == "paused" and job["id"] not in self.running:
                    self.action(job["id"], "resume")
        return True

    def resume_interrupted(self):
        with self.lock:
            count = 0
            for job in self.store.jobs():
                if job['status'] in ('paused', 'error', 'cancelled') and job['id'] not in self.running:
                    self.action(job['id'], 'resume')
                    count += 1
            return count

    def clear_completed(self):
        with self.lock:
            sources = {job['source'] for job in self.store.jobs() if job['status'] == 'complete'}
            count = self.store.clear_completed(self.running)
            for source in sources:
                self._remove_unused_upload(source)
            return count

    def _remove_unused_upload(self, source):
        path = Path(source)
        if (path.parent == self.store.root / 'uploads' and re.fullmatch(r'[0-9a-f]{64}\.torrent', path.name)
                and not any(job['source'] == source for job in self.store.jobs())):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # Removing a history entry must not depend on cache cleanup.

    def torrent_files(self, job_id):
        self.store.get(job_id)
        details = self.store.torrent(job_id)
        if not details:
            raise ValueError('Torrent metadata is not ready yet.')
        return details

    def torrent_select(self, job_id, indices):
        with self.lock:
            job = self.store.get(job_id)
            if job_id in self.running or job['status'] not in ('selecting', 'paused', 'error', 'cancelled'):
                raise ValueError('Wait for metadata or pause the torrent before changing files.')
            details = self.store.torrent(job_id)
            if not details or not isinstance(indices, list) or not indices or len(indices) > len(details['files']):
                raise ValueError('Select at least one torrent file.')
            allowed = {entry['index'] for entry in details['files']}
            if any(type(i) is not int or i not in allowed for i in indices) or len(set(indices)) != len(indices):
                raise ValueError('Invalid torrent file selection.')
            self.store.select_torrent(job_id, sorted(indices))
        return True

    def _schedule(self):
        while not self.stopping.wait(.25):
            with self.lock:
                if self.stopping.is_set():
                    break
                settings = self.store.settings()
                self._maybe_update_video(settings)
                jobs = self.store.jobs()
                if not settings['bt_seed']:
                    for job in jobs:
                        if job['status'] == 'seed_waiting' and job['id'] not in self.running:
                            self.store.update(job['id'], status='complete', upload_speed=0)
                            job['status'] = 'complete'
                first_port, last_port = port_bounds(settings['torrent_ports'])
                aria_slots = last_port - first_port + 1
                aria_running = sum(job['id'] in self.running and job['kind'] not in ('video', 'audio') for job in jobs)
                # Downloads get slots first. At most two additional processes
                # seed; they yield their torrent ports when a download needs one.
                jobs.sort(key=lambda j: j['status'] == 'seed_waiting')
                for job in jobs:
                    if job["status"] not in ('queued', 'seed_waiting') or job["id"] in self.running:
                        continue
                    seeding = sum(j['id'] in self.running and j['status'] in ('seeding', 'seed_waiting') for j in self.store.jobs())
                    if job['status'] == 'queued' and len(self.running) - seeding >= settings['parallel']:
                        continue
                    if job['status'] == 'seed_waiting' and (seeding >= 2 or len(self.running) >= settings['parallel'] + 2):
                        continue
                    uses_aria = job['kind'] not in ('video', 'audio')
                    # Each aria2 transfer owns a process (and TCP/UDP sockets).
                    # A one-port range must not launch competing processes.
                    # HTTP jobs count too: they may follow a torrent response.
                    if uses_aria and aria_running >= aria_slots:
                        if job['status'] == 'queued':
                            for seed in self.store.jobs():
                                if seed['status'] == 'seeding' and seed['id'] in self.running:
                                    self.store.update(seed['id'], status='seed_waiting', upload_speed=0)
                                    self.running[seed['id']][0].set()
                                    break
                        continue
                    stop = threading.Event()
                    thread = threading.Thread(target=self._run, args=(job, settings, stop), daemon=True)
                    self.running[job["id"]] = (stop, thread)
                    self.store.update(job["id"], status='seeding' if job['status'] == 'seed_waiting' else 'active', error="", phase="starting")
                    if uses_aria:
                        aria_running += 1
                    thread.start()

    def _run(self, job, settings, stop):
        status, error = "complete", ""
        try:
            transfer = Transfer(job, self.store, self.runtime, settings, stop)
            def report(value):
                with self.lock:
                    self.network[job['id']] = value
            transfer.report_network = report
            def seed():
                with self.lock:
                    current = self.store.get(job['id'])
                    if stop.is_set() or current['status'] not in ('active', 'seeding'):
                        raise Stopped()
                    if current['status'] == 'active' and sum(j['status'] == 'seeding' for j in self.store.jobs()) >= 2:
                        self.store.update(job['id'], status='seed_waiting', speed=0, upload_speed=0)
                        raise Stopped()
                    self.store.update(job['id'], status='seeding', speed=0)
            transfer.report_seeding = seed
            transfer.run()
        except SelectFiles:
            status = 'selecting'
        except Stopped:
            status = "paused"
        except Exception as exc:
            status, error = "error", str(exc)[:2000]
        finally:
            with self.lock:
                # An explicit pause/cancel always wins against a late completion.
                if self.store.get(job["id"])["status"] in ('active', 'seeding'):
                    self.store.update(job["id"], status=status, error=error, speed=0, upload_speed=0, phase="")
                else:
                    self.store.update(job["id"], speed=0, upload_speed=0, phase="")
                self.running.pop(job["id"], None)
                self.network.pop(job["id"], None)

    def install_runtime(self):
        with self.lock:
            if self.video_install['status'] == 'running':
                raise ValueError('Wait for the video-engine update to finish.')
            if self.install["status"] == "running":
                return True
            binary = shutil.which("flatpak")
            if not binary:
                raise ValueError("Flatpak is unavailable. Install aria2, yt-dlp and FFmpeg using your distribution.")
            self.install = {"status": "running", "error": ""}
            self.install_thread = threading.Thread(target=self._install, args=(binary,), daemon=True)
            self.install_thread.start()
        return True

    def update_video_engine(self):
        return self._start_video_update()

    def _maybe_update_video(self, settings):
        # Called by the queue scheduler; networking runs in a separate worker.
        if (not settings['video_auto_update'] or self.stopping.is_set() or time.time() < self.video_check_due
                or self.install['status'] == 'running' or self.video_install['status'] == 'running'):
            return
        try:
            runtime = self.runtime.detect()
            if runtime.get('flatpak') and not runtime.get('varia'):
                return  # Let first-start Varia setup own the installer first.
            self._start_video_update(automatic=True)
        except Exception as exc:
            self.video_check_due = time.time() + video_update.RETRY_INTERVAL
            self.video_install = {'status': 'error', 'error': str(exc)[:1000], 'automatic': True}

    def _start_video_update(self, automatic=False):
        with self.lock:
            if self.stopping.is_set():
                raise ValueError('Plugin is stopping.')
            if self.video_install['status'] == 'running':
                return True
            if self.install['status'] == 'running':
                raise ValueError('Wait for the Varia installation to finish.')
            due = time.time() + video_update.CHECK_INTERVAL
            video_update.save_check(self.store.root, due)
            self.video_check_due = due
            self.video_install = {'status': 'running', 'error': '', 'automatic': automatic}
            self.video_install_thread = threading.Thread(target=self._update_video, args=(automatic,), daemon=True)
            self.video_install_thread.start()
        return True

    def _update_video(self, automatic=False):
        def probe(command, version):
            with self.lock:
                if self.stopping.is_set():
                    raise RuntimeError('Video-engine update stopped.')
                process = self.installer = spawn([*command, '--version'], self.runtime.env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                stdout, stderr = process.communicate(timeout=30)
                if process.returncode or stdout.strip() != version:
                    raise RuntimeError('Updated yt-dlp could not start: ' + stderr[-500:])
            finally:
                stop_process(process)
                with self.lock:
                    if self.installer is process:
                        self.installer = None
        try:
            version = video_update.install(self.store.root, self.runtime, self.stopping, probe, only_newer=automatic)
            with self.lock:
                self.video_install = {'status': 'complete', 'error': '', 'version': version, 'automatic': automatic}
        except Exception as exc:
            with self.lock:
                self.video_check_due = time.time() + video_update.RETRY_INTERVAL
                try:
                    video_update.save_check(self.store.root, self.video_check_due)
                except OSError:
                    pass
                self.video_install = {'status': 'error', 'error': str(exc)[:1000], 'automatic': automatic}

    def ensure_runtime(self):
        state = self.runtime.detect()
        if state["varia"]:
            return
        if state["flatpak"]:
            self.install_runtime()
        else:
            self.install = {"status": "error", "error": "Flatpak is required to install the complete Varia runtime."}

    def _install(self, binary):
        log_path = self.store.root / "runtime-install.log"
        try:
            # The fixed Flathub reference works without configuring a user remote.
            with log_path.open("w", encoding="utf-8") as log:
                with self.lock:
                    if self.stopping.is_set():
                        return
                    self.installer = spawn([binary, "install", "--user", "--noninteractive", "--assumeyes", "--or-update",
                                            f"https://flathub.org/repo/appstream/{APP_ID}.flatpakref"],
                                           self.runtime.env, stdout=log, stderr=subprocess.STDOUT)
                code = self.installer.wait()
            if code:
                raise RuntimeError(log_path.read_text(errors="replace")[-2000:] or "Varia installation failed.")
            if not self.runtime.detect(force=True)["varia"]:
                raise RuntimeError("Flatpak finished but Varia is not available. Retry installation from Settings.")
            for command, version_arg in (("aria2c", "--version"), ("yt-dlp", "--version"), ("ffmpeg", "-version")):
                result = subprocess.run([binary, "run", f"--command={command}", APP_ID, version_arg],
                                        env=self.runtime.env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                        text=True, timeout=30)
                if result.returncode:
                    raise RuntimeError(f"Varia installed but {command} could not start: {result.stderr[-1000:]}")
            with self.lock:
                self.install = {"status": "complete", "error": ""}
        except Exception as exc:
            with self.lock:
                self.install = {"status": "error", "error": str(exc)}

    def shutdown(self):
        self.stopping.set()
        with self.settings_lock:
            self.receiver.stop()
        with self.lock:
            self.pause_all()
            threads = [entry[1] for entry in self.running.values()]
            installer = self.installer
        if installer:
            stop_process(installer)
        self.scheduler.join(timeout=2)
        deadline = time.monotonic() + 8
        for thread in threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        if self.install_thread:
            self.install_thread.join(timeout=2)
        if self.video_install_thread:
            self.video_install_thread.join(timeout=2)
