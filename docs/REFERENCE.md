# Setup and technical reference

For the plugin overview and current downloads, see the [README](../README.md).

## Installation

Use this repository's `main` branch or a release tag for SPlug source builds.
The [README](../README.md#get-started) links to the source repository and latest downloads.

For a SPlug source build, use this repository's `main` branch (or an immutable
commit), install dependencies with the committed `pnpm-lock.yaml`, and run
`pnpm run build`. This is a standard Decky source
repository: no prebuilt `dist/` or download engines are committed.

The build stages the complete Python package, child supervisor and license
notices under `defaults/`. The Decky/SPlug packager must flatten `defaults/`
into the archive's plugin root. The build itself
only needs Node and pnpm; it does not install Varia on the build server.

Alternatively, download the plugin ZIP using the [latest release link in the README](../README.md)
and use your loader's local ZIP installer.
The archive contains one `DeckyDownloader/` directory with `plugin.json`,
`package.json`, `main.py`, `downloader/` and `dist/index.js`.

On the first backend start, the plugin automatically installs the official
**Varia Flatpak** for the current user if it is not already installed. This
provides aria2, yt-dlp, FFmpeg and Varia's other media dependencies. Installation
needs internet access, free storage and Flatpak (normally present on SteamOS).
Progress state and installation errors are available in Settings. An interrupted
installation can be retried with **Install / update Varia**.

The plugin does not disable SteamOS read-only mode, use `sudo`, or install system
packages. Varia is a separately maintained application; updating it through
Discover/Flatpak updates its engines. Uninstalling the plugin leaves Varia and
your downloaded files in place. Native aria2/yt-dlp installations can also serve
as a fallback, but first-start setup still installs the complete Varia runtime
when Flatpak is available.

## Package metadata and artwork

[`plugin.json`](../plugin.json) defines the loader identity and author.
[`splug.json`](../splug.json) provides catalogue descriptions and artwork links.
The [icon](../assets/icon.png), [cover](../assets/cover.png) and
[screenshots](../assets/screenshots/) are included in the source repository.
The build bundles artwork needed by the plugin interface.

## Downloads and controls

- HTTP/HTTPS files, magnet links and local or HTTP-linked `.torrent` files.
- Video via yt-dlp, with best/1080p/720p/480p selection; MP3 audio via FFmpeg.
- Persistent queue, 1-4 simultaneous transfers, per-transfer bandwidth limit,
  pause/resume, retry, cancellation and priority for the next queued item.
- Progress, speed, remaining time, destination and errors in each item's details.
- Large buttons and scrollable lists/forms for touch; Steam's native focus
  controls for a gamepad, keyboard and mouse.

| Control | Action |
| --- | --- |
| D-pad / left stick | Navigate native Steam controls |
| A / confirm | Activate a button or open download details |
| B / back | Return from a page; close from the download list |
| X / secondary | Add download, while viewing the list |
| Y / options | Settings, while viewing the list |
| LB / RB | Previous / next filter, while viewing the list |
| Touch / mouse | All actions have visible buttons |

The built-in folder browser lists Home, Downloads, the internal filesystem and
mounted storage, including SD cards and USB drives. It shows free space and
read-only status; Refresh updates the list after a drive is connected. Mount
unmounted media through SteamOS/Desktop Mode first. The browser does not mount
or format drives. **New folder** opens a name field using Steam's keyboard,
creates the folder and opens it; **Use this folder** confirms the destination.
The same browser selects local `.torrent` files.

Directional navigation follows the actual on-screen positions of controls,
including wrapped button rows and the horizontal filters on small displays.
At an edge, focus stays in place instead of advancing in tab order.

Text fields use Steam's native keyboard. The modal moves above the on-screen
keyboard; the form scrolls independently and its action buttons stay visible.
Automatic layout also fills short/small displays. Settings can explicitly select
Window or Full screen, useful for a docked handheld or unusual screen scaling.

## Settings

Settings has General, BitTorrent, Browser and Download engines tabs. Draft values survive
tab changes; use **Save settings** to persist them. A destination chosen in the
new-download form applies to that download; choose and save a destination in
Settings to change the default for future downloads.

### Send downloads from a PC or phone

