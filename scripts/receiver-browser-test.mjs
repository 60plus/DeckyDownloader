import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { chromium } from 'playwright';

const fixture = spawn(process.env.PYTHON || 'python', ['tests/receiver_fixture.py'], { stdio: ['pipe', 'pipe', 'inherit'], windowsHide: true });
const lines = createInterface({ input: fixture.stdout });
let browser;
try {
  const access = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('HTTP fixture did not start')), 15000);
    lines.once('line', line => { clearTimeout(timer); resolve(JSON.parse(line)); });
    fixture.once('exit', code => { clearTimeout(timer); reject(Error('Fixture exited: ' + code)); });
  });
  const address = `http://127.0.0.1:${access.port}`;
  const client = { URL, fetch, AbortSignal, btoa, TextEncoder, Blob };
  vm.createContext(client);
  vm.runInContext(await fs.readFile('browser-extension/firefox/client.js', 'utf8'), client);
  for (const rejected of ['http://8.8.8.8:6802', 'http://example.org:6802', 'http://127.0.0.1:80', 'http://user:pass@192.168.1.2:6802', 'http://192.168.1.2:6802/path']) {
    assert.throws(() => client.DownloaderClient.address(rejected));
  }
  const config = { address, password: access.password };
  assert.equal((await client.DownloaderClient.request(config)).app, 'DeckyDownloader');
  await assert.rejects(client.DownloaderClient.request({ address, password: 'wrong' }));
  const accepted = await client.DownloaderClient.request(config, { source: 'https://example.org/from-addon.zip', kind: 'file', quality: 'best' });
  assert.equal(accepted.status, 'queued');
  browser = await chromium.launch({ headless: true, channel: process.env.CHROME_CHANNEL || 'msedge' });
  await fs.mkdir('.work/screenshots', { recursive: true });
  async function manageQueue(page, suffix) {
    const name = `managed-${suffix}.bin`;
    await client.DownloaderClient.request(config, {source:'https://example.org/' + name,kind:'file'});
    const row = page.locator('#jobs li').filter({has:page.getByText(name, {exact:true})});
    await row.getByRole('button', {name:'Move to front',exact:true}).click();
    await row.getByRole('button', {name:'Pause',exact:true}).click();
    await row.getByRole('button', {name:'Resume',exact:true}).waitFor();
    await row.getByRole('button', {name:'Resume',exact:true}).click();
    await row.getByRole('button', {name:'Cancel download',exact:true}).click();
    await page.getByRole('button', {name:'Keep download',exact:true}).click();
    await row.getByRole('button', {name:'Cancel download',exact:true}).click();
    await page.getByRole('button', {name:'Confirm',exact:true}).click();
    await row.getByRole('button', {name:'Remove',exact:true}).waitFor();
    await row.locator('summary').click();
    await row.locator('details p').filter({hasText:'https://example.org/' + name}).waitFor();
    const remove = row.getByRole('button', {name:'Remove',exact:true});
    await remove.focus(); await page.waitForTimeout(1200);
    assert.ok(await remove.evaluate(el=>el===document.activeElement), 'SSE lost action focus');
    if (suffix.includes('390')) await remove.tap(); else await remove.click();
    await page.getByRole('button', {name:'Confirm',exact:true}).click();
    await row.waitFor({state:'detached'});
    assert.ok(!(await client.DownloaderClient.request(config)).jobs.some(j=>j.name===name));
  }
  async function settingsFlow(page, width) {
    await page.getByRole('button', {name:'Settings',exact:true}).click();
    const manager = page.locator('#manager');
    await manager.getByLabel('Simultaneous downloads', {exact:true}).fill('3');
    await manager.getByRole('tab', {name:'BitTorrent',exact:true}).click();
    await manager.getByLabel('Stop seeding at ratio', {exact:true}).fill('2.5');
    await manager.getByLabel('Seed after download', {exact:true}).check();
    await manager.getByRole('tab', {name:'Download engines',exact:true}).click();
    const auto = manager.getByLabel('Automatic yt-dlp updates', {exact:true}); await auto.check();
    await auto.focus(); await page.waitForTimeout(5200);
    assert.ok(await auto.isChecked()); assert.ok(await auto.evaluate(el=>el===document.activeElement));
    await manager.getByRole('button', {name:'Save settings',exact:true}).click();
    await manager.getByText('Settings saved.', {exact:true}).waitFor();
    const state = await client.DownloaderClient.api(config, '/api/state');
    assert.equal(state.settings.parallel, 3); assert.equal(state.settings.bt_seed_ratio, 2.5); assert.equal(state.settings.video_auto_update, true);
    await manager.screenshot({path:`.work/screenshots/manager-engines-${width}.png`});
    if (width === 1280) {
      await manager.getByRole('tab', {name:'Browser',exact:true}).click();
      await manager.getByLabel('New receiver password', {exact:true}).fill('changed-pass');
      await manager.getByRole('button', {name:'Change password',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('#key').value==='changed-pass');
      await assert.rejects(client.DownloaderClient.request(config));
      await manager.getByLabel('New receiver password', {exact:true}).fill(config.password);
      await manager.getByRole('button', {name:'Change password',exact:true}).click();
      await page.waitForFunction(password=>document.querySelector('#key').value===password, config.password);
    }
    await manager.getByRole('tab', {name:'General',exact:true}).click();
    await manager.getByRole('button', {name:'Choose folder / drive for defaults',exact:true}).click();
    await manager.getByLabel('Settings new folder name', {exact:true}).fill('Default ' + width);
    await manager.getByRole('button', {name:'Create folder',exact:true}).click();
    await manager.locator('.folder-picker > p').filter({hasText:'Default ' + width}).waitFor();
    await manager.getByRole('button', {name:'Use as default folder',exact:true}).click();
    await manager.getByRole('button', {name:'Save settings',exact:true}).click();
    await page.waitForFunction(async ({address,password,width})=>{
      const r=await fetch(address+'/api/state',{headers:{Authorization:'Basic '+btoa('downloader:'+password)}});
      return (await r.json()).settings.directory.endsWith('Default '+width);
    }, {...config,width});
    await manager.getByLabel('Simultaneous downloads', {exact:true}).fill('4');
    await manager.getByRole('button', {name:'Discard changes and close',exact:true}).click();
    assert.equal((await client.DownloaderClient.api(config,'/api/state')).settings.parallel,3);
  }
  async function torrentFlow(page, suffix, destination) {
    const name = `remote-${suffix}.bin`;
    const buffer = Buffer.from(`d4:infod6:lengthi3e4:name${name.length}:${name}12:piece lengthi4e6:pieces20:${'x'.repeat(20)}ee`);
    await page.getByLabel('Torrent file from this computer', { exact: true }).setInputFiles({ name: 'example.torrent', mimeType: 'application/x-bittorrent', buffer });
    await page.getByRole('button', { name: 'Send torrent file', exact: true }).click();
    await page.locator('.torrent-picker h3').filter({ hasText: 'Choose torrent files' }).waitFor();
    assert.equal(await page.locator('.torrent-files input').count(), 100);
    await page.getByRole('button', { name: 'Clear selection', exact: true }).click();
    assert.ok(await page.getByRole('button', { name: 'Download selected', exact: true }).isDisabled());
    const first = page.getByRole('checkbox', { name: /^file-1\.bin/ });
    await first.focus(); await page.keyboard.press('Space');
    await page.getByRole('button', { name: 'Next files', exact: true }).click();
    const later = page.getByRole('checkbox', { name: /^file-101\.bin/ });
    if (suffix === 'web-390') await later.locator('..').tap(); else await later.check();
    await page.getByRole('button', { name: 'Previous files', exact: true }).click();
    assert.ok(await first.isChecked());
    await first.focus();
    await page.waitForTimeout(1200); // An SSE update must not reset the draft or focus.
    assert.ok(await first.isChecked());
    assert.ok(await first.evaluate(el => document.activeElement === el));
    await page.getByRole('button', { name: 'Download selected', exact: true }).click();
    await page.locator('.torrent-picker h3').waitFor({ state: 'detached' });
    const snapshot = await client.DownloaderClient.request(config);
    const job = snapshot.jobs.find(job => job.name === name);
    assert.ok(job.directory.includes(destination)); assert.equal(job.status, 'queued');
    const saved = await client.DownloaderClient.api(config, '/api/torrent-files?job_id=' + job.id);
    assert.deepEqual(saved.selection, [1, 101]);
    const row = page.locator('#jobs li').filter({ has: page.getByText(name, { exact: true }) });
    await row.getByRole('button', { name: 'Pause and choose files', exact: true }).click();
    await page.locator('.torrent-picker h3').waitFor();
    assert.ok(await page.getByRole('checkbox', { name: /^file-1\.bin/ }).isChecked());
    assert.ok(!await page.getByRole('checkbox', { name: /^file-2\.bin/ }).isChecked());
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.screenshot({ path: `.work/screenshots/remote-torrent-${suffix}.png`, fullPage: true });
    await page.getByRole('button', { name: 'Close file selection', exact: true }).click();
    await page.getByLabel('Torrent file from this computer', { exact: true }).setInputFiles({ name: 'bad.torrent', mimeType: 'application/x-bittorrent', buffer: Buffer.from('<html>bad</html>') });
    await page.getByRole('button', { name: 'Send torrent file', exact: true }).click();
    await page.locator('.torrent-upload [role=status]').filter({ hasText: /valid .torrent/ }).waitFor();
    // HTTP .torrent links use the same remote picker without uploading a file.
    const source = `https://example.org/link-${suffix}.torrent`;
    await client.DownloaderClient.request(config, { source, kind: 'file' });
    const linked = page.locator('#jobs li').filter({ has: page.getByText(`link-${suffix}.torrent`, { exact: true }) });
    await linked.getByRole('button', { name: 'Choose torrent files', exact: true }).click();
    await page.locator('.torrent-picker h3').waitFor();
    await page.getByRole('button', { name: 'Clear selection', exact: true }).click();
    await page.getByRole('checkbox', { name: /^file-2\.bin/ }).check();
    await page.getByRole('button', { name: 'Download selected', exact: true }).click();
    await page.locator('.torrent-picker h3').waitFor({ state: 'detached' });
    const linkJob = (await client.DownloaderClient.request(config)).jobs.find(job => job.name === `link-${suffix}.torrent`);
    assert.deepEqual((await client.DownloaderClient.api(config, '/api/torrent-files?job_id=' + linkJob.id)).selection, [2]);
  }
  for (const width of [1280, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 850 }, hasTouch: width === 390, locale: 'en-US' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let streamConnections = 0;
    await page.route(address + '/api/events', async route => {
      streamConnections++;
      if (streamConnections === 1) {
        // End the first SSE session early; the UI must reconnect by itself.
        const snapshot = await client.DownloaderClient.request(config);
        await route.fulfill({ contentType: 'text/event-stream', body: 'data: ' + JSON.stringify(snapshot) + '\n\n' });
      } else await route.continue();
    });
    await page.goto(address);
    await page.getByLabel('Password', { exact: true }).fill(access.password);
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await page.getByText('Connected to Decky Downloader.', { exact: true }).waitFor();
    await page.getByText('Live · updates automatically', { exact: true }).waitFor();
    if (width === 1280) {
      await page.getByLabel('Filter downloads', {exact:true}).selectOption('complete');
      await page.getByRole('button', {name:'Next downloads',exact:true}).click();
      await page.getByText('history-54.bin', {exact:true}).waitFor();
      await page.getByRole('button', {name:'Clear completed',exact:true}).click();
      await page.getByRole('button', {name:'Confirm',exact:true}).click();
      await page.getByText('No downloads here.', {exact:true}).waitFor();
      assert.ok(!(await client.DownloaderClient.request(config)).jobs.some(j=>j.status==='complete'));
      await page.getByLabel('Filter downloads', {exact:true}).selectOption('all');
    }
    await page.getByRole('button', { name: 'Choose folder / drive', exact: true }).click();
    await page.getByLabel('Mounted drives and locations').waitFor();
    await page.getByLabel('New folder name').fill(`Browser folder ${width}`);
    await page.getByRole('button', { name: 'Create folder', exact: true }).click();
    await page.locator('.folder-picker > p').filter({ hasText: `Browser folder ${width}` }).waitFor();
    await page.getByRole('button', { name: 'Use this folder', exact: true }).click();
    await page.locator('#destination > p').filter({ hasText: `Browser folder ${width}` }).waitFor();
    await page.getByLabel('Download link', { exact: true }).fill(`https://example.org/web-${width}.zip`);
    await page.getByRole('button', { name: 'Add to queue', exact: true }).click();
    await page.getByText('Added to the handheld queue.', { exact: true }).waitFor();
    await page.getByText(`web-${width}.zip`, { exact: true }).waitFor();
    const snapshot = await client.DownloaderClient.request(config);
    assert.ok(snapshot.jobs.find(job => job.name === `web-${width}.zip`).directory.includes(`Browser folder ${width}`));
    // A separate client queues work; no Refresh click or web POST can update this page.
    await client.DownloaderClient.request(config, { source: `https://example.org/live-${width}.zip`, kind: 'file' });
    await page.getByText(`live-${width}.zip`, { exact: true }).waitFor({ timeout: 5000 });
    assert.ok(streamConnections >= 2, 'Live view did not reconnect after the first stream ended');
    await torrentFlow(page, `web-${width}`, `Browser folder ${width}`);
    if (width === 1280) {
      await page.getByRole('button', {name:'Choose torrent on handheld',exact:true}).click();
      await page.getByRole('button', {name:'on-handheld.torrent',exact:true}).click();
      await page.locator('.torrent-picker h3').waitFor();
      await page.getByRole('button', {name:'Download selected',exact:true}).click();
      await page.locator('.torrent-picker h3').waitFor({state:'detached'});
      assert.ok((await client.DownloaderClient.request(config)).jobs.some(j=>j.name==='handheld.bin'));
    }
    await manageQueue(page, 'web-' + width);
    await settingsFlow(page, width);
    await page.getByLabel('Language').selectOption('pl');
    await page.getByRole('button', { name: 'Odśwież', exact: true }).click();
    await page.getByText('W kolejce', { exact: true }).first().waitFor();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    assert.equal(await page.locator('button:visible').evaluateAll(buttons => buttons.filter(b => b.getBoundingClientRect().height < 44).length), 0);
    await page.screenshot({ path: `.work/screenshots/receiver-${width}.png`, fullPage: true });
    await page.reload();
    assert.equal(await page.getByLabel('Password', { exact: true }).inputValue(), access.password);
    await page.getByRole('button', { name: 'Forget password', exact: true }).click();
    assert.equal(await page.getByLabel('Password', { exact: true }).inputValue(), '');
    assert.equal(errors.length, 0, errors.join('\n'));
    await page.close();
  }
  // Run the actual popup and background source with a minimal Firefox API
  // adapter. Networking is real; this is not an installed Firefox add-on test.
  const popup = await browser.newPage({ viewport: { width: 380, height: 950 } });
  const popupErrors = [];
  popup.on('pageerror', error => popupErrors.push(error.message));
  await popup.addInitScript(config => {
    const storage = { connection: config }; let handler;
    const noop = async () => {};
    globalThis.browser = {
      storage: { local: { get: async () => ({ ...storage }), set: async values => Object.assign(storage, values), remove: async keys => keys.forEach(key => delete storage[key]) } },
      action: { setBadgeText: noop, setBadgeBackgroundColor: noop },
      menus: { removeAll: noop, create: () => {}, onClicked: { addListener: value => { globalThis.contextSend = value; } } },
      runtime: { id: 'test', onInstalled: { addListener() {} }, onStartup: { addListener() {} }, onMessage: { addListener: value => { handler = value; } }, sendMessage: async message => handler(message, { id: 'test' }) },
      permissions: { request: async () => true, getAll: async () => ({ origins: [] }), remove: noop },
      tabs: { query: async () => [{ url: 'https://example.org/video' }], create: async options => { globalThis.openedManager = options.url; } },
    };
    globalThis.savedConnection = () => storage.connection;
  }, config);
  await popup.route(address + '/popup/**', async route => {
    const file = new URL(route.request().url()).pathname.split('/').at(-1);
    const path = file === 'remote.js' ? 'downloader/remote.js' : 'browser-extension/firefox/' + file;
    let body = await fs.readFile(path, 'utf8');
    if (file === 'popup.html') body = body.replace('<script src="popup.js"', '<script src="background.js" defer></script><script src="popup.js"');
    await route.fulfill({ body, contentType: file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript' });
  });
  await popup.goto(address + '/popup/popup.html');
  await popup.getByText('Live · updates automatically', { exact: true }).waitFor();
  await popup.getByRole('button', {name:'Open full manager and settings',exact:true}).click();
  assert.equal(await popup.evaluate(()=>globalThis.openedManager), address);
  await popup.getByRole('button', { name: 'Choose folder / drive', exact: true }).click();
  await popup.getByLabel('New folder name').fill('Firefox destination');
  await popup.getByRole('button', { name: 'Create folder', exact: true }).click();
  await popup.locator('.folder-picker > p').filter({ hasText: 'Firefox destination' }).waitFor();
  await popup.getByRole('button', { name: 'Use this folder', exact: true }).click();
  await popup.locator('#destination > p').filter({ hasText: 'Firefox destination' }).waitFor();
  assert.ok((await popup.evaluate(() => savedConnection().directory)).includes('Firefox destination'));
  await torrentFlow(popup, 'firefox', 'Firefox destination');
  await manageQueue(popup, 'firefox');
  await popup.getByLabel('Download link').fill('https://example.org/popup-download.zip');
  await popup.getByRole('button', { name: 'Send to handheld', exact: true }).click();
  await popup.getByText('popup-download.zip', { exact: true }).waitFor();
  await popup.evaluate(() => contextSend({ menuItemId: 'file', linkUrl: 'https://example.org/context-download.zip' }));
  await popup.getByText('context-download.zip', { exact: true }).waitFor();
  const jobs = (await client.DownloaderClient.request(config)).jobs;
  for (const name of ['popup-download.zip', 'context-download.zip']) assert.ok(jobs.find(job => job.name === name).directory.includes('Firefox destination'));
  assert.ok(await popup.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  assert.deepEqual(popupErrors, []);
  await popup.screenshot({ path: '.work/screenshots/receiver-firefox-popup.png', fullPage: true });
  await popup.getByRole('button', { name: 'Use plugin default', exact: true }).click();
  assert.equal(await popup.evaluate(() => savedConnection().directory), '');
  await popup.close();
  console.log('PASS: real HTTP/SSE; full queue pagination/filters and clear-completed; pause/resume/cancel/remove/details with focus retention; web settings save/discard, folder defaults, ratio, auto-updates and password rotation; PC/device torrent import and file selection; web PL/EN 1280/390px keyboard/touch; Firefox popup/background adapter and full-manager link. No physical device or installed Firefox add-on claim.');
} finally {
  if (browser) await browser.close();
  fixture.stdin.end('\n');
  await new Promise(resolve => fixture.exitCode !== null ? resolve() : fixture.once('exit', resolve));
  lines.close();
}
