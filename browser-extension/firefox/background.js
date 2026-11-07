'use strict';
function menus() {
  browser.menus.removeAll().then(() => {
    browser.menus.create({ id: 'file', title: 'Send link to Decky Downloader', contexts: ['link'] });
    browser.menus.create({ id: 'video', title: 'Send page as video to Decky Downloader', contexts: ['page', 'video'] });
    browser.menus.create({ id: 'audio', title: 'Send page as audio to Decky Downloader', contexts: ['page', 'audio'] });
  });
}
browser.runtime.onInstalled.addListener(menus);
browser.runtime.onStartup.addListener(menus);
let sending = false;
async function send(download) {
  if (sending) throw Error('A link is already being sent.');
  sending = true;
  try {
    const { connection } = await browser.storage.local.get('connection');
    const result = await DownloaderClient.request(connection, { ...download,
      ...(connection?.directory ? { directory: connection.directory } : {}) });
    await browser.storage.local.set({ lastResult: 'Added to the handheld queue.' });
    await browser.action.setBadgeText({ text: 'OK' });
    await browser.action.setBadgeBackgroundColor({ color: '#25805b' });
    return result;
  } catch (error) {
    await browser.storage.local.set({ lastResult: error.message });
    await browser.action.setBadgeText({ text: '!' });
    await browser.action.setBadgeBackgroundColor({ color: '#b43838' });
    throw error;
  } finally { sending = false; }
}
browser.menus.onClicked.addListener(info => {
  void send({ source: info.menuItemId === 'file' ? info.linkUrl : info.pageUrl,
    kind: info.menuItemId, quality: 'best' }).catch(() => {});
});
browser.runtime.onMessage.addListener((message, sender) => {
  if (sender.id !== browser.runtime.id || message?.type !== 'send') return;
  return send(message.download).then(result => ({ ok: true, result }), error => ({ ok: false, error: error.message }));
});
