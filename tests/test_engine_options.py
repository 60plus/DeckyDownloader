import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from downloader.engines import Stopped, Transfer
from downloader.store import Store


class EngineOptionTests(unittest.TestCase):
    def test_options_reach_aria_and_upnp_default_makes_no_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / 'state', root / 'home')
            job = {'id': 'test', 'kind': 'torrent', 'directory': str(root / 'out'), 'source': 'magnet:?xt=urn:btih:' + 'a' * 40}
            runtime = Mock(env={}, command=Mock(return_value=['aria2c']))
            settings = dict(store.settings(), torrent_ports='51413-51416', bt_dht=False, bt_pex=False,
                bt_lpd=True, bt_encryption=True, upload_limit_kib=256, bt_max_peers=100)
            with patch('downloader.engines.spawn', side_effect=Stopped) as spawn, patch('downloader.upnp.discover') as discovery:
                with self.assertRaises(Stopped):
                    Transfer(job, store, runtime, settings, threading.Event()).run()
                discovery.assert_not_called()
                command = spawn.call_args.args[0]
            for flag in ('--listen-port=51413-51416', '--dht-listen-port=51413-51416', '--enable-dht=false',
                         '--enable-peer-exchange=false', '--bt-enable-lpd=true', '--bt-force-encryption=true',
                         '--max-upload-limit=256K', '--bt-max-peers=100', '--rpc-listen-all=false'):
                self.assertIn(flag, command)
