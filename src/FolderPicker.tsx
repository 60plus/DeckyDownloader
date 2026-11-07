import { DialogButton, ModalRoot, TextField, showModal } from '@decky/ui';
import { useEffect, useRef, useState } from 'react';
import { api, bytes, State } from './api';
import { Strings } from './i18n';
import { focus, useKeyboardSpace, usePageFocus } from './layout';
import { Spatial as Focusable } from './navigation';
import { css } from './style';

type Place = { path: string; name: string; kind: string; writable: boolean; free: number | null };
type Folder = { path: string; parent: string; entries: { path: string; name: string; directory: boolean }[];
  writable: boolean; free: number | null; next: number | null };

export function FolderPicker({ start, t, displayClass, choose, closeModal, torrents = false }: {
  start: string; t: Strings; displayClass: string; choose: (path: string) => void; closeModal?: () => void;
  torrents?: boolean;
}) {
  const [places, setPlaces] = useState<Place[]>([]), [folder, setFolder] = useState<Folder>();
  const [error, setError] = useState(''), [busy, setBusy] = useState(true);
  const [creating, setCreating] = useState(false), [folderName, setFolderName] = useState(''), [saving, setSaving] = useState(false);
  const createGate = useRef(false);
  const [request, setRequest] = useState({ path: start, offset: 0, fallback: true, revision: 0 });
  const root = useRef<HTMLDivElement>(null);
  useKeyboardSpace(root);
  usePageFocus(root, `${folder?.path || 'loading'}:${busy}:${creating}`);
  useEffect(() => {
    let active = true;
    void api<Place[]>('locations', undefined, 15000).then(value => { if (active) setPlaces(value); })
      .catch(e => { if (active) setError(String(e.message || e)); });
    return () => { active = false; };
  }, [request.revision]);
  useEffect(() => {
    let active = true;
    setBusy(true); setError('');
    void api<Folder>('browse_folders', { path: request.path, offset: request.offset, fallback: request.fallback, torrents }, 15000)
      .then(value => {
        if (active) setFolder(old => request.offset && old?.path === value.path ? { ...value, entries: [...old.entries, ...value.entries] } : value);
      }).catch(e => { if (active) setError(String(e.message || e)); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [request, torrents]);
  function open(path: string, offset = 0) { setBusy(true); setRequest(old => ({ ...old, path, offset, fallback: false })); }
  function cancel() {
    if (saving) return;
    if (creating) { setCreating(false); setError(''); } else closeModal?.();
  }
  async function create() {
    if (!folder || createGate.current) return;
    createGate.current = true; setSaving(true); setError('');
    try {
      const result = await api<{ path: string }>('create_folder', { parent: folder.path, name: folderName }, 15000);
      setCreating(false); open(result.path);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { createGate.current = false; setSaving(false); }
  }
  const validName = !!folderName.trim() && !['.', '..'].includes(folderName) && !/[\\/:\x00-\x1f\x7f]/.test(folderName);
  return <ModalRoot className={`dd-modal ${displayClass}`} bAllowFullSize bHideCloseIcon onCancel={cancel} closeModal={cancel}>
    <style>{css}</style><Focusable ref={root} className="dd-app dd-folder-picker" data-dd-navigation flow-children="column"
      onCancelButton={e => { e.preventDefault(); e.stopPropagation(); cancel(); }} onCancelActionDescription={t.nevermind}>
      <Focusable className="dd-header" flow-children="row"><div className="dd-brand"><h1>{creating ? t.createFolder : torrents ? t.torrentFile : t.chooseFolder}</h1></div>
        <DialogButton disabled={saving} onClick={cancel}>{t.nevermind}</DialogButton></Focusable>
      {creating ? <>
        <Focusable className="dd-scroll" flow-children="column"><Focusable className="dd-form" flow-children="column">
          <div className="dd-path">{folder?.path}</div>
          <TextField label={t.folderName} value={folderName} data-autofocus focusOnMount disabled={saving} onChange={e => setFolderName(e.target.value)} />
          <p className="dd-help">{t.createFolderHelp}</p>
          {error && <div className="dd-error" role="alert">{error}</div>}
        </Focusable></Focusable>
        <Focusable className="dd-form-footer" flow-children="row"><DialogButton disabled={saving} onClick={cancel}>{t.nevermind}</DialogButton>
          <DialogButton className="dd-primary" disabled={saving || !validName} onClick={() => void create()}>{saving ? t.working : t.createFolder}</DialogButton></Focusable>
      </> : <>
      <Focusable className="dd-toolbar" flow-children="row">
        <DialogButton disabled={busy || !folder || folder.path === folder.parent} onClick={() => folder && open(folder.parent)}>{t.parentFolder}</DialogButton>
        <DialogButton disabled={busy} onClick={() => { setBusy(true); setRequest(old => ({ path: folder?.path || start, offset: 0, fallback: !folder, revision: old.revision + 1 })); }}>{t.refresh}</DialogButton>
        {!torrents && <DialogButton disabled={busy || !folder?.writable || !!error} onClick={() => { setFolderName(''); setError(''); setCreating(true); }}>{t.createFolder}</DialogButton>}
      </Focusable>
      <div className="dd-picker-path dd-path">{folder?.path || start}</div>
      {error && <div className="dd-error" role="alert">{error}</div>}
      <Focusable className="dd-picker-body" flow-children="row">
        <Focusable className="dd-places" flow-children="column" aria-label={t.drives}>
          <h2>{t.drives}</h2>
          {places.map(place => <DialogButton key={place.path} disabled={busy} onClick={() => open(place.path)}>
            <strong>{place.kind === 'home' ? t.homeFolder : place.kind === 'downloads' ? t.downloadsFolder : place.kind === 'root' ? t.filesystem : place.name}</strong>
            <span>{place.path}</span><span>{place.free !== null ? `${bytes(place.free)} ${t.free}` : ''}{!place.writable ? ` · ${t.readOnly}` : ''}</span>
          </DialogButton>)}
        </Focusable>
        <Focusable className="dd-folders" flow-children="column" aria-label={t.folders} aria-busy={busy}>
          {busy && <p className="dd-help">{t.working}</p>}
          {folder?.entries.map((entry, index) => <DialogButton key={entry.path} data-autofocus={index === 0 || undefined} disabled={busy} onClick={() => entry.directory ? open(entry.path) : choose(entry.path)}>{entry.name}</DialogButton>)}
          {!busy && folder && !folder.entries.length && <p className="dd-help">{torrents ? t.noTorrentFiles : t.noFolders}</p>}
          {folder?.next != null && <DialogButton disabled={busy} onClick={() => open(folder.path, folder.next!)}>{t.moreFolders}</DialogButton>}
        </Focusable>
      </Focusable>
      <div className="dd-picker-note dd-help">{t.mountedHelp}{folder && !folder.writable ? ` ${t.readOnly}` : ''}</div>
      <Focusable className="dd-form-footer" flow-children="row">
        <DialogButton data-autofocus={torrents && !folder?.entries.length || undefined} onClick={closeModal}>{t.nevermind}</DialogButton>
        {!torrents && <DialogButton data-autofocus={!folder?.entries.length || undefined} className="dd-primary" disabled={busy || !folder?.writable || !!error}
          onClick={() => { if (folder) choose(folder.path); }}>{t.useFolder}</DialogButton>}
      </Focusable></>}
    </Focusable>
  </ModalRoot>;
}

let active: { Close: () => void } | undefined;
export function closeFolderPicker() { active?.Close(); active = undefined; }
export function chooseFolder(start: string, set: (path: string) => void, t: Strings, state: State, opener: HTMLElement, torrents = false) {
  return new Promise<void>(resolve => {
    let finished = false;
    let modal: ReturnType<typeof showModal> | undefined;
    const finish = () => {
      if (finished) return;
      finished = true; active = undefined; resolve();
      opener.ownerDocument.defaultView?.setTimeout(() => { if (opener.isConnected) focus(opener); }, 80);
    };
    const close = () => { finish(); modal?.Close(); };
    const display = state.settings.display;
    const displayClass = display === 'fullscreen' || display === 'auto' && state.handheld ? 'dd-fullscreen' : display === 'auto' ? 'dd-auto' : 'dd-window';
    // Steam's returned Close() bypasses fnOnClose. Complete our promise on
    // selection/unload explicitly; the injected closeModal handles cancellation.
    modal = showModal(<FolderPicker start={start} t={t} displayClass={displayClass} torrents={torrents} choose={path => { set(path); close(); }} />,
      opener.ownerDocument.defaultView || undefined, { bNeverPopOut: true, fnOnClose: finish });
    active = { Close: close };
  });
}
