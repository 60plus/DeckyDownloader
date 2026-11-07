import { DialogButton, DropdownItem, TextField } from '@decky/ui';
import { useState } from 'react';
import { mutate, Settings, State } from './api';
import { Strings } from './i18n';

export function ReceiverSettings({ state, draft, change, port, setPort, busy, run, t }: {
  state: State; draft: Settings; change: <K extends keyof Settings>(key: K, value: Settings[K]) => void;
  port: string; setPort: (value: string) => void; busy: boolean;
  run: (action: () => Promise<unknown>) => Promise<void>; t: Strings;
}) {
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [saved, setSaved] = useState(false);
  async function savePassword() {
    await mutate('receiver_password', { password });
    setPassword(''); setSaved(true); setShow(false);
  }
  const receiver = state.receiver;
  const valid = [...password].length >= 4 && [...password].length <= 128 && !!password.trim() && !/[\u0000-\u001f\u007f]/.test(password);
  return <>
    <DropdownItem label={t.receiverMode} selectedOption={draft.receiver_mode}
      rgOptions={[{ data: 'off', label: t.disabled }, { data: 'local', label: t.receiverLocal }, { data: 'lan', label: t.receiverLan }]}
      onChange={option => change('receiver_mode', option.data)} />
    <div className="dd-field"><TextField label={t.receiverPort} value={port} onChange={event => setPort(event.target.value)} />
      <p className="dd-help">{t.receiverHelp}</p></div>
    <div className="dd-field"><TextField label={t.receiverPassword} value={password} bIsPassword={!show}
      disabled={busy} onChange={event => { setPassword(event.target.value); setSaved(false); }} />
      <p className="dd-help">{t.receiverPasswordHelp}</p>
      <DialogButton disabled={busy} onClick={() => setShow(!show)}>{show ? t.receiverHidePassword : t.receiverShowPassword}</DialogButton>
      <DialogButton disabled={busy || !valid} onClick={() => void run(savePassword)}>{t.receiverSavePassword}</DialogButton>
      {saved && <div className="dd-notice" role="status">{t.receiverPasswordSaved}</div>}
      {!saved && <p className="dd-help">{receiver?.password_set ? t.receiverPasswordSet : t.receiverPasswordNeeded}</p>}
    </div>
    <div className="dd-notice">{t.receiverStatus}: {receiver?.running ? t.receiverRunning : t.disabled}</div>
    {receiver?.error && <div className="dd-error" role="alert">{receiver.error}</div>}
    {receiver?.running && <>
      <p className="dd-help">{t.receiverAddressHelp}</p>
      {receiver.urls.map(url => <div className="dd-path" key={url}>{url}</div>)}
      <p className="dd-help">{t.receiverPasswordUse}</p>
    </>}
    <p className="dd-help">{t.receiverBrowserHelp}</p>
    <p className="dd-help">{t.receiverPrivacy}</p>
  </>;
}
