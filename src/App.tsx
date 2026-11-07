import { DialogButton, DropdownItem, GamepadButton, GamepadEvent, ModalRoot, TextField } from '@decky/ui';
import { ReactNode, useRef, useState } from 'react';
import { bytes, eta, Job, mutate, percent, refresh, Settings, State, useDownloads } from './api';
import { Icon } from './Icon';
import { strings, Strings } from './i18n';
import { useKeyboardSpace, usePageFocus } from './layout';
import { css } from './style';
import { Spatial as Focusable } from './navigation';
import { chooseFolder } from './FolderPicker';
import { ReceiverSettings } from './ReceiverSettings';
import { TorrentFiles } from './TorrentFiles';

type Page = 'list' | 'add' | 'settings' | 'details' | 'torrent-files';
type Filter = 'all' | 'active' | 'queued' | 'interrupted' | 'complete' | 'error' | 'seeding' | 'selecting';
const filters: Filter[] = ['all', 'active', 'queued', 'interrupted', 'complete', 'error', 'seeding', 'selecting'];
const interrupted = (job: Job) => ['paused', 'error', 'cancelled'].includes(job.status);
const matches = (job: Job, filter: Filter) => filter === 'all' || (filter === 'interrupted' ? interrupted(job) : filter === 'seeding' ? ['seeding', 'seed_waiting'].includes(job.status) : job.status === filter);
const stop = (e: GamepadEvent) => { e.preventDefault(); e.stopPropagation(); };
const kindLabel = (kind: string, t: Strings) => kind === 'video' ? t.video : kind === 'audio' ? t.audio : kind.startsWith('torrent') ? t.torrentFile : t.file;
const kindIcon = (kind: string) => kind === 'video' ? '▷' : kind === 'audio' ? '♫' : kind.startsWith('torrent') ? '⇄' : '↓';
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);

function Progress({ job }: { job: Job }) {
  const value = percent(job);
  return <span className={`dd-progress ${job.status}${job.status === 'active' && !job.total ? ' indeterminate' : ''}`}
    role="progressbar" aria-label={job.name} aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.total || job.status === 'complete' ? Math.round(value) : undefined}>
    <span className="dd-fill" style={{ width: `${value}%` }} />
  </span>;
}

function phase(job: Job, t: Strings) {
  if (job.status !== 'active') return t[job.status];
  return job.phase === 'metadata' ? t.metadata : job.phase === 'processing' ? t.processing : job.phase === 'starting' ? t.preparing : t.active;
}

function Card({ job, t, onClick }: { job: Job; t: Strings; onClick: () => void }) {
  return <DialogButton className="dd-card" onClick={onClick} onGamepadFocus={e => (e.currentTarget as HTMLElement)?.scrollIntoView({ block: 'nearest' })}>
    <span className="dd-card-head"><span className="dd-file-icon">{kindIcon(job.file_count ? 'torrent' : job.kind)}</span><span className="dd-card-title">
      <span className="dd-name">{job.name}</span><span className="dd-kind">{kindLabel(job.file_count ? 'torrent' : job.kind, t)}</span>
    </span><span className={`dd-badge ${job.status}`}>{phase(job, t)}</span></span>
    <Progress job={job} />
    <span className="dd-card-meta"><span>{bytes(job.completed)}{job.total > 0 && ` / ${bytes(job.total)}`}</span>
      <span>{job.status === 'seeding' ? `↑ ${bytes(job.upload_speed || 0)}/s · ${(job.uploaded / Math.max(1, job.total)).toFixed(2)} / ${job.ratio_limit}` : job.status === 'active' && job.speed > 0 ? <><strong>{bytes(job.speed)}/s</strong> · {eta(job)}</> : job.status === 'complete' ? t.finished : job.total > 0 ? `${percent(job).toFixed(0)}%` : '-'}</span>
    </span>
  </DialogButton>;
}

