'use strict';
const $ = id => document.getElementById(id);
function say(value) { $('result').textContent = value; }
function busy(value) { document.querySelectorAll('button').forEach(button => { if (!button.closest('#destination,#jobs,.job-tools,.torrent-upload,.torrent-picker')) button.disabled = value; }); }
let connection;
$('manager-page').onclick = () => {
  try { void browser.tabs.create({url: DownloaderClient.address(connection?.address || '')}); }
  catch (error) { say(error.message); }
};
const panel = new RemotePanel({ root: $('destination'), jobs: $('jobs'), live: $('live'),
  api: (path, data) => DownloaderClient.api(connection, path, data),
  stream: signal => DownloaderClient.fetch(connection, '/api/events', undefined, signal),
  save: async directory => {
    if (!connection) throw Error('Save and test the connection first.');
    const updated = { ...connection, directory };
    await browser.storage.local.set({ connection: updated }); connection = updated;
  },
});
browser.storage.local.get(['connection', 'lastResult']).then(async saved => {
  connection = saved.connection; const { lastResult } = saved;
  if (connection) {
    $('address').value = connection.address; $('key').value = connection.password ?? connection.token ?? '';
    panel.selected = connection.directory || ''; panel.draw(); panel.start();
  }
  if (lastResult) say(lastResult);
}).catch(error => say(error.message));
browser.action.setBadgeText({ text: '' });
$('connection').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    const candidate = { address: DownloaderClient.address($('address').value.trim()), password: $('key').value };
    if (!DownloaderClient.validPassword(candidate.password)) throw Error('Enter your receiver password (4-128 characters).');
    if (candidate.address === connection?.address) candidate.directory = connection.directory || '';
    // Request only this host, directly inside the user gesture (before any await).
    const permission = browser.permissions.request({ origins: [new URL(candidate.address).origin.replace(/:\d+$/, '') + '/*'] });
    busy(true);
    if (!await permission) throw Error('Permission to contact the handheld was not granted.');
    const snapshot = await DownloaderClient.request(candidate);
    await browser.storage.local.set({ connection: candidate }); connection = candidate;
    panel.selected = connection.directory || ''; panel.folder = null; panel.draw(); panel.render(snapshot); panel.start();
    say('Connected. You can now send a link or use the right-click menu.');
  } catch (error) { say(error.message); } finally { busy(false); }
});
$('download').addEventListener('submit', async event => {
  event.preventDefault();busy(true);
  try {
    const result = await browser.runtime.sendMessage({ type: 'send', download: {
      source: $('source').value.trim(), kind: $('kind').value, quality: $('quality').value,
    } });
    if (!result?.ok) throw Error(result?.error || 'Could not contact the extension background.');
    $('source').value = '';say('Added to the handheld queue.');
  } catch (error) { say(error.message); } finally { busy(false); }
});
$('current').addEventListener('click', async () => {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  $('source').value = tab?.url || ''; $('kind').value = 'video'; $('quality').disabled = false;
});
$('kind').addEventListener('change', () => { $('quality').disabled = $('kind').value !== 'video'; });
$('quality').disabled = true;
$('forget').addEventListener('click', async () => {
  panel.stop(); connection = null; panel.selected = ''; panel.folder = null; panel.draw(); $('jobs').replaceChildren();
  await browser.storage.local.remove(['connection', 'lastResult']);
  const granted = await browser.permissions.getAll();
  if (granted.origins?.length) await browser.permissions.remove({ origins: granted.origins });
  $('address').value = ''; $('key').value = ''; say('Connection and host permissions removed.');
});
window.addEventListener('pagehide', () => panel.stop());
$('open-tab').addEventListener('click', () => browser.tabs.create({ url: browser.runtime.getURL('popup.html') }));
