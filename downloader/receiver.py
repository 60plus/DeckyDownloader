"""Opt-in LAN manager. Authenticated commands use Service, never engine RPC."""
import ipaddress
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
from collections import deque, OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from .receiver_web import ASSETS
from . import folders
from .torrent import MAX_TORRENT

NETWORKS = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"))
MAX_BODY = 32768
PASSWORD_ITERATIONS = 210000


def valid_password(value):
    return isinstance(value, str) and 4 <= len(value) <= 128 and bool(value.strip()) and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def local_address(value):
    try:
        address = ipaddress.ip_address(value)
        return address.version == 4 and any(address in network for network in NETWORKS)
    except ValueError:
        return False


def lan_addresses():
    addresses = set()
    binary = shutil.which("ip")
    if binary:
        try:
            result = subprocess.run([binary, "-j", "-4", "address", "show", "scope", "global"],
                                    capture_output=True, text=True, timeout=2, check=True)
            for interface in json.loads(result.stdout):
                addresses.update(item.get("local", "") for item in interface.get("addr_info", []))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    if not addresses:
        try:
            addresses.update(item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
        except OSError:
            pass
    return sorted(address for address in addresses if local_address(address) and not address.startswith("127."))


class InboxServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = os.name != "nt"
    request_queue_size = 8

    def __init__(self, address, owner):
        self.owner = owner
        self.slots = threading.BoundedSemaphore(8)
        self.stream_slots = threading.BoundedSemaphore(4)
        self.stopped = threading.Event()
        super().__init__(address, InboxHandler)

    def process_request(self, request, client_address):
        if not local_address(client_address[0]) or not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # HTTP clients disappearing must not log tokens, URLs or payloads.
        pass


class InboxHandler(BaseHTTPRequestHandler):
    server_version = "DeckyDownloader"
    sys_version = ""

    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def log_message(self, *_args):
        pass

    def respond(self, code, data, content_type="application/json; charset=utf-8"):
        raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.response_headers(code, content_type, len(raw))
        self.wfile.write(raw)

    def response_headers(self, code, content_type, length=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        if getattr(self, "cors_origin", None):
            self.send_header("Access-Control-Allow-Origin", self.cors_origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def boundary(self):
        # Numeric private IPv4 hosts (or localhost) prevent DNS rebinding.
        hosts = self.headers.get_all("Host", [])
        try:
            if len(hosts) != 1:
                raise ValueError()
            host = urlsplit("http://" + hosts[0])
            if (host.hostname != "localhost" and not local_address(host.hostname or "")) or host.port != self.server.server_port:
                raise ValueError()
            if host.username or host.password or host.path or host.query or host.fragment:
                raise ValueError()
            origins = self.headers.get_all("Origin", [])
            if len(origins) > 1:
                raise ValueError()
            if origins:
                origin = origins[0]
                extension = re.fullmatch(r"moz-extension://[a-zA-Z0-9-]+", origin)
                if origin != "http://" + hosts[0] and not extension:
                    raise ValueError()
                if extension:
                    self.cors_origin = origin
        except ValueError:
            self.respond(403, {"error": "Use the receiver's local IP address and port."})
            return False
        return True

    def authorized(self):
        headers = self.headers.get_all("Authorization", [])
        result = self.server.owner.authenticate(headers[0] if len(headers) == 1 else "", self.client_address[0])
        if result == 429:
            self.respond(429, {"error": "Too many incorrect passwords. Wait one minute and try again."})
            return False
        if result != 200:
            self.respond(401, {"error": "Enter the password set in the plugin's Browser settings."})
            return False
        if self.server.owner.server is not self.server:
            self.respond(503, {"error": "Receiver is stopping. Check its settings."})
            return False
        return True

    def do_OPTIONS(self):
        if self.boundary():
            self.respond(204, b"")

    def do_GET(self):
        if not self.boundary():
            return
        if self.path in ASSETS:
            content, mime = ASSETS[self.path]
            self.respond(200, content.encode(), mime)
            return
        owner = self.server.owner
        with owner.lock:
            if not self.authorized():
                return
            credentials = owner.credentials
        if self.path == "/api/events":
            self.events(credentials)
            return
        try:
            if self.path == "/api/status":
                result = owner.snapshot()
            elif self.path == '/api/state':
                result = owner.service.state()
                result.pop('jobs', None)  # Queue is streamed separately; sources are fetched on demand.
            elif urlsplit(self.path).path == '/api/job':
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(query) != {'job_id'} or len(query['job_id']) != 1:
                    raise ValueError('Supply one download ID.')
                result = owner.service.store.get(query['job_id'][0])
            elif self.path == "/api/locations":
                result = {"locations": folders.locations(owner.service.store.home)}
            elif urlsplit(self.path).path == '/api/torrent-files':
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(query) != {'job_id'} or len(query['job_id']) != 1:
                    raise ValueError('Supply one torrent job ID.')
                with owner.service.lock:
                    job_id = query['job_id'][0]
                    job = owner.service.store.get(job_id)
                    result = owner.service.torrent_files(job_id)
                    result.update(status=job['status'], name=job['name'],
                                  editable=job_id not in owner.service.running and job['status'] in ('selecting', 'paused', 'error', 'cancelled'))
            elif urlsplit(self.path).path in ('/api/folders', '/api/device-torrents'):
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(query) - {"path", "offset"} or any(len(v) != 1 for v in query.values()):
                    raise ValueError("Invalid folder request.")
                result = folders.browse(query.get("path", [owner.service.store.settings()["directory"]])[0],
                                        offset=int(query.get("offset", ["0"])[0]), fallback="path" not in query,
                                        torrents=urlsplit(self.path).path == '/api/device-torrents')
            else:
                self.respond(404, {"error": "Not found."})
                return
            with owner.lock:
                if owner.server is self.server and owner.credentials is credentials:
                    self.respond(200, result)
                else:
                    self.respond(503, {"error": "Receiver settings changed. Reconnect."})
        except (ValueError, OSError) as exc:
            self.respond(400, {"error": str(exc)[:300]})

    def events(self, credentials):
        if not self.server.stream_slots.acquire(blocking=False):
            self.respond(503, {"error": "Live view is busy. Close another receiver tab."})
            return
        try:
            self.response_headers(200, "text/event-stream; charset=utf-8")
            # Bounded sessions reconnect in the client. Separate stream slots leave
            # room for commands. Never hold the receiver lock while waiting/I/O.
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                owner = self.server.owner
                with owner.lock:
                    if owner.server is not self.server or owner.credentials is not credentials:
                        break
                    payload = json.dumps(owner.snapshot()).encode()
                self.wfile.write(b"data: " + payload + b"\n\n")
                self.wfile.flush()
                if self.server.stopped.wait(1):
                    break
        except (OSError, ValueError):
            pass  # Disconnected client or a service shutting down.
        finally:
            self.server.stream_slots.release()

    def do_POST(self):
        if not self.boundary():
            return
        with self.server.owner.lock:
            if not self.authorized():
                return
        endpoint = urlsplit(self.path).path
        upload = endpoint == '/api/torrents'
        if endpoint not in ('/api/control', '/api/torrents', '/api/torrent-selection', '/api/torrent-pause', '/api/downloads', '/api/folders') or (not upload and self.path != endpoint):
            self.respond(404, {"error": "Not found."})
            return
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") or len(lengths) != 1 or not lengths[0].isdigit():
            self.respond(400, {"error": "A Content-Length is required."})
            return
        length = int(lengths[0])
        limit = MAX_TORRENT if upload else 131072 if endpoint == '/api/torrent-selection' else MAX_BODY
        if length > limit:
            self.respond(413, {"error": "Torrent upload exceeds 20 MiB." if upload else 'Request is too large.'})
            return
        content_type = 'application/x-bittorrent' if upload else 'application/json'
        if self.headers.get_content_type() != content_type:
            self.respond(415, {"error": 'Use ' + content_type + '.'})
            return
        try:
            self.request.settimeout(30 if upload else 5)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete request.")
            if upload:
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(query) - {'directory'} or any(len(v) != 1 or not v[0] for v in query.values()):
                    raise ValueError('Only one destination directory may be supplied.')
                data = {k: v[0] for k, v in query.items()}
            else:
                data = json.loads(raw)
            if endpoint == '/api/control':
                if not isinstance(data, dict) or set(data) != {'method', 'args'} or not isinstance(data['method'], str) or not isinstance(data['args'], dict):
                    raise ValueError('Supply a command and its arguments.')
                service = self.server.owner.service
                routes = {
                    'action': (service.action, {'job_id', 'action'}),
                    'pause_all': (service.pause_all, set()),
                    'resume_all': (service.resume_all, set()),
                    'resume_interrupted': (service.resume_interrupted, set()),
                    'clear_completed': (service.clear_completed, set()),
                    'settings': (service.settings, {'changes'}),
                    'receiver_password': (self.server.owner.set_password, {'password'}),
                    'install_runtime': (service.install_runtime, set()),
                    'update_video_engine': (service.update_video_engine, set()),
                    'device_torrent': (self.server.owner.device_torrent, {'source', 'directory'}),
                }
                if data['method'] not in routes:
                    raise ValueError('Unknown command.')
                callback, keys = routes[data['method']]
                args = data['args']
                if set(args) != keys or (data['method'] == 'action' and
                        any(not isinstance(args[k], str) for k in keys)):
                    raise ValueError('Invalid command arguments.')
                with self.server.owner.lock:
                    if not self.authorized():
                        return
                # Settings can restart this listener. Do not hold receiver.lock:
                # Service.settings takes settings_lock before receiver.lock.
                result = callback(**args)
                self.respond(200, {'result': result, 'receiver': self.server.owner.status()})
                return
            if endpoint in ('/api/torrent-selection', '/api/torrent-pause'):
                keys = {'job_id', 'indices'} if endpoint == '/api/torrent-selection' else {'job_id'}
                if not isinstance(data, dict) or set(data) != keys or not isinstance(data['job_id'], str):
                    raise ValueError('Invalid torrent request.')
                with self.server.owner.lock:
                    if not self.authorized():
                        return
                    service = self.server.owner.service
                    if endpoint == '/api/torrent-selection':
                        service.torrent_select(**data)
                    else:
                        with service.lock:
                            service.torrent_files(data['job_id'])
                            service.action(data['job_id'], 'pause')
                    self.respond(200, {'ok': True})
                return
            if self.path == "/api/folders":
                if not isinstance(data, dict) or set(data) != {"parent", "name"}:
                    raise ValueError("Supply a parent folder and a new folder name.")
                with self.server.owner.lock:
                    if self.authorized():
                        self.respond(201, folders.create_folder(**data))
                return
            if not isinstance(data, dict) or set(data) - {"source", "kind", "quality", "directory"}:
                raise ValueError("Only source, kind, quality and directory may be supplied.")
            if data.get("kind", "file") not in ("file", "video", "audio"):
                raise ValueError("Send an HTTP(S) link or magnet, not a local file path.")
            if not upload and (not isinstance(data.get("source"), str) or not isinstance(data.get("quality", "best"), str)):
                raise ValueError("Invalid link or quality.")
            with self.server.owner.lock:
                if not self.authorized():
                    return
                now = time.monotonic()
                recent = self.server.owner.recent
                while recent and recent[0] < now - 60:
                    recent.popleft()
                if len(recent) >= 60:
                    self.respond(429, {"error": "Too many links. Try again in one minute."})
                    return
                if "directory" in data:
                    # Explicit choices must still exist: never silently recreate
                    # a missing removable-drive path on the internal disk.
                    selected = folders.browse(data["directory"])
                    if not selected["writable"]:
                        raise ValueError("The selected folder is not writable.")
                    data["directory"] = selected["path"]
                job = self.server.owner.service.upload_torrent(raw, **data) if upload else self.server.owner.service.add(**data)
                recent.append(now)
                self.respond(201, {"id": job, "status": "queued"})
        except (ValueError, UnicodeError, TypeError) as exc:
            self.respond(400, {"error": str(exc)[:300]})
        except TimeoutError:
            self.respond(408, {"error": "Request timed out. Check the queue before retrying."})
        except OSError as exc:
            self.respond(400, {"error": str(exc)[:300]})
        except Exception:
            self.respond(503, {"error": "Could not complete the request. Check the plugin and refresh before retrying."})


class Receiver:
    def __init__(self, service):
        self.service = service
        self.lock = threading.RLock()
        self.server = None
        self.thread = None
        self.credentials = None
        self.failures = OrderedDict()
        self.error = ""
        self.mode = "off"
        self.port = 6802
        self.addresses = []
        self.recent = deque()
        try:
            self._load_credentials()
        except (OSError, ValueError):
            self.error = "Set a new receiver password in Settings."

    def _load_credentials(self):
        path = Path(self.service.store.root) / "receiver-password.json"
        if path.exists():
            with path.open("rb") as stream:
                record = json.loads(stream.read(4096))
            if (not isinstance(record, dict) or record.get("version") != 1 or
                    record.get("iterations") != PASSWORD_ITERATIONS or
                    not isinstance(record.get("salt"), str) or not re.fullmatch(r"[0-9a-f]{32}", record["salt"]) or
                    not isinstance(record.get("hash"), str) or not re.fullmatch(r"[0-9a-f]{64}", record["hash"])):
                raise ValueError("Stored password is invalid. Set a new password in Settings.")
            self.credentials = record
            return
        # Preserve existing 0.1.4 pairings until the owner chooses a password.
        legacy = Path(self.service.store.root) / "receiver-key"
        if legacy.exists():
            with legacy.open("r", encoding="ascii") as stream:
                value = stream.read(128).strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
                raise ValueError("Set a receiver password in Settings.")
            self.set_password(value)

    def set_password(self, password):
        if not valid_password(password):
            raise ValueError("Use a password with 4-128 characters, without control characters.")
        with self.lock:
            salt = secrets.token_bytes(16)
            record = {"version": 1, "iterations": PASSWORD_ITERATIONS, "salt": salt.hex(),
                      "hash": hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PASSWORD_ITERATIONS).hex()}
            self._save_credentials(record)
            self.credentials = record
            self.failures.clear()
            self.error = ""
            # A fresh password must never fall back to the previous raw key.
            (Path(self.service.store.root) / "receiver-key").unlink(missing_ok=True)
            return self.status()

    def _save_credentials(self, record):
        path = Path(self.service.store.root) / "receiver-password.json"
        temp = path.with_name(".receiver-password-" + secrets.token_hex(8))
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                json.dump(record, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def authenticate(self, header, client):
        # Bound both password verification cost and attempts per client. All
        # callers hold self.lock, so a password change invalidates old requests.
        now = time.monotonic()
        attempts = self.failures.setdefault(client, deque())
        self.failures.move_to_end(client)
        while len(self.failures) > 128:
            self.failures.popitem(last=False)
        while attempts and attempts[0] <= now - 60:
            attempts.popleft()
        if len(attempts) >= 10:
            return 429
        password = None
        try:
            if header.startswith("Basic ") and len(header) <= 1024:
                username, value = base64.b64decode(header[6:], validate=True).decode('utf-8').split(':', 1)
                if username == 'downloader' and valid_password(value):
                    password = value
            elif header.startswith("Bearer ") and re.fullmatch(r"[A-Za-z0-9_-]{43}", header[7:]):
                password = header[7:]  # Compatibility with an already paired 0.1.4 sender.
        except (ValueError, UnicodeError):
            pass
        if password is not None and self.credentials:
            digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                         bytes.fromhex(self.credentials['salt']), PASSWORD_ITERATIONS).hex()
            if secrets.compare_digest(digest, self.credentials['hash']):
                return 200
        attempts.append(now)
        return 401

    def configure(self, mode, port):
        with self.lock:
            if self.server and (self.mode, self.port) == (mode, port):
                return
            self.stop()
            self.mode, self.port, self.error = mode, port, ""
            if mode == "off":
                return
            try:
                self._load_credentials()
                if not self.credentials:
                    raise ValueError("Set a receiver password in Settings first.")
                server = InboxServer(("127.0.0.1" if mode == "local" else "0.0.0.0", port), self)
                self.addresses = lan_addresses() if mode == "lan" else []
                thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
                try:
                    thread.start()
                except BaseException:
                    server.server_close()
                    raise
                self.server, self.thread, self.port = server, thread, server.server_port
            except Exception as exc:
                self.error = "Cannot start receiver. Check the port and password. " + str(exc)
                self.stop()
                raise ValueError(self.error) from exc

    def stop(self):
        with self.lock:
            server, self.server = self.server, None
            if server:
                server.stopped.set()
                server.shutdown()
                server.server_close()
            if self.thread:
                self.thread.join(timeout=2)
                self.thread = None

    def snapshot(self):
        directory = self.service.store.settings()['directory']
        try:
            free = shutil.disk_usage(directory).free
        except OSError:
            free = None
        return {"app": "DeckyDownloader", "api": 4,
                "directory": directory, "free": free,
                "jobs": [{k: job[k] for k in ("id", "name", "status", "completed", "total", "speed", "directory", "uploaded", "upload_speed", "ratio_limit", "file_count", "error")}
                         for job in self.service.store.jobs()]}

    def device_torrent(self, source, directory):
        if not isinstance(source, str) or not source or any(ord(c) < 32 for c in source):
            raise ValueError('Choose an existing .torrent file on the handheld.')
        path = Path(source)
        if not path.is_absolute() or path.suffix.lower() != '.torrent' or not path.is_file():
            raise ValueError('Choose an existing .torrent file on the handheld.')
        if directory is not None:
            folder = folders.browse(directory)
            if not folder['writable']:
                raise ValueError('The selected folder is not writable.')
            directory = folder['path']
        with path.open('rb') as stream:
            data = stream.read(MAX_TORRENT + 1)
        return self.service.upload_torrent(data, directory=directory)

    def status(self):
        with self.lock:
            return {"running": self.server is not None, "error": self.error, "port": self.port, "password_set": self.credentials is not None,
                    "urls": [f"http://{host}:{self.port}" for host in (["127.0.0.1"] + self.addresses)] if self.server else []}