In **Settings > Browser**, enter your own **Receiver password** (4-128 characters)
and press **Save password**. Choose **Home network (LAN)**, keep port **6802** (or
choose another free port), and save settings. Reopen Browser settings to see the
running receiver and its addresses. Open a displayed LAN address, for example
`http://192.168.1.50:6802`, in your PC/phone browser and enter the same password.
Send an HTTP(S) or magnet link; choose Video or Audio for a media page. The page
also shows progress, transfer speed and destinations live, without Refresh.

Downloads enter the same queue as locally added jobs. **Choose folder / drive**
browses folders on the receiving device, including mounted SD/USB storage. You
can create a folder and confirm it with **Use this folder**. The web page remembers
the choice for its tab; Firefox remembers it for that receiver, including links
sent from the context menu. **Use plugin default** resets the override. Selection
does not change the plugin's global default. Missing or read-only destinations
report an error; mounted drives must already be accessible on the handheld.

Keep the receiving device awake with SPlug/Decky Loader
running. Closing the plugin modal does not stop the receiver. Disabling it or
unloading the plugin closes its listener. **This device only** binds to loopback;
**Home network** listens on IPv4 and accepts only RFC1918/loopback clients. The
receiver is **off by default**. Its port is separate from torrent listening ports.
If startup fails because a port is occupied, Settings shows the error; choose a
free port and save. No firewall or router rules are changed. An existing firewall
may need to allow the chosen TCP port from the home network.

The web page is ready without a browser add-on. The optional [Firefox
companion](../browser-extension/README.md) adds a right-click **Send link to Decky
Downloader** action and sending the current page as video/audio. Its development
ZIP is unsigned; normal Firefox installation requires Mozilla signing.

Download the unsigned Firefox companion using the link in its
[setup guide](../browser-extension/README.md). Extract it, open
`about:debugging#/runtime/this-firefox`, choose **Load Temporary
Add-on** and select `manifest.json`. Requires Firefox 142 or newer; temporary
installation lasts until Firefox restarts. See the [setup instructions](../browser-extension/README.md)
for entering the receiver address/password and sending links.

The receiver stores a salted PBKDF2 password hash; neither the password nor its
hash is returned in plugin state or the public web page. **Save password** replaces
it immediately and revokes previous access. Ten incorrect attempts from one
client within a minute temporarily block further attempts. There is no default
password; set one before enabling a new receiver. Legacy access-key pairings
migrate to hashed storage and keep working until you choose your own password.

The web page remembers the password for the current tab session; the companion
keeps it in the local Firefox profile. HTTP is unencrypted: use only a trusted
home network, without forwarding this port to the internet. No cloud account is
required. Browser cookies and login sessions are not transferred. The web page
and Firefox companion can upload a local v1/hybrid `.torrent` file up to 20 MiB.
Binary metainfo is validated before queueing, stored under a
hash-derived filename in the plugin's private upload cache, and never treated
as a client-supplied server path. Duplicate active uploads are rejected. Removing
the last referencing queue entry removes its uploaded metainfo, preserving
downloaded files.

Both clients can list torrent contents, select individual files and start the
download. Selections survive paging and SSE refreshes. Active torrents can be
paused remotely before changing files. Keep the page/popup open until an upload
is acknowledged; the Firefox companion also provides **Open in a tab**.

The authenticated API uses
`Authorization: Basic <base64 of downloader:password in UTF-8>`:

