import { definePlugin } from '@decky/api';
import { DialogButton, PanelSection, PanelSectionRow, showModal } from '@decky/ui';
import { App } from './App';
import { bytes, dispose, useDownloads } from './api';
import { Icon } from './Icon';
import { strings } from './i18n';
import { css } from './style';
import { closeFolderPicker } from './FolderPicker';

let modal: ReturnType<typeof showModal> | undefined;
function launch(page: 'list' | 'settings' = 'list') {
  if (modal) return;
  modal = showModal(<App initialPage={page} />, undefined, { bNeverPopOut: true, fnOnClose: () => { modal = undefined; } });
}
function Content() {
  const { state, error } = useDownloads();
  const t = strings(state?.settings.language);
  const active = state?.jobs.filter(j => j.status === 'active') || [];
  const speed = active.reduce((sum, job) => sum + job.speed, 0);
  const seeders = state?.jobs.filter(j => j.status === 'seeding') || [];
  const upload = seeders.reduce((sum, job) => sum + (job.upload_speed || 0), 0);
  return <PanelSection><style>{css}</style><div className="dd-sidebar">
    <PanelSectionRow><DialogButton className="dd-primary" onClick={() => launch()}>{t.open}</DialogButton></PanelSectionRow>
    <PanelSectionRow><div className="dd-sidebar-summary">↓ {bytes(speed)}/s<br />{active.length} {t.active.toLowerCase()} · {state?.jobs.filter(j => j.status === 'queued').length || 0} {t.queued.toLowerCase()}</div></PanelSectionRow>
    {!!seeders.length && <PanelSectionRow><p>↑ {bytes(upload)}/s · {seeders.length} {t.seeding.toLowerCase()}</p></PanelSectionRow>}
    {state?.jobs.some(j => j.status === 'selecting') && <PanelSectionRow><p>{t.chooseTorrentFiles}</p></PanelSectionRow>}
    {state?.install.status === 'running' && <PanelSectionRow><p>{t.installing}</p></PanelSectionRow>}
    {error && <PanelSectionRow><p role="alert">{t.connection}</p></PanelSectionRow>}
    <PanelSectionRow><DialogButton onClick={() => launch('settings')}>{t.settings}</DialogButton></PanelSectionRow>
    <PanelSectionRow><p>{t.background}</p></PanelSectionRow>
  </div></PanelSection>;
}
export default definePlugin(() => ({
  name: 'Decky Downloader', titleView: <div>Decky Downloader</div>, icon: <Icon />, content: <Content />,
  onDismount() { closeFolderPicker(); modal?.Close(); modal = undefined; dispose(); },
}));
