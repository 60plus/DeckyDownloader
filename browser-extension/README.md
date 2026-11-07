# Decky Downloader Sender for Firefox

Sends links and `.torrent` files to the **Decky Downloader plugin** on another device in your home
network. This is a separate companion, not Varia Integrator and not an aria2 RPC
client. It does not use a cloud service or intercept/cancel browser downloads.

**[Get the latest Firefox companion](https://github.com/60plus/DeckyDownloader/releases/latest)**.
On the release page, download the unsigned ZIP with `sender` in its name.
Extract it and load its `manifest.json` temporarily as described below. The web
page in the plugin remains available without installing this companion.

1. In the plugin, open **Settings > Browser**, enter your own password
   (4-128 characters), and press **Save password**. Choose **Home network (LAN)**
   and save settings. Reopen Browser settings to read the receiver address.
2. Install the companion, open its toolbar popup and enter that address and your password.
   **Save and test connection** asks for permission to contact that host only.
3. Right-click a file or magnet link and choose **Send link to Decky Downloader**.
   For video/audio, use the page context menu or **Use current page as video**.
   **Choose folder / drive** opens the handheld's folders and mounted storage.
   Create a folder if needed, then **Use this folder**. The choice is saved for
   this receiver and also applies to the right-click menu. **Use plugin default**
   restores the default; switching receiver addresses clears the old override.
4. The toolbar badge shows `OK` or `!`. Open the popup to read the result. An
   acknowledgement means queued, not finished. The popup and web page display
   progress and speed live while open, using an authenticated SSE connection.

Downloads use the selected folder or the plugin's default. The receiver must be awake with the
loader running. Links that require cookies/login are not supported by this
companion; cookies are never read or transferred. The password is saved only in
the Firefox profile's local extension storage, not sync storage. **Forget
connection** removes it and revokes granted host permissions.

## Send a torrent from your PC

Choose **Torrent file from this computer**, select a `.torrent` file and press
**Send torrent file**. It uses your selected destination on the handheld.
Uploads support v1/hybrid torrents up to 20 MiB. Keep the popup open until it
confirms receipt, or use **Open in a tab** for a larger, persistent workspace.

When metadata is ready, choose files here and press **Download selected**.
For a torrent link or magnet, press **Choose torrent files** beside its queue
entry. **Select all**, **Clear selection** and pages of 100 entries help with
large torrents. Selections stay checked across pages and live progress updates.
**Pause and choose files** lets you change an active torrent's selection.
There is no need to open the plugin on the receiving device.

## Manage downloads

The companion supports pause, resume/retry, cancel, remove,
move-to-front and bulk queue actions. Removal keeps downloaded files. Filters
and pagination include the entire queue, and **Choose torrent on handheld**
imports metainfo already stored on the receiving device.

Use **Open full manager and settings** for the local page's General, BitTorrent,
Browser and Download engines settings. Enter the same password on that page;
the companion does not put it in the URL.

The plugin's **Choose files before downloading** setting controls whether new
torrents wait for a choice; it is enabled by default. If it is disabled, new
torrents start with all files. The live view also shows seeding speed and ratio.
Keep both the plugin and companion up to date to use all available features.

## Build and test

Run `python scripts/package-extension.py`. The output in `out/` is an **unsigned
development ZIP**, not a signed Firefox release. In Firefox, open
`about:debugging#/runtime/this-firefox`, choose **Load Temporary Add-on**, and select
the `manifest.json` from the extracted ZIP. Packaging includes the shared remote
UI from `downloader/remote.js`. Temporary installation lasts until
Firefox restarts. Firefox 142 or newer is required.

Normal permanent installation requires Mozilla signing, including for unlisted
distribution: https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/
No Mozilla submission is performed by this repository's build scripts.

The manifest's `data_collection_permissions` declares `none`: no telemetry or
developer collection. User-requested URLs and selected torrent files go only to the receiver address the
user configured; HTTP is unencrypted and intended for a trusted LAN.

The optional host pattern allows requesting a host entered during setup. The
popup requests only that host, and the client further restricts destinations to
IPv4 RFC1918/loopback or localhost, HTTP, and an explicit unprivileged port.
