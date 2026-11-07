const jobs = [
  { id: '1', name: 'Fedora-Workstation-Live-x86_64.iso', kind: 'file', status: 'active', completed: 1680000000, total: 2400000000, speed: 18400000, phase: 'downloading' },
  { id: '2', name: 'Big Buck Bunny: Blender Open Movie', kind: 'video', status: 'active', completed: 215000000, total: 892000000, speed: 6200000, phase: 'downloading' },
  { id: '3', name: 'Debian installation image', kind: 'torrent', status: 'paused', completed: 380000000, total: 830000000, speed: 0, phase: '' },
  { id: '4', name: 'Game soundtrack collection', kind: 'audio', status: 'queued', completed: 0, total: 0, speed: 0, phase: '' },
  { id: '5', name: 'Blender-4.5-linux-x64.tar.xz', kind: 'file', status: 'complete', completed: 371000000, total: 371000000, speed: 0, phase: '' },
].map(job => ({ ...job, source: `https://example.org/${job.id}`, directory: `/home/deck/Downloads/DeckyDownloader/${job.id}`, error: '', quality: 'best', created: Date.now() / 1000 }));
const state = { jobs, settings: { directory: '/home/deck/Downloads/DeckyDownloader', parallel: 2, limit_kib: 0, display: 'auto', language: 'en' }, handheld: false, free: 138000000000,
  runtime: { flatpak: true, varia: true, aria2: 'varia', video: 'varia', ffmpeg: true, video_version: '2026.07.04', video_managed: false }, install: { status: 'idle', error: '' }, video_install: { status: 'idle', error: '', version: '' } };
(window as any).previewState = state;
(window as any).previewCalls = [];
const createdFolders = new Set<string>();
export const FileSelectionType = { FILE: 0, FOLDER: 1 };
export async function openFilePicker() { return { path: '/run/media/deck/SD/Downloads', realpath: '/run/media/deck/SD/Downloads' }; }
export function callable() { return async (method: string, args: any = {}) => {
  (window as any).previewCalls.push({ method, args });
  if (method === 'state') return { ok: true, data: structuredClone(state) };
  if (method === 'update_video_engine') {
    state.video_install.status = 'running';
    setTimeout(() => { state.runtime.video_version = '2026.10.26'; state.runtime.video_managed = true; state.video_install.status = 'complete'; state.video_install.version = '2026.10.26'; }, 600);
    return { ok: true, data: true };
  }
  if (method === 'locations') return { ok: true, data: [
    { path: '/home/deck', name: 'deck', kind: 'home', writable: true, free: 138000000000 },
    { path: '/', name: '/', kind: 'root', writable: false, free: 5000000000 },
    { path: '/run/media/deck/SD', name: 'SD', kind: 'drive', writable: true, free: 256000000000 },
    { path: '/run/media/deck/USB', name: 'USB', kind: 'drive', writable: false, free: 128000000000 },
  ] };
  if (method === 'browse_folders') {
    if ((window as any).previewHangFolders) return new Promise(() => {});
    if (args.path.endsWith('/Denied')) return { ok: false, error: 'Permission denied' };
    const path = args.path;
    return { ok: true, data: { path, parent: path.substring(0, path.lastIndexOf('/')) || '/',
      entries: path.endsWith('/SD') ? ['Downloads', 'Games', 'Denied'].map(name => ({ name, path: path + '/' + name, directory: true })) :
        args.torrents ? [{ name: 'Sample.torrent', path: path + '/Sample.torrent', directory: false }] : [],
      next: null, writable: path !== '/' && !path.endsWith('/USB'), free: 256000000000 } };
  }
  if (method === 'create_folder') {
    const path = args.parent + '/' + args.name;
    if (createdFolders.has(path) || args.name === 'Existing') return { ok: false, error: 'Folder already exists' };
    createdFolders.add(path);
    return { ok: true, data: { path } };
  }
  if (method === 'settings') Object.assign(state.settings, args.changes);
  if (method === 'receiver_password') { Object.assign(state, { receiver: { running: false, password_set: true, error: '', port: 6802, urls: [] } }); return { ok: true, data: true }; }
  if (method === 'pause_all') state.jobs.forEach(job => { if (['active', 'queued'].includes(job.status)) { job.status = 'paused'; job.speed = 0; } });
  if (method === 'resume_all') state.jobs.forEach(job => { if (job.status === 'paused') job.status = 'queued'; });
  if (method === 'resume_interrupted') state.jobs.forEach(job => { if (['paused', 'error', 'cancelled'].includes(job.status)) job.status = 'queued'; });
  if (method === 'clear_completed') state.jobs = state.jobs.filter(job => job.status !== 'complete');
  if (method === 'torrent_files') return { ok: true, data: { infohash: 'a'.repeat(40), selection: (window as any).previewTorrentSelection || null,
    files: Array.from({ length: 205 }, (_, i) => ({ index: i + 1, name: `Collection/Part ${String(i + 1).padStart(3, '0')}.bin`, length: (i + 1) * 1048576 })) } };
  if (method === 'torrent_select') {
    const job = state.jobs.find(j => j.id === args.job_id)!;
    Object.assign(job, { status: 'queued', selection_mode: 'selected' });
    (window as any).previewTorrentSelection = args.indices;
    return { ok: true, data: true };
  }
  if (method === 'action') {
    const job = state.jobs.find(j => j.id === args.job_id)!;
    if (args.action === 'remove') state.jobs = state.jobs.filter(j => j !== job);
    if (args.action === 'pause') { job.status = 'paused'; job.speed = 0; }
    if (args.action === 'resume') job.status = 'queued';
    if (args.action === 'cancel') job.status = 'cancelled';
  }
  if (method === 'add') {
    const torrent = args.source.startsWith('magnet:') || args.kind === 'torrent-file';
    const id = String(Date.now());
    state.jobs.push({ ...jobs[0], id, source: args.source, name: torrent ? 'Test collection' : args.source, kind: args.kind, directory: args.directory,
      status: torrent ? 'selecting' : 'queued', file_count: torrent ? 205 : 0, selection_mode: torrent ? 'ask' : 'all', speed: 0, completed: 0, total: 0 } as any);
    return { ok: true, data: id };
  }
  return { ok: true, data: true };
}; }
