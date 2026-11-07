# Varia and Decky Downloader

Decky Downloader is an independent plugin inspired by
[Varia](https://github.com/giantpinkrobots/varia). It uses Varia's Flatpak runtime
for aria2, yt-dlp, FFmpeg and media dependencies, with its own Steam interface,
settings and download queue. Varia's desktop window does not need to be open.

## Available in the plugin

| Area | Decky Downloader |
| --- | --- |
| Files and torrents | HTTP/HTTPS links, magnets, local torrent files, HTTP torrent links and uploaded torrent files. |
| Video and audio | Video quality selection and MP3 conversion through yt-dlp and FFmpeg. |
| Queue | Pause, resume, retry, cancel, remove, move to front and bulk queue actions. Removing entries keeps downloaded files. |
| Storage | Default and per-download destinations, mounted drives, free-space display and folder creation. |
| Transfer limits | Simultaneous download count and per-transfer download/upload limits. |
| BitTorrent | Listening ports, peer limits, DHT, PEX, local peer discovery, required encryption and optional UPnP. |
| Torrent files and seeding | Individual file selection, optional seeding after completion and a persistent ratio limit. |
| Remote management | A local web page for queue actions and settings, plus a Firefox companion for sending links and managing transfers. |
| Engine updates | Varia installation/update and independent yt-dlp updates, with optional automatic checks. |
| Controls | A Steam modal designed for gamepad, touch, keyboard and mouse, with windowed and full-screen layouts. |

## Differences from the desktop application

Varia's desktop preferences and queue are separate from the plugin. Installing
or updating its runtime does not automatically add desktop features to
Decky Downloader. Configure plugin downloads in the plugin or its local web page.

The plugin has one default download destination with per-download overrides.
It does not have a separate default folder for torrents. HTTP connection and
segment counts are configured by the engine integration, without a user-facing
segment-count setting.

Scheduled downloads, automatic shutdown, archive extraction, playlist downloads,
per-download login fields, cookies.txt import and connections to remote aria2
servers are not available. Browser sending transfers links or torrent metadata;
it does not copy browser cookies, login sessions or desktop Varia settings.

Torrents can upload while downloading. Seeding after completion is optional.
Supported torrent formats and other operating limits are described in the
[technical reference](REFERENCE.md#persistence-and-file-behavior).

For setup and usage, see the [README](../README.md). For test coverage and device
checks, see the [testing guide](VALIDATION.md).
