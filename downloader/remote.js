/* Shared by the offline receiver page and the packaged Firefox popup. */
'use strict';
globalThis.RemotePanel = class {
  constructor({ root, jobs, live, api, stream, selected = '', save = async () => {}, language = () => 'en' }) {
    Object.assign(this, { root, jobs, live, api, stream, selected, save, language });
    this.defaultPath = ''; this.connected = false; this.busy = false; this.generation = 0;
    this.uploadBox = this.element('div', ''); this.uploadBox.className = 'torrent-upload';
    this.torrentBox = this.element('div', ''); this.torrentBox.className = 'torrent-picker';
    const downloadForm = this.root.closest('form');
    if (downloadForm) downloadForm.after(this.uploadBox); else this.jobs.before(this.uploadBox);
    this.jobs.before(this.torrentBox);
    this.jobTools = this.element('div', ''); this.jobTools.className = 'job-tools'; this.jobs.before(this.jobTools);
    this.queueSummary = this.element('p', ''); this.jobTools.before(this.queueSummary);
    this.jobNotice = this.element('div', ''); this.jobNotice.setAttribute('role', 'status'); this.jobs.before(this.jobNotice);
    this.filter = 'all'; this.jobPage = 0;
    // Keep SSE repainting from replacing a button between pointer-down and click.
    this.jobs.addEventListener('pointerdown', () => { this.pressing = true; });
    this.jobTools.addEventListener('pointerdown', () => { this.pressing = true; });
    for (const event of ['pointerup', 'pointercancel']) window.addEventListener(event, () => {
      if (this.pressing) setTimeout(() => { this.pressing = false; if (this.lastSnapshot) this.render(this.lastSnapshot); }, 0);
    });
    this.drawUpload();
    this.draw();
  }
  t(en, pl) { return this.language() === 'pl' ? pl : en; }
  element(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
  button(text, action) {
    const b = this.element('button', text); b.type = 'button'; b.className = 'secondary';
    b.addEventListener('click', () => this.run(action)); return b;
  }
  async run(action) {
    if (this.busy) return;
    this.busy = true; this.error = '';
    this.root.querySelectorAll('button').forEach(b => b.disabled = true);
    try { await action(); } catch (error) { this.error = error.message; }
    finally { this.busy = false; this.draw(); }
  }
  draw() {
    this.root.replaceChildren();
    this.root.append(this.element('strong', this.t('Save on handheld', 'Zapis na handheldzie')),
      this.element('p', this.selected || `${this.t('Plugin default', 'Domyślny folder pluginu')}: ${this.defaultPath || '-'}`));
    this.root.append(this.button(this.t('Choose folder / drive', 'Wybierz folder / dysk'), async () => {
      this.deviceTorrent = false;
      this.locations = (await this.api('/api/locations')).locations;
      await this.open(this.selected || '');
    }), this.button(this.t('Use plugin default', 'Użyj domyślnego folderu'), async () => {
      await this.save(''); this.selected = ''; this.folder = null;
    }));
    if (this.folder) {
      const box = this.element('div', ''); box.className = 'folder-picker';
      const label = this.element('label', this.t('Mounted drives and locations', 'Podłączone dyski i lokalizacje'));
      const drives = document.createElement('select');
      const placeholder = this.element('option', this.t('Choose a location…', 'Wybierz lokalizację…')); placeholder.value = ''; drives.append(placeholder);
      for (const location of this.locations || []) {
        const option = this.element('option', `${location.name}: ${location.path}`); option.value = location.path; drives.append(option);
      }
      drives.addEventListener('change', () => { if (drives.value) void this.run(() => this.open(drives.value)); });
      label.append(drives); box.append(label, this.element('p', this.folder.path));
      const space = this.folder.free === null ? '' : `${(this.folder.free / 1024 ** 3).toFixed(1)} GiB ${this.t('free', 'wolne')}`;
      box.append(this.element('p', space + (this.folder.writable ? '' : this.t(' · Read only', ' · Tylko do odczytu'))));
      box.append(this.button(this.t('Parent folder', 'Folder nadrzędny'), () => this.open(this.folder.parent)),
        this.button(this.t('Refresh drives and folders', 'Odśwież dyski i foldery'), async () => {
          this.locations = (await this.api('/api/locations')).locations; await this.open(this.folder.path);
        }));
      const list = this.element('div', ''); list.className = 'folder-entries';
      for (const entry of this.folder.entries) list.append(this.button(entry.name, async () => {
        if (!this.deviceTorrent || entry.directory) return this.open(entry.path);
        const result = await this.api('/api/control', {method:'device_torrent', args:{source:entry.path, directory:this.selected || null}});
        this.pendingTorrent = result.result; this.folder = null; this.deviceTorrent = false;
        this.uploadNotice.textContent = this.t('Torrent added. Waiting for its file list…', 'Dodano torrent. Oczekiwanie na listę plików…');
        try { this.render(await this.api('/api/status')); } catch {}
      }));
      if (!this.folder.entries.length) list.append(this.element('p', this.t('No subfolders', 'Brak podfolderów')));
      box.append(list);
      if (this.folder.next !== null) box.append(this.button(this.t('More folders', 'Więcej folderów'), () => this.open(this.folder.path, this.folder.next)));
      if (!this.deviceTorrent) {
      const nameLabel = this.element('label', this.t('New folder name', 'Nazwa nowego folderu'));
      const name = document.createElement('input'); name.type = 'text'; name.autocomplete = 'off';
      // Do not submit the surrounding download form while naming a directory.
      name.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); create.click(); } });
      nameLabel.append(name); box.append(nameLabel);
      const create = this.button(this.t('Create folder', 'Utwórz folder'), async () => {
        const result = await this.api('/api/folders', { parent: this.folder.path, name: name.value }); await this.open(result.path);
      }); create.disabled = !this.folder.writable; box.append(create);
      const use = this.button(this.t('Use this folder', 'Użyj tego folderu'), async () => {
        await this.save(this.folder.path); this.selected = this.folder.path; this.folder = null;
      }); use.disabled = !this.folder.writable; box.append(use,
        this.button(this.t('Cancel', 'Anuluj'), async () => { this.folder = null; }));
      } else box.append(this.element('p', this.t('Select a .torrent file on the handheld. It will use the destination selected above.', 'Wybierz plik .torrent na handheldzie. Użyje folderu zapisu wybranego powyżej.')),
        this.button(this.t('Cancel', 'Anuluj'), async () => { this.folder = null; this.deviceTorrent = false; }));
      this.root.append(box);
    }
    if (this.error) { const message = this.element('p', this.error); message.setAttribute('role', 'alert'); this.root.append(message); }
  }
  async open(path, offset = 0) {
    const result = await this.api((this.deviceTorrent ? '/api/device-torrents' : '/api/folders') + (path ? `?path=${encodeURIComponent(path)}&offset=${offset}` : ''));
    if (offset && this.folder?.path === result.path) result.entries = [...this.folder.entries, ...result.entries];
    this.folder = result;
  }
  drawUpload() {
    if (this.uploading) return;
    this.uploadBox.replaceChildren();
    const label = this.element('label', this.t('Torrent file from this computer', 'Plik torrent z tego komputera'));
    const input = document.createElement('input'); input.type = 'file'; input.accept = '.torrent,application/x-bittorrent';
    label.append(input);
    const message = this.element('p', this.t('Up to 20 MiB. Uses the destination selected above.', 'Do 20 MiB. Używa folderu zapisu wybranego powyżej.'));
    this.uploadNotice = message;
    message.setAttribute('role', 'status');
    const button = this.element('button', this.t('Send torrent file', 'Wyślij plik torrent')); button.type = 'button';
    button.addEventListener('click', async () => {
      const file = input.files[0];
      if (!file || !file.size || file.size > 20 * 1024 * 1024 || !/\.torrent$/i.test(file.name)) {
        message.textContent = this.t('Choose a .torrent file up to 20 MiB.', 'Wybierz plik .torrent do 20 MiB.'); return;
      }
      const generation = this.generation;
      this.uploading = true; button.disabled = input.disabled = true;
      message.textContent = this.t('Sending torrent…', 'Wysyłanie torrenta…');
      try {
        const result = await this.api('/api/torrents' + (this.selected ? '?directory=' + encodeURIComponent(this.selected) : ''), file);
        if (generation !== this.generation) return;
        input.value = ''; this.pendingTorrent = result.id;
        message.textContent = this.t('Torrent added. Waiting for its file list…', 'Dodano torrent. Oczekiwanie na listę plików…');
        // A successful upload remains successful if the following status read fails.
        try { this.render(await this.api('/api/status')); } catch {}
      } catch (error) { if (generation === this.generation) message.textContent = error.message; }
      finally { this.uploading = false; button.disabled = input.disabled = false; }
    });
    this.uploadBox.append(label, button, message);
    this.uploadBox.append(this.button(this.t('Choose torrent on handheld', 'Wybierz torrent na handheldzie'), async () => {
      this.deviceTorrent = true; this.locations = (await this.api('/api/locations')).locations;
      await this.open('');
    }));
  }
  async loadTorrent(id, pause = false) {
    const generation = this.generation;
    this.torrentError = ''; this.torrentBusy = true;
    this.torrentBox.textContent = this.t('Loading torrent files…', 'Wczytywanie plików torrenta…');
    try {
      if (pause) await this.api('/api/torrent-pause', { job_id: id });
      let data;
      for (let attempt = 0; attempt < 30; attempt++) {
        data = await this.api('/api/torrent-files?job_id=' + encodeURIComponent(id));
        if (generation !== this.generation) return;
        if (!pause || data.editable) break;
        await new Promise(resolve => setTimeout(resolve, 250));
      }
      this.torrent = { ...data, id, page: 0, selected: new Set(data.selection || data.files.map(f => f.index)) };
    } catch (error) { if (generation === this.generation) this.torrentError = error.message; }
    finally { if (generation === this.generation) { this.torrentBusy = false; this.drawTorrent(); } }
  }
  drawTorrent() {
    this.torrentBox.replaceChildren();
    const data = this.torrent;
    if (this.torrentError) { const error = this.element('p', this.torrentError); error.setAttribute('role', 'alert'); this.torrentBox.append(error); }
    if (!data) return;
    this.torrentBox.append(this.element('h3', this.t('Choose torrent files', 'Wybierz pliki torrenta')), this.element('strong', data.name));
    const action = (text, fn) => {
      const button = this.element('button', text); button.type = 'button'; button.className = 'secondary'; button.disabled = this.torrentBusy;
      button.addEventListener('click', fn); return button;
    };
    const controls = this.element('div', ''); controls.className = 'torrent-controls';
    controls.append(action(this.t('Select all', 'Zaznacz wszystko'), () => { data.selected = new Set(data.files.map(f => f.index)); this.drawTorrent(); }),
      action(this.t('Clear selection', 'Wyczyść wybór'), () => { data.selected.clear(); this.drawTorrent(); }));
    const pages = Math.ceil(data.files.length / 100);
    if (pages > 1) {
      const prev = action(this.t('Previous files', 'Poprzednie pliki'), () => { data.page--; this.drawTorrent(); }); prev.disabled ||= data.page === 0;
      const next = action(this.t('Next files', 'Następne pliki'), () => { data.page++; this.drawTorrent(); }); next.disabled ||= data.page + 1 >= pages;
      controls.append(prev, this.element('span', `${data.page + 1} / ${pages}`), next);
    }
    this.torrentBox.append(controls);
    const list = this.element('div', ''); list.className = 'torrent-files';
    const count = this.element('p', ''); count.setAttribute('role', 'status');
    const start = action(this.t('Download selected', 'Pobierz zaznaczone'), async () => {
      if (this.torrentBusy || !data.selected.size || !data.editable) return;
      const generation = this.generation;
      this.torrentBusy = true; this.torrentError = ''; this.drawTorrent();
      try {
        await this.api('/api/torrent-selection', { job_id: data.id, indices: [...data.selected].sort((a, b) => a - b) });
        if (generation !== this.generation) return;
        this.torrent = null;
        try { this.render(await this.api('/api/status')); } catch {}
      } catch (error) { if (generation === this.generation) this.torrentError = error.message; }
      finally { if (generation === this.generation) { this.torrentBusy = false; this.drawTorrent(); } }
    });
    const update = () => {
      const size = data.files.reduce((sum, file) => sum + (data.selected.has(file.index) ? file.length : 0), 0);
      count.textContent = `${data.selected.size} / ${data.files.length} · ${(size / 1048576).toFixed(2)} MiB`;
      start.disabled = this.torrentBusy || !data.editable || !data.selected.size;
    };
    for (const file of data.files.slice(data.page * 100, (data.page + 1) * 100)) {
      const label = this.element('label', '');
      const box = document.createElement('input'); box.type = 'checkbox'; box.checked = data.selected.has(file.index); box.disabled = this.torrentBusy || !data.editable;
      box.addEventListener('change', () => { if (box.checked) data.selected.add(file.index); else data.selected.delete(file.index); update(); });
      label.append(box, this.element('span', `${file.name} · ${(file.length / 1048576).toFixed(2)} MiB`)); list.append(label);
    }
    update();
    this.torrentBox.append(list, count, this.element('p', this.t('Shared torrent pieces may leave partial data for unselected files.', 'Wspólne fragmenty torrenta mogą pozostawić częściowe dane niezaznaczonych plików.')));
    if (!data.editable) this.torrentBox.append(this.element('p', this.t('Pause the torrent from the list to change its files.', 'Wstrzymaj torrent przyciskiem na liście, aby zmienić pliki.')));
    this.torrentBox.append(start, action(this.t('Close file selection', 'Zamknij wybór plików'), () => { this.torrent = null; this.torrentError = ''; this.drawTorrent(); }));
  }
  async command(method, args = {}) {
    if (this.jobBusy) return;
    const generation = this.generation;
    this.jobBusy = true; this.jobNotice.textContent = this.t('Working…', 'Pracuję…');
    if (this.lastSnapshot) this.render(this.lastSnapshot);
    try {
      await this.api('/api/control', { method, args });
      if (generation !== this.generation) return;
      this.jobNotice.textContent = this.t('Done. Downloaded files are kept.', 'Gotowe. Pobrane pliki pozostają na dysku.');
      if (args.action === 'remove' || method === 'clear_completed') {
        if (args.job_id === this.torrent?.id) { this.torrent = null; this.drawTorrent(); }
      }
      try { this.render(await this.api('/api/status')); } catch {}
    } catch (error) { if (generation === this.generation) this.jobNotice.textContent = error.message; }
    finally { this.jobBusy = false; if (generation === this.generation && this.lastSnapshot) this.render(this.lastSnapshot); }
  }
  confirmCommand(label, method, args = {}) {
    this.jobNotice.replaceChildren(this.element('p', label + ' ' + this.t('Downloaded files will stay on disk.', 'Pobrane pliki pozostaną na dysku.')));
    const confirm = this.element('button', this.t('Confirm', 'Potwierdź')); confirm.type = 'button';
    const back = this.element('button', this.t('Keep download', 'Zachowaj pobieranie')); back.type = 'button'; back.className = 'secondary';
    confirm.onclick = () => void this.command(method, args);
    back.onclick = () => this.jobNotice.replaceChildren();
    this.jobNotice.append(confirm, back); confirm.focus();
  }
  drawJobTools(snapshot, states) {
    const signature = JSON.stringify([snapshot.api, snapshot.jobs.map(j => j.status), this.language(), this.filter, this.jobPage, !!this.jobBusy]);
    if (signature === this.toolsSignature) return;
    this.toolsSignature = signature;
    this.jobTools.replaceChildren();
    if (snapshot.api < 4) return;
    const make = (en, pl, method, enabled, confirm = false) => {
      const label = this.t(en, pl), button = this.element('button', label); button.type = 'button'; button.className = 'secondary';
      button.dataset.focus = method; button.disabled = this.jobBusy || !enabled;
      button.onclick = () => confirm ? this.confirmCommand(label + '?', method) : void this.command(method);
      this.jobTools.append(button);
    };
    make('Pause all', 'Wstrzymaj wszystkie', 'pause_all', snapshot.jobs.some(j => ['active', 'queued', 'seeding', 'seed_waiting'].includes(j.status)));
    make('Resume paused', 'Wznów wstrzymane', 'resume_all', snapshot.jobs.some(j => j.status === 'paused'));
    make('Resume interrupted', 'Wznów przerwane', 'resume_interrupted', snapshot.jobs.some(j => ['paused', 'error', 'cancelled'].includes(j.status)));
    make('Clear completed', 'Wyczyść ukończone', 'clear_completed', snapshot.jobs.some(j => j.status === 'complete'), true);
    const label = this.element('label', this.t('Filter downloads', 'Filtruj pobierania')), select = document.createElement('select');
    select.setAttribute('aria-label', this.t('Filter downloads', 'Filtruj pobierania'));
    select.dataset.focus = 'filter';
    for (const key of ['all', 'active', 'queued', 'interrupted', 'complete', 'error', 'seeding', 'selecting']) {
      const name = key === 'all' ? this.t('All', 'Wszystkie') : key === 'interrupted' ? this.t('Interrupted', 'Przerwane') : states[key];
      const count = snapshot.jobs.filter(j => this.matches(j, key)).length;
      const option = this.element('option', `${name} (${count})`); option.value = key; select.append(option);
    }
    select.value = this.filter; select.onchange = () => { this.filter = select.value; this.jobPage = 0; this.render(this.lastSnapshot); };
    label.append(select); this.jobTools.append(label);
    const count = snapshot.jobs.filter(j => this.matches(j, this.filter)).length;
    const pages = Math.max(1, Math.ceil(count / 50)); this.jobPage = Math.min(this.jobPage, pages - 1);
    if (pages > 1) {
      for (const [delta, en, pl] of [[-1, 'Previous downloads', 'Poprzednie pobrania'], [1, 'Next downloads', 'Następne pobrania']]) {
        const b = this.element('button', this.t(en, pl)); b.type = 'button'; b.dataset.focus = 'page' + delta;
        b.disabled = this.jobPage + delta < 0 || this.jobPage + delta >= pages;
        b.onclick = () => { this.jobPage += delta; this.render(this.lastSnapshot); }; this.jobTools.append(b);
      }
      this.jobTools.append(this.element('span', `${this.jobPage + 1} / ${pages}`));
    }
  }
  matches(job, filter) {
    return filter === 'all' || (filter === 'interrupted' ? ['paused', 'error', 'cancelled'].includes(job.status) :
      filter === 'seeding' ? ['seeding', 'seed_waiting'].includes(job.status) : job.status === filter);
  }
  render(snapshot) {
    this.lastSnapshot = snapshot;
    if (this.pressing) return;
    const totalSpeed = snapshot.jobs.reduce((sum, j) => sum + j.speed, 0);
    this.queueSummary.textContent = `${snapshot.jobs.length} ${this.t('downloads', 'pobrań')} · ${(totalSpeed / 1048576).toFixed(1)} MiB/s` +
      (typeof snapshot.free === 'number' ? ` · ${(snapshot.free / 1073741824).toFixed(1)} GiB ${this.t('free', 'wolne')}` : '');
    if (this.defaultPath !== snapshot.directory) { this.defaultPath = snapshot.directory; if (!this.busy) this.draw(); }
    const focused = (this.jobs.contains(document.activeElement) || this.jobTools.contains(document.activeElement)) ? document.activeElement.dataset.focus : null;
    const openDetails = new Set([...this.jobs.querySelectorAll('details[open]')].map(el => el.dataset.job));
    this.jobs.replaceChildren();
    const states = this.language() === 'pl' ? { selecting:'Wybierz pliki', seeding:'Udostępnianie', seed_waiting:'Udostępnianie w kolejce', active:'Pobieranie', queued:'W kolejce', paused:'Wstrzymane', complete:'Ukończone', cancelled:'Anulowane', error:'Błąd' } :
      { selecting:'Choose files', seeding:'Seeding', seed_waiting:'Seeding queued', active:'Downloading', queued:'Queued', paused:'Paused', complete:'Completed', cancelled:'Cancelled', error:'Failed' };
    this.drawJobTools(snapshot, states);
    for (const job of snapshot.jobs) {
      if (this.pendingTorrent === job.id && job.status === 'error') { this.pendingTorrent = null; this.uploadNotice.textContent = job.error || states.error; }
      if (this.pendingTorrent === job.id && job.file_count && !this.torrentBusy) {
        this.pendingTorrent = null; this.uploadNotice.textContent = this.t('Torrent added. Its files are shown below.', 'Dodano torrent. Lista plików jest poniżej.'); void this.loadTorrent(job.id);
      }
      if (this.torrent?.id === job.id && this.torrent.status !== job.status && !this.torrentBusy) {
        this.torrent.status = job.status; this.torrent.editable = ['selecting', 'paused', 'error', 'cancelled'].includes(job.status); this.drawTorrent();
      }
    }
    const visible = snapshot.jobs.filter(j => this.matches(j, this.filter)).slice(this.jobPage * 50, (this.jobPage + 1) * 50);
    if (!visible.length) this.jobs.append(this.element('li', this.t('No downloads here.', 'Brak pobrań w tej kategorii.')));
    for (const job of visible) {
      const li = this.element('li', ''); const progress = document.createElement('progress'); progress.max = 100;
      if (job.status === 'complete') progress.value = 100;
      else if (job.total > 0) progress.value = Math.min(100, job.completed / job.total * 100);
      else if (job.status !== 'active') progress.value = 0;
      progress.setAttribute('aria-label', job.name);
      li.append(this.element('strong', job.name), this.element('span', states[job.status] || job.status),
        this.element('span', `${(job.completed / 1048576).toFixed(1)} / ${(job.total / 1048576).toFixed(1)} MiB · ${(job.speed / 1048576).toFixed(1)} MiB/s`),
        this.element('span', job.directory), progress);
      if (job.status === 'seeding' || job.status === 'seed_waiting') li.append(this.element('span',
        `↑ ${((job.upload_speed || 0) / 1048576).toFixed(1)} MiB/s · ratio ${((job.uploaded || 0) / Math.max(1, job.total)).toFixed(2)} / ${job.ratio_limit || '-'}`));
      if (job.error) li.append(this.element('span', job.error));
      if (job.speed > 0 && job.total > job.completed) li.append(this.element('span', this.t('Time remaining: ', 'Pozostało: ') + Math.ceil((job.total - job.completed) / job.speed) + ' s'));
      if (snapshot.api >= 4) {
        const controls = this.element('div', ''); controls.className = 'job-actions';
        const add = (action, en, pl, confirmation = false) => {
          const label = this.t(en, pl), b = this.element('button', label); b.type = 'button'; b.className = 'secondary';
          b.dataset.focus = job.id + ':' + action; b.disabled = this.jobBusy;
          b.onclick = () => confirmation ? this.confirmCommand(`${label}: ${job.name}?`, 'action', {job_id: job.id, action}) : void this.command('action', {job_id: job.id, action}); controls.append(b);
        };
        const active = ['active', 'queued', 'seeding', 'seed_waiting'].includes(job.status);
        if (active) add('pause', 'Pause', 'Wstrzymaj');
        if (['paused', 'error', 'cancelled'].includes(job.status)) add('resume', job.status === 'error' ? 'Retry' : 'Resume', job.status === 'error' ? 'Ponów' : 'Wznów');
        if (job.status === 'queued') add('first', 'Move to front', 'Na początek kolejki');
        if (!['complete', 'cancelled'].includes(job.status)) add('cancel', 'Cancel download', 'Anuluj pobieranie', true);
        if (!active) add('remove', 'Remove', 'Usuń', true);
        li.append(controls);
        const detail = this.element('details', ''); detail.dataset.job = job.id; detail.open = openDetails.has(job.id);
        const summary = this.element('summary', this.t('Download details', 'Szczegóły pobierania')); summary.dataset.focus = job.id + ':details';
        const info = this.element('p', this.detailCache?.[job.id] || this.t('Open to load source and details.', 'Otwórz, aby wczytać źródło i szczegóły.'));
        detail.append(summary, info); li.append(detail);
        detail.addEventListener('toggle', async () => {
          if (!detail.open || this.detailCache?.[job.id]) return;
          const generation = this.generation;
          try {
            const data = await this.api('/api/job?job_id=' + encodeURIComponent(job.id));
            if (generation !== this.generation) return;
            this.detailCache ||= {}; this.detailCache[job.id] = `${data.source}\n${data.kind} · ${data.quality}\n${data.directory}`;
            info.textContent = this.detailCache[job.id];
          } catch (error) { info.textContent = error.message; }
        });
      }
      if (job.file_count && job.status !== 'complete') {
        const pause = ['active', 'queued', 'seeding', 'seed_waiting'].includes(job.status);
        const button = this.element('button', pause ? this.t('Pause and choose files', 'Wstrzymaj i wybierz pliki') : this.t('Choose torrent files', 'Wybierz pliki torrenta'));
        button.type = 'button'; button.dataset.focus = job.id + ':files'; button.disabled = this.torrentBusy || this.jobBusy;
        button.addEventListener('click', () => { if (!this.torrentBusy) void this.loadTorrent(job.id, pause); }); li.append(button);
      }
      this.jobs.append(li);
    }
    if (focused) [...this.jobs.querySelectorAll('[data-focus]'), ...this.jobTools.querySelectorAll('[data-focus]')].find(el => el.dataset.focus === focused)?.focus({ preventScroll: true });
    if (this.torrent && !snapshot.jobs.some(j => j.id === this.torrent.id)) { this.torrent = null; this.drawTorrent(); }
  }
  stop() {
    this.connected = false; this.generation++; this.controller?.abort(); clearTimeout(this.timer);
    this.live.textContent = this.t('Disconnected', 'Rozłączono');
    this.pendingTorrent = null; this.torrent = null; this.torrentBusy = false; this.torrentError = ''; this.drawTorrent();
    this.detailCache = {}; this.toolsSignature = null; this.jobNotice.replaceChildren(); this.jobTools.replaceChildren();
  }
  start() {
    this.stop(); this.connected = true; const generation = this.generation; let failures = 0;
    const connect = async () => {
      if (!this.connected || generation !== this.generation) return;
      const controller = this.controller = new AbortController();
      // Also abort stalled connections; a normal server session ends after 60s.
      const timeout = setTimeout(() => controller.abort(), 75000);
      this.live.textContent = this.t('Connecting live view…', 'Łączenie podglądu na żywo…');
      let reader;
      try {
        const response = await this.stream(controller.signal);
        if (generation !== this.generation) { await response.body?.cancel(); return; }
        if (!response.ok) {
          const result = await response.json();
          if ([401, 403, 429].includes(response.status)) this.connected = false;
          throw Error(result.error || 'Live view unavailable.');
        }
        reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
        while (true) {
          const { value, done } = await reader.read(); if (done) break;
          if (generation !== this.generation) return;
          buffer += decoder.decode(value, { stream: true });
          if (buffer.length > 16777216) throw Error('Live response too large.');
          let end;
          while ((end = buffer.indexOf('\n\n')) !== -1) {
            const event = buffer.slice(0, end); buffer = buffer.slice(end + 2);
            if (event.startsWith('data: ')) {
              this.render(JSON.parse(event.slice(6))); failures = 0;
              this.live.textContent = this.t('Live · updates automatically', 'Na żywo · aktualizacja automatyczna');
            }
          }
        }
      } catch (error) {
        if (generation === this.generation) this.live.textContent = this.connected ? this.t('Connection lost · reconnecting…', 'Utracono połączenie · ponawianie…') : error.message;
        failures++;
      } finally {
        clearTimeout(timeout); if (reader) await reader.cancel().catch(() => {});
        if (this.connected && generation === this.generation) this.timer = setTimeout(connect, Math.min(15000, 1000 * 2 ** Math.min(failures, 4)));
      }
    };
    void connect();
  }
};
