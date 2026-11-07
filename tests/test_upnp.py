import threading
import time
import unittest
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from downloader.upnp import Gateway, GatewayError, Lease, local_url, xml


class Router(BaseHTTPRequestHandler):
    entries = {}
    calls = []
    fail_udp = False

    def log_message(self, *args):
        pass

    def do_POST(self):
        root = ET.fromstring(self.rfile.read(int(self.headers['Content-Length'])))
        action = list(root.find('{*}Body'))[0]
        name = action.tag.split('}')[-1]
        args = {child.tag: child.text or '' for child in action}
        self.calls.append((name, args))
        key = (args['NewExternalPort'], args['NewProtocol'])
        entry = self.entries.get(key)
        fault = None
        if name == 'GetSpecificPortMappingEntry':
            if entry is None:
                fault = '714'
            result = entry or {}
        elif name == 'AddPortMapping':
            if self.fail_udp and key[1] == 'UDP':
                fault = '725'
            else:
                self.entries[key] = args
            result = {}
        else:
            self.entries.pop(key, None)
            result = {}
        result = {'errorCode': fault, 'errorDescription': 'Test router rejection'} if fault else result
        body = ET.Element('Envelope')
        for key, value in result.items():
            ET.SubElement(body, key).text = str(value)
        data = ET.tostring(body)
        self.send_response(500 if fault else 200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class UPnPTests(unittest.TestCase):
    def setUp(self):
        Router.entries = {}
        Router.calls = []
        Router.fail_udp = False
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Router)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        # The production endpoint guard excludes loopback. Only this test's
        # simulated router is allowed; no SSDP discovery reaches the LAN.
        with patch('downloader.upnp.local_url', return_value='127.0.0.1'):
            self.gateway = Gateway(f'http://127.0.0.1:{self.server.server_port}/control',
                'urn:schemas-upnp-org:service:WANIPConnection:1', '192.168.1.20')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def wait(self, predicate):
        deadline = time.monotonic() + 4
        while not predicate() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue(predicate())

    def test_finite_lease_ownership_and_safe_removal(self):
        self.gateway.add(51413, 'TCP', 'ours')
        entry = Router.entries[('51413', 'TCP')]
        self.assertEqual(entry['NewLeaseDuration'], '3600')
        self.assertEqual(entry['NewInternalClient'], '192.168.1.20')
        self.gateway.remove(51413, 'TCP', 'someone-else')
        self.assertIn(('51413', 'TCP'), Router.entries)
        with self.assertRaisesRegex(RuntimeError, 'another mapping'):
            self.gateway.add(51413, 'TCP', 'someone-else')
        self.gateway.remove(51413, 'TCP', 'ours')
        self.assertEqual(Router.entries, {})

    def test_background_mapping_renews_and_stops(self):
        reports = []
        lease = Lease(51413, reports.append)
        with patch('downloader.upnp.discover', return_value=self.gateway), patch('downloader.upnp.LEASE_SECONDS', 2):
            lease.start()
            try:
                self.wait(lambda: sum(name == 'AddPortMapping' for name, _ in Router.calls) >= 4)
                self.assertEqual(set(Router.entries), {('51413', 'TCP'), ('51413', 'UDP')})
                self.assertTrue(any(report['status'] == 'mapped' for report in reports))
            finally:
                lease.close()
        self.assertFalse(lease.thread.is_alive())
        self.assertEqual(Router.entries, {})

    def test_partial_failure_removes_owned_mapping(self):
        reports = []
        Router.fail_udp = True
        lease = Lease(51413, reports.append)
        with patch('downloader.upnp.discover', return_value=self.gateway):
            lease.start()
            lease.thread.join(4)
        self.assertFalse(lease.thread.is_alive())
        self.assertEqual(Router.entries, {})
        self.assertEqual(reports[-1]['status'], 'failed')

    def test_endpoint_and_xml_validation(self):
        self.assertEqual(local_url('http://192.168.1.1:1234/control', '192.168.1.1'), '192.168.1.1')
        for address in ('http://example.org/x', 'http://8.8.8.8/x', 'file:///etc/passwd', 'http://127.0.0.1/x', 'http://user:pass@192.168.1.1/x'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                local_url(address)
        with self.assertRaises(ValueError):
            local_url('http://192.168.1.2/x', '192.168.1.1')
        with self.assertRaises(ValueError):
            xml(b'<!DOCTYPE x [<!ENTITY a "x">]><x/>')
