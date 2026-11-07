/* Local web settings use the same validated service methods as the plugin. */
'use strict';
globalThis.ManagerPanel = class {
  constructor({root, api, language, onConnectionChange}) {
    Object.assign(this, {root, api, language, onConnectionChange});
    this.generation = 0;
  }
  t(en, pl) { return this.language() === 'pl' ? pl : en; }
  el(tag, text = '') { const e = document.createElement(tag); e.textContent = text; return e; }
  button(en, pl, fn) {
    const b = this.el('button', this.t(en, pl)); b.type = 'button'; b.className = 'secondary';
    b.onclick = () => void this.run(fn); return b;
  }
  async run(fn) {
    if (this.busy) return;
    this.busy = true; if (this.fieldset) this.fieldset.disabled = true;
    try { await fn(); }
    catch (error) { if (this.message) this.message.textContent = error.message; }
    finally { this.busy = false; if (this.fieldset) this.fieldset.disabled = false; }
  }
  close() { this.generation++; clearTimeout(this.timer); this.root.replaceChildren(); this.opened = false; }
  async open() {
    this.close(); this.opened = true; const generation = this.generation;
    this.root.textContent = this.t('Loading settings…', 'Wczytywanie ustawień…');
    try {
      const state = await this.api('/api/state');
      if (generation !== this.generation) return;
      this.state = state; this.baseline = {...state.settings}; this.draft = {...state.settings};
      this.draw(); this.poll(generation);
    } catch (error) { if (generation === this.generation) this.root.textContent = error.message; }
  }
  poll(generation) {
    this.timer = setTimeout(async () => {
      try {
        const state = await this.api('/api/state');
        if (generation !== this.generation) return;
        this.state = state; this.status();
      } catch (error) { if (generation === this.generation) this.message.textContent = error.message; }
      if (generation === this.generation) this.poll(generation);
    }, 5000);
  }
  draw() {
    this.root.replaceChildren();
    this.root.append(this.el('h2', this.t('Settings', 'Ustawienia')));
    this.message = this.el('p'); this.message.setAttribute('role', 'status');
    this.form = this.el('form'); this.form.noValidate = true;
    this.fieldset = this.el('fieldset'); this.form.append(this.fieldset);
    const tabs = this.el('div'); tabs.className = 'settings-tabs'; tabs.setAttribute('role', 'tablist');
    this.fieldset.append(tabs); this.panels = {}; this.inputs = {};
    for (const [key, en, pl] of [['general', 'General', 'Ogólne'], ['torrent', 'BitTorrent', 'BitTorrent'], ['browser', 'Browser', 'Przeglądarka'], ['engines', 'Download engines', 'Silniki pobierania']]) {
      const tab = this.el('button', this.t(en, pl)); tab.type = 'button'; tab.setAttribute('role', 'tab'); tab.id = 'settings-tab-' + key;
      const panel = this.el('div'); panel.setAttribute('role', 'tabpanel'); panel.id = 'settings-panel-' + key; panel.setAttribute('aria-labelledby', tab.id);
      tab.setAttribute('aria-controls', panel.id); panel.hidden = key !== 'general'; tab.setAttribute('aria-selected', String(!panel.hidden)); tab.tabIndex = panel.hidden ? -1 : 0;
      const activate = () => { for (const b of tabs.children) { b.setAttribute('aria-selected', String(b === tab)); b.tabIndex = b === tab ? 0 : -1; } for (const p of Object.values(this.panels)) p.hidden = p !== panel; };
      tab.onclick = activate;
      tab.onkeydown = event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault(); const all = [...tabs.children], index = all.indexOf(tab);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? all.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + all.length) % all.length;
        all[next].click(); all[next].focus();
      };
      tabs.append(tab); this.panels[key] = panel; this.fieldset.append(panel);
    }
    const field = (section, key, en, pl, type = 'text', options, min, max, step = '1') => {
      const label = this.el('label', this.t(en, pl)); let input;
      if (options) {
        input = this.el('select');
        for (const [value, english, polish] of options) { const option = this.el('option', this.t(english, polish || english)); option.value = value; input.append(option); }
      } else { input = this.el('input'); input.type = type; }
      if (type === 'checkbox') { label.className = 'check-field'; input.checked = this.draft[key]; }
      else input.value = this.draft[key];
      if (min !== undefined) input.min = min;
      if (max !== undefined) input.max = max;
      if (type === 'number') { input.step = step; input.required = true; }
      input.name = key;
      input.addEventListener('input', () => { this.draft[key] = type === 'checkbox' ? input.checked : type === 'number' ? Number(input.value) : input.value; });
      label.append(input); this.panels[section].append(label); this.inputs[key] = input; return input;
    };
    field('general', 'directory', 'Download folder', 'Folder pobierania');
    this.panels.general.append(this.button('Choose folder / drive for defaults', 'Wybierz domyślny folder / dysk', () => this.browse(this.draft.directory, true)));
    this.folderBox = this.el('div'); this.folderBox.className = 'folder-picker'; this.folderBox.hidden = true; this.panels.general.append(this.folderBox);
    field('general', 'parallel', 'Simultaneous downloads', 'Równoczesne pobierania', 'number', null, 1, 4);
    field('general', 'limit_kib', 'Speed limit per download (KiB/s; 0 = unlimited)', 'Limit pobierania (KiB/s; 0 = bez limitu)', 'number', null, 0, 1024000);
    field('general', 'display', 'Plugin display mode', 'Tryb wyświetlania pluginu', 'text', [['auto','Automatic','Automatyczny'],['window','Window','Okno'],['fullscreen','Full screen','Pełny ekran']]);
    field('general', 'language', 'Plugin language', 'Język pluginu', 'text', [['en','English'],['pl','Polski']]);
    field('torrent', 'torrent_ports', 'Torrent ports (TCP / UDP)', 'Porty torrentów (TCP / UDP)');
    this.panels.torrent.append(this.el('p', this.t('Port or range, e.g. 51413 or 51413-51416. Changes apply when a download starts or resumes.', 'Port lub zakres, np. 51413 albo 51413-51416. Zmiany działają po uruchomieniu lub wznowieniu pobierania.')));
    field('torrent', 'upload_limit_kib', 'Upload limit per torrent (KiB/s; 0 = unlimited)', 'Limit wysyłania torrenta (KiB/s; 0 = bez limitu)', 'number', null, 0, 1024000);
    field('torrent', 'bt_max_peers', 'Maximum peers (0 = unlimited)', 'Maksymalna liczba peerów (0 = bez limitu)', 'number', null, 0, 10000);
    for (const [key, en, pl] of [['bt_dht','DHT','DHT'], ['bt_pex','PEX','PEX'], ['bt_lpd','Local peer discovery','Wykrywanie peerów w LAN'], ['bt_encryption','Require encrypted peers','Wymagaj szyfrowanych połączeń'], ['bt_upnp','UPnP port mapping','Mapowanie portów UPnP'], ['bt_select_files','Choose files before downloading torrents','Wybierz pliki przed pobraniem torrenta'], ['bt_seed','Seed after download','Seeduj po pobraniu']]) field('torrent', key, en, pl, 'checkbox');
    field('torrent', 'bt_seed_ratio', 'Stop seeding at ratio', 'Zatrzymaj seedowanie przy ratio', 'number', null, 0.1, 100, '0.1');
    this.panels.torrent.append(this.el('p', this.t('Torrents upload while downloading. The ratio limit applies to optional seeding after completion. UPnP is off by default.', 'Torrenty wysyłają dane w trakcie pobierania. Limit ratio dotyczy opcjonalnego seedowania po ukończeniu. UPnP jest domyślnie wyłączone.')));
    this.network = this.el('p'); this.panels.torrent.append(this.network);
    field('browser', 'receiver_mode', 'Receive downloads', 'Odbieraj pobierania', 'text', [['off','Off','Wyłączone'], ['local','This device only','Tylko to urządzenie'], ['lan','Home network (LAN)','Sieć domowa (LAN)']]);
    field('browser', 'receiver_port', 'Receiver HTTP port', 'Port HTTP odbiornika', 'number', null, 1024, 65535);
    this.panels.browser.append(this.el('p', this.t('Changing the port or mode disconnects this page. LAN is required to reconnect from another computer. Turning the receiver off requires re-enabling it in the plugin.', 'Zmiana portu lub trybu rozłączy tę stronę. Połączenie z innego komputera wymaga LAN. Wyłączony odbiornik włączysz ponownie w pluginie.')));
    const passwordLabel = this.el('label', this.t('New receiver password', 'Nowe hasło odbiornika'));
    this.password = this.el('input'); this.password.type = 'password'; this.password.autocomplete = 'new-password'; passwordLabel.append(this.password);
    this.panels.browser.append(passwordLabel, this.button('Show / hide password', 'Pokaż / ukryj hasło', async () => { this.password.type = this.password.type === 'password' ? 'text' : 'password'; }),
      this.button('Change password', 'Zmień hasło', async () => {
        const password = this.password.value;
        await this.api('/api/control', {method:'receiver_password', args:{password}});
        this.password.value = ''; this.message.textContent = this.t('Password changed. Other senders must reconnect.', 'Hasło zmienione. Pozostałe urządzenia muszą połączyć się ponownie.');
        this.onConnectionChange({password});
      }));
    this.engineStatus = this.el('p'); this.panels.engines.append(this.engineStatus);
    this.installButton = this.button('Install / update Varia', 'Zainstaluj / zaktualizuj Varię', () => this.engine('install_runtime'));
    this.updateButton = this.button('Update yt-dlp', 'Zaktualizuj yt-dlp', () => this.engine('update_video_engine'));
    this.panels.engines.append(this.installButton, this.updateButton);
    field('engines', 'video_auto_update', 'Automatic yt-dlp updates', 'Automatyczne aktualizacje yt-dlp', 'checkbox');
    this.panels.engines.append(this.el('p', this.t('Checks daily while the plugin is running; retries failed checks after one hour. Running downloads keep their engine. Save settings to apply.', 'Sprawdza raz dziennie podczas działania pluginu; po błędzie ponawia za godzinę. Trwające pobierania zachowują swój silnik. Zapisz ustawienia, aby zastosować.')));
    const save = this.el('button', this.t('Save settings', 'Zapisz ustawienia')); save.type = 'submit';
    this.fieldset.append(save, this.button('Discard changes and close', 'Odrzuć zmiany i zamknij', async () => this.close()));
    this.form.onsubmit = event => { event.preventDefault();
      const invalid = Object.values(this.inputs).find(input => !input.checkValidity());
      if (invalid) { const key = Object.keys(this.panels).find(key => this.panels[key].contains(invalid)); tabs.querySelector('#settings-tab-' + key).click(); invalid.reportValidity(); return; }
      void this.run(async () => {
      const changes = Object.fromEntries(Object.entries(this.draft).filter(([key, value]) => value !== this.baseline[key]));
      const result = await this.api('/api/control', {method:'settings', args:{changes}});
      this.baseline = {...this.draft}; this.message.textContent = this.t('Settings saved.', 'Ustawienia zapisane.');
      if ('receiver_port' in changes || 'receiver_mode' in changes) { this.onConnectionChange({receiver:result.receiver}); }
      else { this.state = await this.api('/api/state'); this.status(); }
    }); };
    this.root.append(this.form, this.message); this.status();
  }
  async engine(method) {
    await this.api('/api/control', {method, args:{}});
    this.state = await this.api('/api/state'); this.status();
    this.message.textContent = this.t('Engine operation started. Progress updates automatically.', 'Uruchomiono operację silnika. Stan aktualizuje się automatycznie.');
  }
  status() {
    if (!this.engineStatus) return;
    const {runtime = {}, install = {}, video_install = {}, network = []} = this.state;
    this.engineStatus.textContent = `aria2: ${runtime.aria2 || '-'}\nyt-dlp: ${runtime.video_version || runtime.video || '-'}\nFFmpeg: ${runtime.ffmpeg ? '✓' : '-'}\nVaria: ${install.status || 'idle'} ${install.error || ''}\nyt-dlp: ${video_install.status || 'idle'} ${video_install.error || ''}`;
    this.installButton.disabled = this.updateButton.disabled = install.status === 'running' || video_install.status === 'running';
    this.network.textContent = network.map(n => `UPnP: ${n.status} ${n.port || ''} ${n.error || ''}`).join('\n');
  }
  async browse(path, locations = false, offset = 0) {
    if (locations) this.locations = (await this.api('/api/locations')).locations;
    const folder = await this.api('/api/folders' + (locations && path === this.state.settings.directory ? '' : '?path=' + encodeURIComponent(path) + '&offset=' + offset));
    if (offset && this.folder?.path === folder.path) folder.entries = [...this.folder.entries, ...folder.entries];
    this.folder = folder; this.folderBox.hidden = false; this.folderBox.replaceChildren();
    const select = this.el('select'); select.setAttribute('aria-label', this.t('Settings drives', 'Dyski w ustawieniach'));
    const placeholder = this.el('option', this.t('Choose drive / location', 'Wybierz dysk / lokalizację')); placeholder.value = ''; select.append(placeholder);
    for (const loc of this.locations || []) { const option = this.el('option', `${loc.name}: ${loc.path}`); option.value = loc.path; select.append(option); }
    select.onchange = () => { if (select.value) void this.run(() => this.browse(select.value)); };
    this.folderBox.append(select, this.el('p', folder.path), this.button('Parent folder', 'Folder nadrzędny', () => this.browse(folder.parent)));
    const entries = this.el('div'); entries.className = 'folder-entries';
    for (const entry of folder.entries) entries.append(this.button(entry.name, entry.name, () => this.browse(entry.path)));
    this.folderBox.append(entries);
    if (folder.next !== null) this.folderBox.append(this.button('More folders', 'Więcej folderów', () => this.browse(folder.path, false, folder.next)));
    const label = this.el('label', this.t('Settings new folder name', 'Nazwa nowego folderu w ustawieniach')), name = this.el('input'); label.append(name);
    name.onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); create.click(); } };
    const create = this.button('Create folder', 'Utwórz folder', async () => { const result = await this.api('/api/folders', {parent:folder.path, name:name.value}); await this.browse(result.path); }); create.disabled = !folder.writable;
    const use = this.button('Use as default folder', 'Ustaw jako domyślny folder', async () => {
      this.draft.directory = this.inputs.directory.value = folder.path; this.folderBox.hidden = true;
    }); use.disabled = !folder.writable;
    this.folderBox.append(label, create, use, this.button('Close folder picker', 'Zamknij wybór folderu', async () => { this.folderBox.hidden = true; }));
  }
};
