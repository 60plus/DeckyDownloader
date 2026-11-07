"""Use Varia's maintained Flatpak engines, or native installations. No root."""
import os
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

APP_ID = "io.github.giantpinkrobots.varia"


def environment(home):
    env = dict(os.environ, HOME=str(home), LC_ALL="C.UTF-8", PYTHONUNBUFFERED="1")
    if os.name == "posix":
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=" + env["XDG_RUNTIME_DIR"] + "/bus")
    return env


class Runtime:
    def __init__(self, home, root=None):
        self.home = Path(home)
        self.env = environment(home)
        self.cached = None
        self.checked = 0
        self.root = Path(root) if root else None
        self.version_key = None
        self.video_version = ''

    def video_override(self):
        if not self.root:
            return None
        try:
            record = json.loads((self.root / 'video-engine/current.json').read_text())
            version = record['version']
            if not isinstance(version, str) or not re.fullmatch(r'\d{4}\.\d{2}\.\d{2}(?:\.\d+)?', version):
                return None
            path = self.root / 'video-engine' / version / 'yt-dlp'
            return (version, path) if path.is_file() and os.access(path, os.X_OK) else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def detect(self, force=False):
        if self.cached is not None and not force and time.monotonic() - self.checked < 15:
            return dict(self.cached)
        flatpak = shutil.which("flatpak")
        installed = False
        if flatpak:
            try:
                installed = subprocess.run([flatpak, "info", APP_ID], stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL, env=self.env, timeout=5).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                pass
        override = self.video_override()
        self.cached = {"flatpak": bool(flatpak), "varia": installed,
                       "aria2": "varia" if installed else ("native" if shutil.which("aria2c") else "missing"),
                       "video": "varia" if installed else ("native" if override or shutil.which("yt-dlp") else "missing"),
                       "ffmpeg": installed or bool(shutil.which("ffmpeg"))}
        self.checked = time.monotonic()
        key = (installed, override[0] if override else None, shutil.which('yt-dlp'))
        if force or key != self.version_key:
            self.version_key = key
            self.video_version = override[0] if override else ''
            if not override and self.cached['video'] != 'missing':
                command = [flatpak, 'run', '--command=yt-dlp', APP_ID] if installed else [shutil.which('yt-dlp')]
                try:
                    result = subprocess.run([*command, '--version'], env=self.env, capture_output=True, text=True, timeout=5)
                    version = result.stdout.strip()
                    if result.returncode == 0 and re.fullmatch(r'\d{4}\.\d{2}\.\d{2}(?:\.\d+)?', version):
                        self.video_version = version
                except (OSError, subprocess.TimeoutExpired):
                    pass
        self.cached.update(video_version=self.video_version, video_managed=bool(override))
        return dict(self.cached)

    def command(self, engine, directories, video_path=None):
        state = self.detect()
        override = self.video_override() if engine == 'yt-dlp' else None
        managed = video_path if engine == 'yt-dlp' and video_path else override[1] if override else None
        if managed:
            if not state['varia']:
                return [str(managed)]
            access = [f'--filesystem={Path(p).resolve()}' for p in dict.fromkeys([*directories, Path(managed).parent])]
            return [shutil.which('flatpak'), 'run', *access, f'--command={managed}', APP_ID]
        provider = state["aria2" if engine == "aria2c" else "video"]
        if provider == "missing":
            raise RuntimeError("Install Varia in Settings to enable this download type.")
        if provider == "native":
            binary = shutil.which(engine)
            if not binary:
                raise RuntimeError(f"{engine} is no longer installed.")
            return [binary]
        # Grants apply only to this invocation, not to Varia's persistent permissions.
        access = [f"--filesystem={Path(p).resolve()}" for p in dict.fromkeys(directories)]
        return [shutil.which("flatpak"), "run", *access, f"--command={engine}", APP_ID]


def handheld():
    try:
        vendor = Path('/sys/class/dmi/id/sys_vendor').read_text().strip().lower()
        product = Path('/sys/class/dmi/id/product_name').read_text().strip().lower()
        return vendor == 'valve' or any(x in product for x in ('rog ally', 'legion go', 'claw', 'ayaneo', 'gpd win', 'onexplayer'))
    except OSError:
        return False
