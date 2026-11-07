import socket
import unittest
from unittest.mock import patch

from downloader.ports import normalize_ports, port_bounds, reserve_port, release_port


class PortTests(unittest.TestCase):
    def test_range_validation(self):
        self.assertEqual(normalize_ports(' 05141-5141 '), '5141')
        self.assertEqual(port_bounds('1024-65535'), (1024, 65535))
        for value in (None, 51413, True, '', '0', '80', '65536', '51413-51412', '1-2-3', '5,6', '51413\n--foo'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_ports(value)

    def test_reservation_skips_occupied_ports_and_releases(self):
        with socket.socket() as busy:
            busy.bind(('0.0.0.0', 0))
            port = busy.getsockname()[1]
            with self.assertRaisesRegex(RuntimeError, 'No free'):
                reserve_port(str(port))
        first = reserve_port('49152-65535')
        try:
            with self.assertRaisesRegex(RuntimeError, 'No free'):
                reserve_port(str(first))
        finally:
            release_port(first)
        self.assertEqual(reserve_port(str(first)), first)
        release_port(first)
