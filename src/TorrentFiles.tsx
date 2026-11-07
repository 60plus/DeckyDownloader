import { DialogButton } from '@decky/ui';
import { useEffect, useState } from 'react';
import { api, bytes, Job, mutate } from './api';
import { Strings } from './i18n';
import { Spatial as Focusable } from './navigation';

type Entry = { index: number; name: string; length: number };
type Catalogue = { infohash: string; files: Entry[]; selection: number[] | null };

export function TorrentFiles({ job, t, back }: { job: Job; t: Strings; back: () => void }) {
  const [data, setData] = useState<Catalogue>();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [page, setPage] = useState(0), [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    if (!job.file_count) return;
    let alive = true;
    void api<Catalogue>('torrent_files', { job_id: job.id }, 15000).then(value => {
      if (alive) { setData(value); setSelected(new Set(value.selection || value.files.map(f => f.index))); }
    }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [job.id, job.file_count]);
  const canChoose = ['selecting', 'paused', 'error', 'cancelled'].includes(job.status);
  const total = data?.files.filter(file => selected.has(file.index)).reduce((sum, file) => sum + file.length, 0) || 0;
  const pages = Math.ceil((data?.files.length || 0) / 100);
  async function submit() {
    if (busy || !canChoose || !selected.size) return;
    setBusy(true); setError('');
    try { await mutate('torrent_select', { job_id: job.id, indices: [...selected].sort((a, b) => a - b) }); back(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  return <>
    <div className="dd-torrent-summary"><strong>{job.name}</strong><p className="dd-help">{t.torrentSelectionHelp}</p></div>
    {data && <Focusable className="dd-toolbar" flow-children="row">
      <DialogButton disabled={busy} onClick={() => setSelected(new Set(data.files.map(f => f.index)))}>{t.selectAll}</DialogButton>
      <DialogButton disabled={busy} onClick={() => setSelected(new Set())}>{t.selectNone}</DialogButton>
      {pages > 1 && <><DialogButton disabled={busy || page === 0} onClick={() => setPage(page - 1)}>{t.previousPage}</DialogButton>
        <span>{page + 1} / {pages}</span><DialogButton disabled={busy || page + 1 >= pages} onClick={() => setPage(page + 1)}>{t.nextPage}</DialogButton></>}
    </Focusable>}
    <Focusable className="dd-list dd-torrent-files" key={page} flow-children="column">
      {data ? data.files.slice(page * 100, (page + 1) * 100).map(file => <DialogButton key={file.index} disabled={busy} aria-pressed={selected.has(file.index)}
        className="dd-torrent-file" onClick={() => setSelected(old => { const next = new Set(old); if (next.has(file.index)) next.delete(file.index); else next.add(file.index); return next; })}>
        <span aria-hidden="true">{selected.has(file.index) ? '☑' : '☐'}</span><span>{file.name}<small>{bytes(file.length)}</small></span>
      </DialogButton>) : <div className="dd-empty"><h2>{job.status === 'error' ? t.error : t.metadata}</h2><p>{job.error || t.metadataWait}</p></div>}
    </Focusable>
    {(error || job.error) && <div className="dd-error" role="alert">{error || job.error}</div>}
    {data && <p className="dd-torrent-summary">{selected.size} / {data.files.length} · {bytes(total)}<span className="dd-help"> · {t.pieceBoundary}</span></p>}
    <Focusable className="dd-form-footer" flow-children="row"><DialogButton disabled={busy} onClick={back}>{t.back}</DialogButton>
      <DialogButton className="dd-primary" disabled={busy || !data || !canChoose || !selected.size} onClick={() => void submit()}>{busy ? t.working : t.downloadSelected}</DialogButton></Focusable>
  </>;
}