- `GET /api/status`: queue snapshot and default destination.
- API version 4 includes the full queue (up to the service's 1000-entry limit),
  free space and transfer progress. Clients display 50 entries per page.
- `GET /api/state`: settings, runtime, installation and receiver status, without
  queue sources or credentials. The web settings panel polls it every five seconds
  without replacing unsaved form values.
- `GET /api/job?job_id=...`: one download's details, including its source.
- `POST /api/control`: JSON `method` and `args`, using an explicit allowlist:
  `action` (`job_id`, `action`), `pause_all`, `resume_all`, `resume_interrupted`,
  `clear_completed`, `settings` (`changes`), `receiver_password` (`password`),
  `install_runtime` and `update_video_engine`. No-argument commands require `{}`.
  Actions use the same service validation as the plugin; downloaded files are
  preserved on removal. Receiver changes can disconnect clients. Turning it off
  requires re-enabling it in the plugin; switching to local mode prevents LAN use.
- `GET /api/device-torrents?path=...&offset=0`: folders and `.torrent` filenames
  on the handheld. `device_torrent` through `/api/control` accepts `source` and
  `directory` (null for the default), reads at most 20 MiB plus one byte, validates
  metainfo and imports it through the same upload cache. It returns a job ID,
  never raw local file contents.
- `GET /api/events`: live Server-Sent Events (SSE), updated once per second.
  The web page and Firefox popup reconnect automatically. Closing the page/popup,
  changing the password or stopping the receiver closes its live session.
- `GET /api/locations`: mounted drives and standard locations.
- `GET /api/folders?path=...&offset=0`: paged directory-only listing. Omit `path`
  to open the default folder or its nearest existing parent.
- `POST /api/folders`: create one folder with JSON `parent` and `name`.
- `POST /api/downloads`: JSON `source`, optional `kind` (`file`, `video`, `audio`),
  `quality` (`best`, `1080`, `720`, `480`) and existing writable `directory`.
- `POST /api/torrents?directory=...`: binary `application/x-bittorrent` body,
  with an optional URL-encoded existing writable destination. Returns a job ID.
- `GET /api/torrent-files?job_id=...`: validated catalogue, saved selection,
  name, status and whether selection is currently editable.
- `POST /api/torrent-selection`: JSON `job_id` and nonempty unique `indices`;
  persists selection and queues the torrent. Running/stale selections are rejected.
- `POST /api/torrent-pause`: JSON `job_id`; pauses a torrent so its files can be changed.

All management commands require the receiver password and pass the same host
and origin checks as queue submissions. The API does not provide general file
reads or engine RPC. A `201` response
means accepted into the queue, not completed. On a timeout check the queue before
retrying. JSON requests are limited to 32 KiB (128 KiB for selection of up to
10000 files), binary torrent uploads to 20 MiB, and the server to eight connections
(at most four live streams, leaving command capacity) and 60 accepted links/uploads
per minute. Only numeric local IPv4 hosts/localhost and same-origin or Firefox
extension origins are allowed; arbitrary websites cannot submit browser requests.

### BitTorrent

BitTorrent settings include:

- TCP and DHT/UDP listening port or range (1024-65535); default 49152-65535.
- Upload speed per torrent and maximum peers (0 means unlimited).
- DHT and PEX enabled by default; LAN peer discovery disabled by default.
- Optional required protocol encryption (not an anonymity feature).
- UPnP IPv4 router mapping, **disabled by default**.
- Choose files before downloading, enabled for new transfers by default.
- Optional seeding after completion, off by default, with a ratio limit from
  0.1 to 100 (default 1). Ratio uses persisted uploaded bytes divided by the
  selected files' size. Seed policy changes apply to running seeders.

Local `.torrent` files, HTTP torrent links and magnets are loaded paused before
payload download. The file picker uses aria2's file IDs and stores the choice
with the metadata hash. Metadata is cached in the plugin's task folder so
resuming does not need to fetch the original torrent again. Up to 10000 files
are supported, with 100 entries per UI page. Waiting for selection releases its
worker and port. Existing queue entries migrate with their previous all-files
behavior. HTTP/magnet links and uploaded torrents sent from Firefox or the web
page also wait when the selection preference is enabled. Make that choice in
the plugin, web page or Firefox companion.

At most two additional processes seed alongside the configured download slots.
Seeders yield when a queued aria2 download needs their torrent port, including
with a single configured port. The Seeding view includes these waiting seeders.
Clear completed does not remove seeding or selection-waiting entries. Loader
shutdown pauses seeders; resume them explicitly after restarting.

Changes apply to newly started/resumed transfers. Each aria2 transfer is an
independent process, so a single configured port serializes aria2 downloads;
a range permits concurrent transfers up to its port count and the parallel
setting. HTTP downloads also use aria2 and can follow torrent responses.
Video/audio downloads do not consume these port slots.

When enabled, UPnP discovers a compatible IGD router on the local network and
requests temporary TCP/UDP mappings for active torrents. The plugin uses a
free port from the configured range, renews its one-hour leases and requests
removal when the transfer stops. It checks ownership before replacing/removing
a mapping and never falls back to permanent mappings. Turning UPnP off and
saving also removes current mappings during ongoing downloads. A router or
network failure may prevent immediate cleanup; the lease then expires.
Mapping failure is shown in BitTorrent settings and does not stop the download.
Routers requiring permanent mappings or unsupported services report failure.
No firewall rules are changed; manual forwarding remains available.

Port and encryption semantics follow the [aria2 manual](https://aria2.github.io/manual/en/html/aria2c.html#bittorrent-metalink-options).
Router leases use the [UPnP IGD WANIPConnection protocol](https://upnp.org/specs/gw/UPnP-gw-WANIPConnection-v2-Service.pdf).

## Updating the video engine

**Settings > Download engines > Update yt-dlp** downloads the latest official
stable release from `yt-dlp/yt-dlp` on GitHub. Linux x86_64 and aarch64 are
supported. The updater bounds download sizes, restricts redirects to GitHub's
release hosts, verifies the published SHA-256 and probes `--version` before
atomically selecting the new engine. It never installs into `/app` or the OS.

Executables are stored under the plugin settings directory in
`video-engine/<version>/yt-dlp`, with `video-engine/current.json` selecting the
active version. Older version directories are retained so running transfers
can finish; new/resumed transfers use the selected version. A failed update
keeps the previous selection.

**Automatic yt-dlp updates** is an opt-in setting, off by default. Save settings
to enable it. The queue scheduler starts a separate update worker when a check
is due, without stopping downloads. Successful checks are spaced 24 hours apart;
failures retry after one hour. The next deadline is atomically persisted in
`video-engine/auto-check.json` before work starts, preventing repeat checks on
loader restarts. Invalid timing data is treated as due; future timestamps are
bounded on startup to handle clock corrections. Initial Varia setup takes
priority, as do already running installations.

Automatic checks compare the installed version with the official stable release
and skip binary downloads when the current version is equal or newer. Manual
updates bypass the deadline and perform checksum verification and probing even
for the same version. Disabling automatic updates stops future checks; a worker
already started may finish. Checks run only while the plugin is loaded and the
device is awake.

When Varia is installed, the executable runs inside its Flatpak with a temporary
filesystem grant to the engine directory and download/task directories. FFmpeg
and Deno remain supplied by Varia. Native installations use the managed
executable with native dependencies. The settings page shows the selected
yt-dlp version; Varia and video-engine updates cannot run concurrently.

An HTTP 403 is a server refusal, not the outdated-version warning itself.
Updating yt-dlp can fix outdated YouTube extraction, but some sources still
require authentication or impose connection/account restrictions. The plugin
does not automatically transfer browser cookies or attempt repeated bypasses.

## Persistence and file behavior

Closing the modal or returning to a game leaves transfers running in the plugin
backend. Unloading/restarting the loader pauses transfers. After a restart,
resume them explicitly from the list. Downloads cannot continue while the device
is asleep or powered off.

Each transfer uses its own named subfolder under the selected destination.
This avoids collisions between equal filenames and preserves resume data.
Cancellation and removing an entry **never delete downloaded files**. Removing
an entry removes its resume control from the plugin; manage the retained files
with FileExplorer or a desktop file manager.

HTTP resume depends on server support. Video resume depends on the source and
format; media processing can restart when resumed. Torrents upload while
downloading; post-download seeding is optional. Unselected torrent files can
contain partial shared pieces; the plugin does not delete them. BitTorrent
v1/hybrid magnets are supported; pure v2 magnets are not supported by aria2.
Playlist downloads, browser interception, remote aria2 servers and Varia's
scheduler/shutdown features are not available in the plugin.

The queue and settings use SQLite in the loader-provided plugin settings folder.
URLs can contain private tokens, so these files are private to the user's account.
aria2 control connections bind to loopback and use a random per-process secret.

## Build and validation

Requires Node, pnpm and Python 3.10+:

```sh
pnpm install --frozen-lockfile
pnpm typecheck
pnpm build
python3 -m unittest discover -s tests -v
python3 scripts/package.py
```

Real integration tests need `aria2c`, `yt-dlp` and `ffmpeg` on PATH. Tests use a
local HTTP server, generated media, and a local torrent seed/tracker. They do
not download someone else's media. Without these tools, the corresponding
integration tests are explicitly skipped.

See the [testing guide](VALIDATION.md) for browser checks, test dependencies
and checks to perform in Steam on a physical device.

Runtime design references: [Varia's Flatpak manifest](https://github.com/giantpinkrobots/varia/blob/main/io.github.giantpinkrobots.varia.json),
[aria2 manual](https://aria2.github.io/manual/en/html/aria2c.html),
[yt-dlp CLI](https://github.com/yt-dlp/yt-dlp#usage-and-options).
