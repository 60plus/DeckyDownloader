// Decky/SPlug's source builder flattens defaults/ into the plugin package.
// Python packages outside defaults/ would otherwise be omitted by Decky CLI.
import { cpSync, lstatSync, mkdirSync, readdirSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const defaults = join(root, 'defaults');
const required = ['main.py', 'plugin.json', 'package.json', 'LICENSE', 'README.md',
  'downloader/__init__.py', 'downloader/store.py', 'downloader/runtime.py',
  'downloader/service.py', 'downloader/engines.py', 'downloader/child.py', 'downloader/folders.py', 'downloader/ports.py', 'downloader/upnp.py',
  'downloader/receiver.py', 'downloader/receiver_web.py', 'downloader/remote.js', 'downloader/manager.js', 'downloader/torrent.py', 'downloader/video_update.py',
  'THIRD_PARTY_NOTICES.md', 'licenses/LGPL-2.1.txt'];
for (const name of required) {
  const info = lstatSync(join(root, name), { throwIfNoEntry: false });
  if (!info?.isFile() || info.isSymbolicLink()) throw new Error(`Missing or unsafe required source: ${name}`);
}
const old = lstatSync(defaults, { throwIfNoEntry: false });
if (old && (!old.isDirectory() || old.isSymbolicLink())) throw new Error('defaults must be a real generated directory');
// Absolute target is the fixed defaults/ child of this repository, never a
// command-line path. Reject links before removing the generated tree.
function checkTree(folder) {
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const path = join(folder, entry.name);
    if (lstatSync(path).isSymbolicLink()) throw new Error(`Unexpected symlink: ${path}`);
    if (entry.isDirectory()) checkTree(path);
  }
}
if (old) checkTree(defaults);
rmSync(defaults, { recursive: true, force: true });
mkdirSync(join(defaults, 'downloader'), { recursive: true });
mkdirSync(join(defaults, 'licenses'), { recursive: true });
for (const entry of readdirSync(join(root, 'downloader'), { withFileTypes: true })) {
  if (entry.isSymbolicLink()) throw new Error(`Unexpected backend symlink: ${entry.name}`);
  if (!entry.isFile() || !/\.(py|js)$/.test(entry.name)) continue;
  cpSync(join(root, 'downloader', entry.name), join(defaults, 'downloader', entry.name));
}
for (const name of ['THIRD_PARTY_NOTICES.md', 'licenses/LGPL-2.1.txt']) cpSync(join(root, name), join(defaults, name));
console.log('Staged Python backend, child supervisor and dependency license notices in defaults/.');