function Empty({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return <div className="dd-empty"><div className="dd-hero"><Icon size={38} /></div><h2>{title}</h2><p>{description}</p>{children}</div>;
}

function useAction() {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const gate = useRef(false);
  async function run(action: () => Promise<unknown>, done?: () => void) {
    if (gate.current) return;
    gate.current = true; setBusy(true); setError('');
    try { await action(); done?.(); } catch (e) { setError(errorText(e)); }
    finally { gate.current = false; setBusy(false); }
  }
  return { busy, error, run, setError };
}

function ErrorBox({ error }: { error: string }) { return error ? <div className="dd-error" role="alert">{error}</div> : null; }

function NewDownload({ state, t, back, chooseFiles }: { state: State; t: Strings; back: () => void; chooseFiles: (id: string) => void }) {
  const [kind, setKind] = useState('file'), [source, setSource] = useState('');
  const [directory, setDirectory] = useState(state.settings.directory), [quality, setQuality] = useState('best');
  const { busy, error, run } = useAction();
  const video = kind === 'video' || kind === 'audio';
  const unavailable = state.runtime[video ? 'video' : 'aria2'] === 'missing';
  function submit() { void run(async () => {
    const id = await mutate('add', { source, kind, directory, quality });
    if (state.settings.bt_select_files !== false && (kind === 'torrent-file' || source.startsWith('magnet:') || /\.torrent(?:[?#]|$)/i.test(source))) chooseFiles(id as string);
    else back();
  }); }
  return <>
    <Focusable className="dd-scroll" flow-children="column"><Focusable className="dd-form" flow-children="column">
      <DropdownItem label={t.type} selectedOption={kind} rgOptions={[
        { data: 'file', label: t.file }, { data: 'torrent-file', label: t.torrentFile }, { data: 'video', label: t.video }, { data: 'audio', label: t.audio },
      ]} onChange={o => { setKind(o.data); setSource(''); }} />
      <div className="dd-field">
        {kind === 'torrent-file' ? <>
          <p className="dd-help">{t.torrentHelp}</p><div className="dd-path">{source || '-'}</div>
          <DialogButton data-autofocus disabled={busy} onClick={e => { const opener = e.currentTarget as HTMLElement;
            void run(() => chooseFolder(state.settings.directory, setSource, t, state, opener, true));
          }}>{t.browse}</DialogButton>
        </> : <><TextField label={t.link} value={source} onChange={e => setSource(e.target.value)} disabled={busy} focusOnMount />
          <p className="dd-help">{t.linkHelp}</p></>}
      </div>
      {kind === 'video' && <DropdownItem label={t.quality} selectedOption={quality} rgOptions={['best', '1080', '720', '480'].map(data => ({ data, label: data === 'best' ? t.best : `${data}p` }))} onChange={o => setQuality(o.data)} />}
      {video && <p className="dd-help">{t.formatHelp}</p>}
      <div className="dd-field"><TextField label={t.destination} value={directory} onChange={e => setDirectory(e.target.value)} disabled={busy} />
        <DialogButton disabled={busy} onClick={e => { const opener = e.currentTarget as HTMLElement; void run(() => chooseFolder(directory, setDirectory, t, state, opener)); }}>{t.browse}</DialogButton>
        <p className="dd-help">{t.newFolder}</p>
      </div>
      <p className="dd-help">{t.seedingHelp}</p>
      {unavailable && <div className="dd-notice">{t.setupHelp}</div>}
    </Focusable></Focusable>
    <ErrorBox error={error} />
    <Focusable className="dd-form-footer" flow-children="row">
      <DialogButton onClick={back}>{t.back}</DialogButton>
      <DialogButton className="dd-primary" disabled={busy || !source.trim() || !directory.trim() || unavailable} onClick={submit}>{busy ? t.working : t.start}</DialogButton>
    </Focusable>
  </>;
}

function SettingsPage({ state, t, back }: { state: State; t: Strings; back: () => void }) {
  const [draft, setDraft] = useState<Settings>({ ...state.settings, torrent_ports: state.settings.torrent_ports || '49152-65535',
    upload_limit_kib: state.settings.upload_limit_kib ?? 0, bt_max_peers: state.settings.bt_max_peers ?? 55,
    bt_dht: state.settings.bt_dht ?? true, bt_pex: state.settings.bt_pex ?? true, bt_lpd: state.settings.bt_lpd ?? false,
    bt_encryption: state.settings.bt_encryption ?? false, bt_upnp: state.settings.bt_upnp ?? false,
    receiver_mode: state.settings.receiver_mode ?? 'off', receiver_port: state.settings.receiver_port ?? 6802,
    bt_select_files: state.settings.bt_select_files ?? true, bt_seed: state.settings.bt_seed ?? false, bt_seed_ratio: state.settings.bt_seed_ratio ?? 1,
    video_auto_update: state.settings.video_auto_update ?? false });
  const [seedRatio, setSeedRatio] = useState(String(state.settings.bt_seed_ratio ?? 1));
  const ratio = Number(seedRatio.replace(',', '.'));
  const validRatio = /^\d+(?:[.,]\d+)?$/.test(seedRatio) && ratio >= .1 && ratio <= 100;
  const [section, setSection] = useState<'general' | 'torrent' | 'browser' | 'engines'>('general');
  const [receiverPort, setReceiverPort] = useState(String(state.settings.receiver_port ?? 6802));
  const [upload, setUpload] = useState(String(state.settings.upload_limit_kib ?? 0));
  const [peers, setPeers] = useState(String(state.settings.bt_max_peers ?? 55));
  const [limit, setLimit] = useState(String(state.settings.limit_kib));
  const { busy, error, run } = useAction();
  const installing = state.install.status === 'running';
  const portParts = draft.torrent_ports.trim().split('-').map(Number);
  const validPorts = /^\d{1,5}(-\d{1,5})?$/.test(draft.torrent_ports.trim()) && portParts[0] >= 1024 &&
    portParts[portParts.length - 1] <= 65535 && portParts[0] <= portParts[portParts.length - 1];
  const change = <K extends keyof Settings>(key: K, value: Settings[K]) => setDraft(old => ({ ...old, [key]: value }));
  const provider = (value: string) => value === 'varia' ? 'Varia' : value === 'native' ? t.native : t.unavailable;
  const validNumbers = /^\d+$/.test(upload) && Number(upload) <= 1024000 && /^\d+$/.test(peers) && Number(peers) <= 10000;
  const validReceiverPort = /^\d{4,5}$/.test(receiverPort) && Number(receiverPort) >= 1024 && Number(receiverPort) <= 65535;
  const toggle = (key: 'bt_dht' | 'bt_pex' | 'bt_lpd' | 'bt_encryption' | 'bt_upnp' | 'bt_select_files' | 'bt_seed' | 'video_auto_update', label: string, help: string) =>
    <div className="dd-field"><DialogButton aria-pressed={draft[key]} disabled={busy} onClick={() => change(key, !draft[key])}>{label}: {draft[key] ? t.enabled : t.disabled}</DialogButton><p className="dd-help">{help}</p></div>;
  return <>
    <Focusable data-dd-zone="tabs" className="dd-toolbar dd-tabs" flow-children="row" aria-label={t.settings}>
      {(['general', 'torrent', 'browser', 'engines'] as const).map(key => <DialogButton key={key} data-autofocus={section === key || undefined} aria-pressed={section === key} className={section === key ? 'dd-primary' : ''}
        onClick={() => setSection(key)}>{key === 'general' ? t.generalSettings : key === 'torrent' ? 'BitTorrent' : key === 'browser' ? t.browser : t.runtime}</DialogButton>)}
    </Focusable>
    <Focusable key={section} data-dd-zone="form" className="dd-scroll" flow-children="column"><Focusable className="dd-form" flow-children="column">
      {section === 'browser' && <ReceiverSettings state={state} draft={draft} change={change} port={receiverPort} setPort={setReceiverPort} busy={busy} run={run} t={t} />}
      {section === 'engines' && <div className="dd-runtime"><h2>{t.runtime}</h2><p className="dd-help">{t.runtimeHelp}</p>
        <div className="dd-engine"><span>aria2 · HTTP / BitTorrent</span><span>{provider(state.runtime.aria2)}</span></div>
        <div className="dd-engine"><span>yt-dlp · {t.video} / {t.audio}</span><span>{state.runtime.video_version || provider(state.runtime.video)}{state.runtime.video_managed ? ` · ${t.videoManaged}` : ''}</span></div>
        <div className="dd-engine"><span>FFmpeg</span><span>{state.runtime.ffmpeg ? '✓' : t.unavailable}</span></div>
        {state.runtime.flatpak ? <>
          <p className="dd-help">{t.installHelp}</p>
          <DialogButton data-autofocus disabled={busy || installing || state.video_install?.status === 'running'} onClick={() => void run(() => mutate('install_runtime'))}>{installing ? t.installing : t.install}</DialogButton>
        </> : <p className="dd-help">{t.noFlatpak}</p>}
        {state.install.status === 'complete' && <div className="dd-notice">{t.installed}</div>}
        <ErrorBox error={state.install.error} />
        <p className="dd-help">{t.videoUpdateHelp}</p>
        <DialogButton disabled={busy || installing || state.video_install?.status === 'running'} onClick={() => void run(() => mutate('update_video_engine'))}>{state.video_install?.status === 'running' ? t.videoUpdating : t.videoUpdate}</DialogButton>
        {state.video_install?.status === 'complete' && <div className="dd-notice">{state.video_install.automatic ? t.videoAutoChecked : t.videoUpdated} {state.video_install.version}</div>}
        <ErrorBox error={state.video_install?.error || ''} />
        {toggle('video_auto_update', t.videoAutoUpdate, t.videoAutoHelp)}
      </div>}
      {section === 'general' && <>
      <div className="dd-field"><TextField label={t.location} value={draft.directory} onChange={e => change('directory', e.target.value)} />
        <DialogButton disabled={busy} onClick={e => { const opener = e.currentTarget as HTMLElement; void run(() => chooseFolder(draft.directory, path => change('directory', path), t, state, opener)); }}>{t.browse}</DialogButton></div>
      <DropdownItem label={t.parallel} selectedOption={draft.parallel} rgOptions={[1, 2, 3, 4].map(data => ({ data, label: String(data) }))} onChange={o => change('parallel', o.data)} />
      <div className="dd-field"><TextField label={t.limit} value={limit} onChange={e => setLimit(e.target.value)} /><p className="dd-help">{t.unlimited}</p></div></>}
      {section === 'torrent' && <>
      <div className="dd-field"><TextField label={t.torrentPorts} value={draft.torrent_ports} onChange={e => change('torrent_ports', e.target.value)} /><p className="dd-help">{t.torrentPortsHelp}</p>
        {!validPorts && <p className="dd-help" role="alert">{t.invalidPorts}</p>}</div>
      <div className="dd-field"><TextField label={t.uploadLimit} value={upload} onChange={e => setUpload(e.target.value)} /><p className="dd-help">{t.zeroUnlimited}</p></div>
      <div className="dd-field"><TextField label={t.maxPeers} value={peers} onChange={e => setPeers(e.target.value)} /><p className="dd-help">{t.zeroUnlimited}</p></div>
      {toggle('bt_dht', 'DHT', t.dhtHelp)}
      {toggle('bt_pex', 'PEX', t.pexHelp)}
      {toggle('bt_lpd', t.localPeers, t.lpdHelp)}
      {toggle('bt_encryption', t.encryption, t.encryptionHelp)}
      {toggle('bt_upnp', 'UPnP', t.upnpHelp)}
      {toggle('bt_select_files', t.askTorrentFiles, t.askTorrentFilesHelp)}
      {toggle('bt_seed', t.allowSeeding, t.allowSeedingHelp)}
      {draft.bt_seed && <div className="dd-field"><TextField label={t.seedRatio} value={seedRatio} onChange={e => setSeedRatio(e.target.value)} /><p className="dd-help">{t.seedRatioHelp}</p></div>}
      {(state.network || []).map(item => <div className="dd-notice" key={item.job_id}>UPnP: {item.status === 'mapped' ? `${t.upnpMapped} (${item.port})` : item.status === 'discovering' ? t.working : item.status === 'disabled' ? t.disabled : t.upnpFailed}{item.error && <p>{item.error}</p>}</div>)}
      <p className="dd-help">{t.networkApply}</p>
      </>}
      {section === 'general' && <>
      <DropdownItem label={t.display} selectedOption={draft.display} rgOptions={(['auto', 'window', 'fullscreen'] as const).map(data => ({ data, label: t[data] }))} onChange={o => change('display', o.data)} />
      <DropdownItem label={t.language} selectedOption={draft.language} rgOptions={[{ data: 'en', label: 'English' }, { data: 'pl', label: 'Polski' }]} onChange={o => change('language', o.data)} />
      <p className="dd-help">{t.restart}</p><p className="dd-help">{t.about}</p></>}
    </Focusable></Focusable>
    <ErrorBox error={error} />
    <Focusable data-dd-zone="footer" className="dd-form-footer" flow-children="row"><DialogButton onClick={back}>{t.back}</DialogButton>
      <DialogButton className="dd-primary" disabled={busy || !validPorts || !validNumbers || !validReceiverPort || !validRatio || !/^\d+$/.test(limit) || Number(limit) > 1024000} onClick={() => void run(() => mutate('settings', { changes: { ...draft, bt_seed_ratio: ratio, receiver_port: Number(receiverPort), torrent_ports: draft.torrent_ports.trim(), upload_limit_kib: Number(upload), bt_max_peers: Number(peers), limit_kib: Number(limit) } }), back)}>{busy ? t.working : t.save}</DialogButton>
    </Focusable>
  </>;
}

function Details({ job, t, back, chooseFiles }: { job: Job; t: Strings; back: () => void; chooseFiles: () => void }) {
  const { busy, error, run } = useAction();
  const [confirm, setConfirm] = useState<'cancel' | 'remove' | null>(null);
  const canPause = ['active', 'queued', 'seeding', 'seed_waiting'].includes(job.status);
  const canResume = ['paused', 'error', 'cancelled'].includes(job.status);
  const act = (action: string) => void run(() => mutate('action', { job_id: job.id, action }), () => { setConfirm(null); if (action === 'remove') back(); });
  return <>
    <Focusable className="dd-scroll" flow-children="column"><Focusable className="dd-form" flow-children="column">
      <div><span className={`dd-badge ${job.status}`}>{phase(job, t)}</span><h2 className="dd-detail-title" style={{ marginTop: 14 }}>{job.name}</h2><Progress job={job} /></div>
      <div className="dd-stats"><div className="dd-stat"><span>{t.total}</span><strong>{job.total ? bytes(job.total) : '-'}</strong></div>
        <div className="dd-stat"><span>{t.speed}</span><strong>{bytes(job.speed)}/s</strong></div><div className="dd-stat"><span>{t.remaining}</span><strong>{eta(job)}</strong></div></div>
      <div className="dd-field"><span className="dd-label">{t.destination}</span><div className="dd-path">{job.directory}</div></div>
      <div className="dd-field"><span className="dd-label">{t.source}</span><div className="dd-path">{job.source}</div></div>
      {job.error && <ErrorBox error={job.error} />}
      {!!job.file_count && <div className="dd-notice">↑ {bytes(job.uploaded || 0)} · {t.seedRatio}: {(job.uploaded / Math.max(1, job.total)).toFixed(2)} / {job.ratio_limit || '-'}</div>}
      <p className="dd-help">{t.partial}</p>{(!!job.file_count || job.kind.startsWith('torrent')) && <p className="dd-help">{t.seedingHelp}</p>}
    </Focusable></Focusable><ErrorBox error={error} />
      {confirm ? <div className="dd-confirm"><h2>{confirm === 'cancel' ? t.confirmCancel : t.confirmRemove}</h2><p className="dd-help">{t.keepFiles}</p>
        <Focusable className="dd-actions" flow-children="row"><DialogButton disabled={busy} onClick={() => setConfirm(null)}>{t.nevermind}</DialogButton>
          <DialogButton disabled={busy} onClick={() => act(confirm)}>{t.confirm}</DialogButton></Focusable></div> :
        <Focusable className="dd-form-footer dd-actions" flow-children="row">
          <DialogButton onClick={back}>{t.back}</DialogButton>
          {!!job.file_count && ['selecting', 'paused', 'error', 'cancelled'].includes(job.status) && <DialogButton data-autofocus disabled={busy} onClick={chooseFiles}>{t.chooseTorrentFiles}</DialogButton>}
          {canPause && <DialogButton data-autofocus className="dd-primary" disabled={busy} onClick={() => act('pause')}>{t.pause}</DialogButton>}
          {canResume && <DialogButton data-autofocus className="dd-primary" disabled={busy} onClick={() => act('resume')}>{job.status === 'error' ? t.retry : t.resume}</DialogButton>}
          {job.status === 'queued' && <DialogButton disabled={busy} onClick={() => act('first')}>{t.first}</DialogButton>}
          {['active', 'queued', 'paused', 'error', 'seeding', 'seed_waiting', 'selecting'].includes(job.status) && <DialogButton disabled={busy} onClick={() => setConfirm('cancel')}>{t.cancel}</DialogButton>}
          {!canPause && <DialogButton data-autofocus={job.status === 'complete' ? true : undefined} disabled={busy} onClick={() => setConfirm('remove')}>{t.remove}</DialogButton>}
        </Focusable>}
  </>;
}

export function App({ closeModal, initialPage = 'list' }: { closeModal?: () => void; initialPage?: 'list' | 'settings' }) {
  const { state, error: connectionError } = useDownloads();
  const t = strings(state?.settings.language);
  const [page, setPage] = useState<Page>(initialPage), [filter, setFilter] = useState<Filter>('all');
  const [selected, setSelected] = useState('');
  const [confirmClear, setConfirmClear] = useState(false);
  const { busy, error, run, setError } = useAction();
  const root = useRef<HTMLDivElement>(null);
  useKeyboardSpace(root); usePageFocus(root, page);
  const go = (next: Page) => { setError(''); setConfirmClear(false); setPage(next); };
  const back = () => page === 'list' ? closeModal?.() : page === 'torrent-files' ? go('details') : go('list');
  const display = state?.settings.display || 'auto';
  const displayClass = display === 'fullscreen' || display === 'auto' && state?.handheld ? 'dd-fullscreen' : display === 'auto' ? 'dd-auto' : 'dd-window';
  const jobs = state?.jobs || [];
  const job = jobs.find(j => j.id === selected);
  const visible = jobs.filter(j => matches(j, filter));
  const speed = jobs.reduce((total, item) => total + item.speed, 0);
  const needsSetup = state && (state.runtime.aria2 === 'missing' || state.runtime.video === 'missing');
  const title = page === 'add' ? t.add : page === 'settings' ? t.settings : page === 'torrent-files' ? t.chooseTorrentFiles : page === 'details' ? t.details : 'Decky Downloader';
  function buttons(e: GamepadEvent) {
    const target = e.target as HTMLElement;
    if (page !== 'list' || target?.closest('input,textarea,[role="combobox"]')) return;
    if (e.detail.button === GamepadButton.SECONDARY) { stop(e); go('add'); }
    if (e.detail.button === GamepadButton.OPTIONS) { stop(e); go('settings'); }
    if (e.detail.button === GamepadButton.BUMPER_LEFT || e.detail.button === GamepadButton.BUMPER_RIGHT) {
      stop(e); const direction = e.detail.button === GamepadButton.BUMPER_RIGHT ? 1 : -1;
      setFilter(current => filters[(filters.indexOf(current) + direction + filters.length) % filters.length]);
    }
  }
  return <ModalRoot className={`dd-modal ${displayClass}`} bAllowFullSize bHideCloseIcon onCancel={back} closeModal={closeModal}>
    <style>{css}</style><Focusable ref={root} className="dd-app" data-dd-navigation data-dd-page={page} flow-children="column" onButtonDown={buttons}
      onCancelButton={e => { stop(e); back(); }} onCancelActionDescription={page === 'list' ? t.close : t.back}
      onSecondaryActionDescription={page === 'list' ? t.add : undefined} onOptionsActionDescription={page === 'list' ? t.settings : undefined}>
      <Focusable data-dd-zone="header" className="dd-header" flow-children="row"><div className="dd-logo"><Icon size={28} /></div>
        <div className="dd-brand"><h1>{title}</h1><p className="dd-subtitle">{page === 'list' ? t.subtitle : 'Decky Downloader'}</p></div>
        {page !== 'list' && <DialogButton onClick={back}>{t.back}</DialogButton>}
        <DialogButton className="dd-icon" aria-label={t.close} onClick={closeModal}>×</DialogButton>
      </Focusable>
      {connectionError && <ErrorBox error={`${t.connection}: ${connectionError}`} />}
      {!state ? <Empty title={connectionError ? t.connection : t.loading} description={connectionError ? t.connectionHint : undefined}>
        {connectionError && <DialogButton onClick={() => void refresh()}>{t.tryAgain}</DialogButton>}</Empty> :
        page === 'add' ? <NewDownload state={state} t={t} back={() => go('list')} chooseFiles={id => { setSelected(id); go('torrent-files'); }} /> :
        page === 'settings' ? <SettingsPage state={state} t={t} back={() => go('list')} /> :
        page === 'torrent-files' && job ? <TorrentFiles key={job.id} job={job} t={t} back={() => go('details')} /> :
        page === 'details' && job ? <Details key={job.id} job={job} t={t} back={() => go('list')} chooseFiles={() => go('torrent-files')} /> : <>
          <Focusable className="dd-toolbar" flow-children="row"><DialogButton data-autofocus className="dd-primary" onClick={() => go('add')}>＋ {t.add}</DialogButton>
            <span className="dd-spacer" /><DialogButton disabled={busy || !jobs.some(j => ['active', 'queued', 'seeding', 'seed_waiting'].includes(j.status))} onClick={() => void run(() => mutate('pause_all'))}>{t.pauseAll}</DialogButton>
            <DialogButton disabled={busy || !jobs.some(interrupted)} onClick={() => void run(() => mutate('resume_interrupted'))}>{t.resumeInterrupted}</DialogButton>
            <DialogButton disabled={busy || !jobs.some(j => j.status === 'complete')} onClick={() => setConfirmClear(true)}>{t.clearCompleted}</DialogButton>
            <DialogButton onClick={() => go('settings')}>{t.settings}</DialogButton>
          </Focusable><ErrorBox error={error} />
          {confirmClear && <div className="dd-confirm"><h2>{t.confirmClear}</h2><p className="dd-help">{t.keepFiles}</p>
            <Focusable className="dd-actions" flow-children="row"><DialogButton disabled={busy} onClick={() => setConfirmClear(false)}>{t.nevermind}</DialogButton>
              <DialogButton disabled={busy} onClick={() => void run(() => mutate('clear_completed'), () => setConfirmClear(false))}>{t.confirm}</DialogButton></Focusable></div>}
          <Focusable className="dd-body" flow-children="row"><Focusable className="dd-nav" flow-children="column">
            {filters.map(key => <DialogButton key={key} className={filter === key ? 'dd-selected' : ''} aria-pressed={filter === key} onClick={() => setFilter(key)}>
              <span>{t[key]}</span><span className="dd-count">{jobs.filter(j => matches(j, key)).length}</span>
            </DialogButton>)}<div className="dd-nav-note">{t.background}<br /><br />{t.about}</div>
          </Focusable><Focusable className="dd-list" flow-children="column">
            {visible.map(item => <Card key={item.id} job={item} t={t} onClick={() => { setSelected(item.id); go('details'); }} />)}
            {!visible.length && (needsSetup ? <Empty title={t.setupTitle} description={state.install.status === 'running' ? t.installing : t.setupHelp}>
              <DialogButton className="dd-primary" onClick={() => go('settings')}>{state.install.status === 'running' ? t.view : t.settings}</DialogButton>
            </Empty> : <Empty title={jobs.length ? t.noResults : t.nothing} description={jobs.length ? undefined : t.nothingHelp}>
              <DialogButton className="dd-primary" onClick={() => go('add')}>＋ {t.add}</DialogButton>
            </Empty>)}
          </Focusable></Focusable>
        </>}
      <div className="dd-footer"><span>{speed > 0 ? `↓ ${bytes(speed)}/s` : `${jobs.length} ${t.items}`}{state?.free != null ? ` · ${bytes(state.free)} ${t.free}` : ''}</span>
      </div>
    </Focusable>
  </ModalRoot>;
}
