# Testing

This guide describes how to build and test Decky Downloader. Test results depend
on the checked-out source, installed dependencies and environment.

## Build and package

Use Node, pnpm and Python 3.10 or newer. Run these commands from the repository root:

```sh
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm run build
python3 scripts/package.py
python3 scripts/package-extension.py
```

The build creates the frontend and stages the backend for loader packaging.
The packaging scripts write the plugin ZIP, its SHA-256 checksum and the unsigned
Firefox companion ZIP to `out/`. Package versions come from their manifests.

## Backend tests

Run the backend suite on Linux:

```sh
python3 -m unittest discover -s tests -v
```

Engine integration tests require `aria2c`, `yt-dlp` and `ffmpeg` on PATH.
Missing engines cause the corresponding integration tests to be skipped, so
review the skipped-test summary as well as the exit status. Process supervision
checks require Linux.

| Area | Coverage |
| --- | --- |
| Queue and storage | Input validation, isolated destinations, persistence, pause/resume, retry, cancellation, removal and preserving downloaded files. |
| Engine integration | Local HTTP transfers and resume, generated video/audio, torrent metadata, selected files and ratio-limited seeding. |
| Local web API | Authentication, origin checks, queue actions, settings, password changes, receiver lifecycle, folder selection and torrent imports. |
| Video engine updates | Release validation, checksums, activation failures, cancellation, persisted update schedules and retries. |
| Networking and folders | Port allocation, simulated UPnP responses, mounted-location parsing, folder creation and invalid paths. |

Integration tests use local servers, generated content and a local torrent
tracker/seed. They do not depend on downloading a particular public video.
Updater unit tests replace external release responses with controlled fixtures.

## Browser tests

The browser harness uses adapter components for Steam controls. Generate its
preview before running the Steam-interface checks:

```sh
node scripts/preview.mjs
node scripts/ui-test.mjs
node scripts/torrent-ui-test.mjs
```

Playwright is included in the development dependencies. These tests also need
a browser available to Playwright. `CHROME_CHANNEL` selects an installed browser channel.
The general UI script defaults to Playwright Chromium; the torrent and receiver
scripts default to installed Microsoft Edge. The general UI script also accepts
`PLAYWRIGHT_MODULE` when using a separately installed Playwright package.

On Linux, run the receiver tests with the Python interpreter explicitly selected:

```sh
PYTHON=python3 node scripts/receiver-browser-test.mjs
```

The receiver harness starts a temporary local HTTP server and exercises the
actual web page and shared Firefox companion code. It covers live updates,
queue controls, settings drafts, password changes, folder selection, torrent
uploads and file selection. Firefox APIs and torrent metadata generation are
adapted for the test. Real payload transfers are covered by the Linux engine tests.

The scripts produce local screenshots and previews for inspection. Generated
output and temporary test data are not part of the source distribution.

## Checks in Steam

Automated browser checks do not reproduce Steam's focus engine or a physical
controller. When checking a release on SteamOS:

1. Install through the loader and verify first-start Varia setup, including
   video/audio dependencies and error reporting.
2. Check the window on a PC and full-screen layout on a handheld. Navigate with
   the D-pad, stick, keyboard and touch, including long settings forms.
3. Enter a link with Steam's keyboard, choose internal or mounted removable
   storage, create a folder and complete a download through Varia's Flatpak.
4. Close and reopen the modal during a transfer. Restart the loader and resume
   interrupted downloads without losing their destination or torrent selection.
5. Connect from another device on the LAN. Check queue actions, settings,
   torrent uploads and reconnecting after receiver changes.
6. Load the Firefox companion in Firefox and check permissions, its popup and
   context-menu actions. A browser API adapter is not an installed-extension test.

UPnP fixtures do not establish compatibility with every physical router.
Native Linux engine tests do not establish Varia Flatpak or ARM device behavior.
Report those environments separately when sharing test results.

## Reporting a problem

Include the plugin and loader versions, operating system, steps to reproduce,
expected behavior and relevant error text. Remove passwords, access tokens,
private download URLs and personal paths from logs and screenshots before sharing.
