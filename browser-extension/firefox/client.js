'use strict';
globalThis.DownloaderClient = {
  address(value) {
    const url = new URL(value);
    const parts = url.hostname.split('.').map(Number);
    const ipv4 = /^\d+\.\d+\.\d+\.\d+$/.test(url.hostname) && parts.every(n => n >= 0 && n <= 255);
    const local = url.hostname === 'localhost' || (ipv4 && (parts[0] === 10 || parts[0] === 127 ||
      (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) || (parts[0] === 192 && parts[1] === 168)));
    if (url.protocol !== 'http:' || !local || !url.port || Number(url.port) < 1024 ||
        url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
      throw Error('Use the LAN address shown in the plugin, for example http://192.168.1.50:6802');
    }
    return url.origin;
  },
  async request(config, download) {
    const result = await this.api(config, download ? '/api/downloads' : '/api/status', download);
    if (download ? typeof result.id !== 'string' : result.app !== 'DeckyDownloader') throw Error('Not a Decky Downloader receiver.');
    return result;
  },
  async api(config, path, data) {
    const response = await this.fetch(config, path, data, AbortSignal.timeout(data instanceof Blob ? 45000 : 15000));
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Receiver rejected the request.');
    return result;
  },
  async fetch(config, path, data, signal) {
    const address = this.address(config?.address || '');
    const password = config?.password ?? config?.token ?? '';
    if (!this.validPassword(password)) throw Error('Enter your receiver password (4-128 characters).');
    if (!/^\/api\/(status|state|job|control|device-torrents|downloads|folders|locations|events|torrents|torrent-files|torrent-selection|torrent-pause)(\?|$)/.test(path)) throw Error('Invalid receiver endpoint.');
    if (path === '/api/downloads' && data) {
      const download = data;
      if (!['file', 'video', 'audio'].includes(download.kind)) throw Error('Invalid download type.');
      const source = new URL(download.source);
      if (!['http:', 'https:', ...(download.kind === 'file' ? ['magnet:'] : [])].includes(source.protocol)) {
        throw Error('Send an HTTP(S) link or a magnet.');
      }
    }
    let response;
    try {
      response = await fetch(address + path, {
        method: data ? 'POST' : 'GET', credentials: 'omit', redirect: 'error',
        headers: { Authorization: 'Basic ' + btoa(String.fromCharCode(...new TextEncoder().encode('downloader:' + password))), ...(data ? { 'Content-Type': data instanceof Blob ? 'application/x-bittorrent' : 'application/json' } : {}) },
        body: data instanceof Blob ? data : data ? JSON.stringify(data) : undefined, signal,
      });
    } catch {
      throw Error('Cannot confirm delivery. Check the device, address, permission and queue before retrying.');
    }
    return response;
  },
  validPassword(value) {
    return typeof value === 'string' && [...value].length >= 4 && [...value].length <= 128 && !!value.trim() && !/[\u0000-\u001f\u007f]/.test(value);
  },
};
