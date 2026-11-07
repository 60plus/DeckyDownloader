"""Validated aria2 TCP and DHT/UDP listening-port settings."""
import re
import secrets
import socket
import threading

DEFAULT_TORRENT_PORTS = "49152-65535"
_lock = threading.Lock()
_reserved = set()


def port_bounds(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,5}(?:-[0-9]{1,5})?", value):
        raise ValueError("Enter a torrent port or range, for example 51413 or 51413-51416.")
    pieces = value.split("-")
    first, last = int(pieces[0]), int(pieces[-1])
    if not 1024 <= first <= last <= 65535:
        raise ValueError("Torrent ports must be between 1024 and 65535 in ascending order.")
    return first, last


def normalize_ports(value):
    first, last = port_bounds(value.strip() if isinstance(value, str) else value)
    return str(first) if first == last else f"{first}-{last}"


def reserve_port(value):
    """Pick the same available TCP/UDP port for a UPnP-enabled aria2 process."""
    first, last = port_bounds(value)
    count = last - first + 1
    start = secrets.randbelow(count)
    with _lock:
        for offset in range(count):
            port = first + (start + offset) % count
            if port in _reserved:
                continue
            try:
                with socket.socket() as tcp, socket.socket(type=socket.SOCK_DGRAM) as udp:
                    # Match aria2's listener: recently closed peers can leave
                    # TIME_WAIT sockets after pause/completion. Those must not
                    # make a configured single port unusable on the next job.
                    tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    tcp.bind(('0.0.0.0', port))
                    udp.bind(('0.0.0.0', port))
                _reserved.add(port)
                return port
            except OSError:
                continue
    raise RuntimeError('No free TCP/UDP port in the configured torrent range.')


def release_port(port):
    with _lock:
        _reserved.discard(port)
