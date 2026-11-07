"""Opt-in IGD port leases. No discovery or router requests when disabled."""
import ipaddress
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlsplit

SERVICES = {f'urn:schemas-upnp-org:service:{kind}:{version}'
            for kind in ('WANIPConnection', 'WANPPPConnection') for version in (1, 2)}
LEASE_SECONDS = 3600


class GatewayError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f'UPnP {code}: {message}')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('UPnP redirects are not supported.')


def local_url(url, peer=None):
    parsed = urlsplit(url)
    try:
        address = ipaddress.ip_address(parsed.hostname or '')
    except ValueError:
        raise ValueError('UPnP endpoint must use a local IP address.') from None
    local = any(address in ipaddress.ip_network(net) for net in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16'))
    if parsed.scheme != 'http' or parsed.username or parsed.password or not local or (peer and str(address) != peer):
        raise ValueError('Invalid local UPnP endpoint.')
    return str(address)


def xml(data):
    if len(data) > 1024 * 1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Invalid UPnP XML response.')
    return ET.fromstring(data)


def fetch(request):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=2) as response:
            return xml(response.read(1024 * 1024 + 1))
    except urllib.error.HTTPError as exc:
        try:
            root = xml(exc.read(1024 * 1024 + 1))
        finally:
            exc.close()
        code = root.findtext('.//{*}errorCode', '')
        raise GatewayError(code, root.findtext('.//{*}errorDescription', 'Router rejected the request.')) from None


class Gateway:
    def __init__(self, control, service, address):
        self.control, self.service, self.address = control, service, address
        local_url(control)
        if service not in SERVICES:
            raise ValueError('Unsupported UPnP service.')

    def action(self, name, values):
        envelope = ET.Element('s:Envelope', {'xmlns:s': 'http://schemas.xmlsoap.org/soap/envelope/',
            's:encodingStyle': 'http://schemas.xmlsoap.org/soap/encoding/'})
        body = ET.SubElement(envelope, 's:Body')
        action = ET.SubElement(body, 'u:' + name, {'xmlns:u': self.service})
        for key, value in values.items():
            ET.SubElement(action, key).text = str(value)
        result = fetch(urllib.request.Request(self.control, data=ET.tostring(envelope, encoding='utf-8'),
            headers={'Content-Type': 'text/xml; charset="utf-8"', 'SOAPAction': f'"{self.service}#{name}"'}))
        return {element.tag.rsplit('}', 1)[-1]: element.text or '' for element in result.iter()}

    def entry(self, port, protocol):
        try:
            return self.action('GetSpecificPortMappingEntry', {'NewRemoteHost': '', 'NewExternalPort': port, 'NewProtocol': protocol})
        except GatewayError as exc:
            if exc.code == '714':
                return None
            raise

    def owns(self, entry, port, token):
        return entry and entry.get('NewInternalClient') == self.address and entry.get('NewInternalPort') == str(port) and entry.get('NewPortMappingDescription') == token

    def add(self, port, protocol, token):
        existing = self.entry(port, protocol)
        if existing and not self.owns(existing, port, token):
            raise RuntimeError(f'UPnP {protocol} port {port} already belongs to another mapping.')
        self.action('AddPortMapping', {'NewRemoteHost': '', 'NewExternalPort': port, 'NewProtocol': protocol,
            'NewInternalPort': port, 'NewInternalClient': self.address, 'NewEnabled': 1,
            'NewPortMappingDescription': token, 'NewLeaseDuration': LEASE_SECONDS})

    def remove(self, port, protocol, token):
        if self.owns(self.entry(port, protocol), port, token):
            self.action('DeletePortMapping', {'NewRemoteHost': '', 'NewExternalPort': port, 'NewProtocol': protocol})


def discover(stop):
    seen = set()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(.2)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        for version in (1, 2):
            message = ('M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\n'
                       f'MX: 1\r\nST: urn:schemas-upnp-org:device:InternetGatewayDevice:{version}\r\n\r\n')
            sock.sendto(message.encode(), ('239.255.255.250', 1900))
        deadline = time.monotonic() + 2
        while not stop.is_set() and time.monotonic() < deadline:
            try:
                payload, peer = sock.recvfrom(65535)
            except socket.timeout:
                continue
            headers = dict(line.split(':', 1) for line in payload.decode('latin1').split('\r\n')[1:] if ':' in line)
            location = next((v.strip() for k, v in headers.items() if k.lower() == 'location'), '')
            if location in seen or len(seen) >= 4:
                continue
            seen.add(location)
            try:
                address = local_url(location, peer[0])
                root = fetch(location)
                base = root.findtext('.//{*}URLBase') or location
                for service in root.findall('.//{*}service'):
                    kind = service.findtext('{*}serviceType')
                    if kind not in SERVICES:
                        continue
                    control = urljoin(base, service.findtext('{*}controlURL') or '')
                    local_url(control, address)
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
                        route.connect((address, 1900))
                        client = route.getsockname()[0]
                    return Gateway(control, kind, client)
            except (OSError, ValueError, RuntimeError, ET.ParseError):
                continue
    raise RuntimeError('No compatible UPnP router found on the local network.')


class Lease:
    def __init__(self, port, report):
        self.port, self.report = port, report
        self.stop = threading.Event()
        self.token = 'DeckyDownloader-' + secrets.token_hex(6)
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.report({'status': 'discovering', 'port': self.port})
        self.thread.start()

    def run(self):
        gateway, attempted = None, []
        try:
            gateway = discover(self.stop)
            while not self.stop.is_set():
                for protocol in ('TCP', 'UDP'):
                    if self.stop.is_set():
                        return
                    if protocol not in attempted:
                        attempted.append(protocol)
                    gateway.add(self.port, protocol, self.token)
                if not self.stop.is_set():
                    self.report({'status': 'mapped', 'port': self.port})
                if self.stop.wait(LEASE_SECONDS / 2):
                    break
        except Exception as exc:
            if not self.stop.is_set():
                self.report({'status': 'failed', 'error': str(exc), 'port': self.port})
        finally:
            if gateway:
                for protocol in attempted:
                    try:
                        gateway.remove(self.port, protocol, self.token)
                    except Exception:
                        pass  # The finite lease expires even after loss of network.

    def close(self):
        self.stop.set()
        self.thread.join(timeout=12)
