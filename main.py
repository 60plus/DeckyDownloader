import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import decky
from downloader.service import Service
from downloader.folders import browse, create_folder, locations


class Plugin:
    async def _main(self):
        self.service = Service(decky.DECKY_USER_HOME, decky.DECKY_PLUGIN_SETTINGS_DIR)
        await asyncio.to_thread(self.service.ensure_runtime)

    async def _unload(self):
        # Synchronous cleanup: Decky can close the RPC socket before awaiting
        # unload. Transfers survive closing the modal; loader unload pauses them.
        if hasattr(self, "service"):
            self.service.shutdown()

    async def _migration(self):
        pass

    async def request(self, method, args=None):
        try:
            if not hasattr(self, "service"):
                await self._main()
            routes = {"state": self.service.state, "settings": self.service.settings,
                      "add": self.service.add, "action": self.service.action,
                      "pause_all": self.service.pause_all, "resume_all": self.service.resume_all,
                      "resume_interrupted": self.service.resume_interrupted, "clear_completed": self.service.clear_completed,
                      "torrent_files": self.service.torrent_files, "torrent_select": self.service.torrent_select,
                      "install_runtime": self.service.install_runtime,
                      "update_video_engine": self.service.update_video_engine,
                      "browse_folders": browse,
                      "create_folder": create_folder,
                      "receiver_password": self.service.receiver.set_password,
                      "locations": lambda: locations(decky.DECKY_USER_HOME)}
            if method not in routes:
                raise ValueError("Unknown request.")
            result = await asyncio.to_thread(routes[method], **(args or {}))
            return {"ok": True, "data": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
