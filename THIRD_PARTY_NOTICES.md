# Acknowledgements and dependencies

Decky Downloader is an independent controller/touch frontend inspired by
[Varia](https://github.com/giantpinkrobots/varia), by giantpinkrobots and its
contributors. It is not an official Varia release and does not embed or modify
Varia's GTK source code or desktop window. The plugin uses the supplied Varia
icon in `assets/icon.png`; the catalogue cover also references that visual
identity. Varia's name and original artwork remain attributed to its authors.

The plugin installs the official Varia Flatpak from Flathub for the current
user and runs its existing download tools. The Varia application and its
dependencies are distributed separately by their maintainers; they are not
included in this plugin ZIP. Their original licenses continue to apply.

The optional **Update yt-dlp** action downloads the official Linux release
binary directly from yt-dlp's GitHub releases into the plugin settings cache.
The binary is not included in the plugin ZIP. Its bundled-component licenses
are documented upstream in
https://github.com/yt-dlp/yt-dlp/blob/master/THIRD_PARTY_LICENSES.txt.

- Varia: Mozilla Public License 2.0.
  https://github.com/giantpinkrobots/varia/blob/main/LICENSE
- aria2: GNU General Public License, version 2 or later, with upstream's
  OpenSSL linking exception. https://github.com/aria2/aria2/blob/master/COPYING
- yt-dlp: Unlicense; its bundled dependencies have separate terms.
  https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE
- FFmpeg: licenses depend on the build configuration.
  https://ffmpeg.org/legal.html
- Deno and further dependencies: see Varia's own dependency notices.
  https://github.com/giantpinkrobots/varia/tree/main/dependencies_information

The plugin uses the Decky frontend APIs supplied by the loader:

- @decky/api 1.1.2 and @decky/ui 4.10.4, LGPL-2.1, SteamDeckHomebrew.
  Their license is included in `licenses/LGPL-2.1.txt`. The original sources
  are shipped in the pinned npm packages (`src/` and `dist/`); this repository's
  source, lockfile and build scripts allow rebuilding with modified libraries.
  https://github.com/SteamDeckHomebrew/loader-api
  https://github.com/SteamDeckHomebrew/decky-frontend-lib
- React and React DOM 18.3.1, MIT, Meta Platforms, Inc. and affiliates.

The FileExplorer project by 60plus provided the reference behavior for the
modal layout and controller navigation. Plugin code is released under the
MIT license in LICENSE.
