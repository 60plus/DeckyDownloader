"""Static, offline inbox page; no credentials are embedded in these assets."""
from pathlib import Path

PAGE = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Decky Downloader</title><link rel="stylesheet" href="/style.css"><script src="/remote.js" defer></script><script src="/manager.js" defer></script><script src="/app.js" defer></script></head>
<body><main><header><span class="mark">↓</span><div><h1>Decky Downloader</h1><p data-i18n="subtitle">Send to your handheld</p></div>
<select id="language" aria-label="Language"><option value="en">English</option><option value="pl">Polski</option></select></header>
<button id="settings" class="secondary" data-i18n="settings">Settings</button><section id="manager" hidden></section>
<section><h2 data-i18n="connect">Connect</h2><p data-i18n="keyHelp">Use the password you set in Settings → Browser in the plugin.</p>
<label><span data-i18n="key">Password</span><input id="key" type="password" autocomplete="off" spellcheck="false" ></label>
<div class="row"><button id="connect" data-i18n="connect">Connect</button><button id="forget" class="secondary" data-i18n="forget">Forget password</button></div>
<p class="hint" data-i18n="privacy">For your trusted home network. HTTP does not encrypt links or the password. No cloud account is used.</p></section>
<section><h2 data-i18n="send">Send a download</h2><form id="download">
<label><span data-i18n="link">Download link</span><textarea id="source" rows="3" maxlength="16384" required placeholder="https://… / magnet:…" spellcheck="false"></textarea></label>
<div class="row"><label><span data-i18n="type">Type</span><select id="kind"><option value="file" data-i18n="file">File / magnet</option><option value="video" data-i18n="video">Video</option><option value="audio" data-i18n="audio">Audio (MP3)</option></select></label>
<label><span data-i18n="quality">Video quality</span><select id="quality"><option value="best" data-i18n="best">Best available</option><option value="1080">1080p</option><option value="720">720p</option><option value="480">480p</option></select></label></div>
<div id="destination" class="remote-destination"></div>
<button id="send" type="submit" data-i18n="queue">Add to queue</button></form></section>
<p id="message" role="status" aria-live="polite"></p>
<section><div class="row"><h2 data-i18n="recent">Recent downloads</h2><button id="refresh" class="secondary" data-i18n="refresh">Refresh</button></div><p id="live" role="status"></p><ul id="jobs"></ul></section>
<footer data-i18n="limits">Public links and magnets. Links requiring browser cookies or login may need additional authentication and are not transferred with this page.</footer>
</main></body></html>'''

STYLE = '''*{box-sizing:border-box}body{margin:0;background:#10191f;color:#edf4f2;font:16px/1.5 system-ui,sans-serif}main{max-width:760px;margin:32px auto;padding:0 20px}header,.row{display:flex;align-items:center;gap:16px}header{margin-bottom:28px}header div{flex:1}h1{font-size:26px;margin:0}h2{font-size:20px;margin:0 0 12px}p{margin:8px 0 16px;color:#bacdc7}.mark{font-size:38px;color:#61deb4}.row>*{flex:1;min-width:0}section{background:#19272c;border:1px solid #33474a;border-radius:16px;padding:24px;margin-bottom:20px}label{display:flex;flex-direction:column;gap:6px;margin-bottom:16px}input,textarea,select,button{font:inherit;min-height:46px;border-radius:9px;padding:10px 14px}input,textarea,select{width:100%;background:#0f1d22;color:#edf4f2;border:1px solid #52666b}textarea{resize:vertical}button{border:0;background:#60d8ae;color:#0a3024;font-weight:650;cursor:pointer}button.secondary{background:#30454d;color:#edf4f2}button:disabled{opacity:.5;cursor:wait}:focus-visible{outline:3px solid #96f2d3;outline-offset:3px}#language{width:auto;font-size:14px}.hint,footer{font-size:13px;color:#afc2bb}#message{padding:0 12px;color:#90f2cc;overflow-wrap:anywhere}#message.error{color:#ffb5ad}ul{padding:0;margin:0;list-style:none}li{padding:12px 0;border-top:1px solid #33474a;overflow-wrap:anywhere}li span{display:block;color:#afc2bb;font-size:14px}progress{width:100%;height:9px;accent-color:#60d8ae}@media(max-width:520px){main{margin:20px auto;padding:0 12px}section{padding:18px}.row{flex-wrap:wrap}.row>*{flex-basis:140px}header{flex-wrap:wrap}h1{font-size:22px}}'''

SCRIPT = r''''use strict';
const $ = id => document.getElementById(id);
const words = {
 en: {subtitle:'Send to your handheld',connect:'Connect',keyHelp:'Use the password you set in Settings → Browser in the plugin.',key:'Password',forget:'Forget password',privacy:'For your trusted home network. HTTP does not encrypt links or the password. No cloud account is used.',send:'Send a download',link:'Download link',type:'Type',file:'File / magnet',video:'Video',audio:'Audio (MP3)',quality:'Video quality',best:'Best available',destination:'Saves to the default folder configured in the plugin. The handheld must be awake with SPlug or Decky Loader running.',queue:'Add to queue',recent:'Recent downloads',refresh:'Refresh',limits:'Public links and magnets. Browser cookies and logged-in sessions are not transferred.',connected:'Connected to Decky Downloader.',accepted:'Added to the handheld queue.',forgot:'Password removed from this tab.',empty:'No downloads yet.',network:'Cannot confirm the result. Check the receiver address, password and handheld queue before retrying.',invalidKey:'Enter the password set in the plugin (4-128 characters).',active:'Downloading',queued:'Queued',paused:'Paused',complete:'Completed',cancelled:'Cancelled',error:'Failed'},
 pl: {subtitle:'Wyślij na handheld',connect:'Połącz',keyHelp:'Użyj hasła ustawionego w pluginie: Ustawienia → Przeglądarka.',key:'Hasło',forget:'Zapomnij hasło',privacy:'Do zaufanej sieci domowej. HTTP nie szyfruje linków ani hasła. Nie wymaga konta w chmurze.',send:'Wyślij pobieranie',link:'Link do pobrania',type:'Rodzaj',file:'Plik / magnet',video:'Wideo',audio:'Dźwięk (MP3)',quality:'Jakość wideo',best:'Najlepsza dostępna',destination:'Zapisuje w domyślnym folderze ustawionym w pluginie. Handheld musi być wybudzony, z działającym SPlug lub Decky Loader.',queue:'Dodaj do kolejki',recent:'Ostatnie pobierania',refresh:'Odśwież',limits:'Publiczne linki i magnety. Ciasteczka i sesja zalogowania w przeglądarce nie są przesyłane.',connected:'Połączono z Decky Downloader.',accepted:'Dodano do kolejki handhelda.',forgot:'Usunięto hasło z tej karty.',empty:'Brak pobrań.',network:'Nie można potwierdzić wyniku. Sprawdź adres, hasło i kolejkę na handheldzie przed ponowieniem.',invalidKey:'Wpisz swoje hasło z pluginu (4-128 znaków).',active:'Pobieranie',queued:'W kolejce',paused:'Wstrzymane',complete:'Ukończone',cancelled:'Anulowane',error:'Błąd'}
};
let language = navigator.language.startsWith('pl') ? 'pl' : 'en', busy = false;
function t(key){return words[language][key] || key;}
function say(message, error=false){$('message').textContent=message;$('message').classList.toggle('error',error);}
function translate(){document.documentElement.lang=language;document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n));}
Object.assign(words.en, {subtitle:'Manage your handheld downloads',recent:'Downloads',settings:'Settings'});
Object.assign(words.pl, {subtitle:'Zarządzaj pobieraniem na handheldzie',recent:'Pobierania',settings:'Ustawienia'});
$('language').value=language;translate();
$('language').addEventListener('change',()=>{language=$('language').value;translate();panel.draw();panel.drawUpload();panel.drawTorrent();if(panel.lastSnapshot)panel.render(panel.lastSnapshot);if(manager.opened && manager.state && !manager.busy){const password=manager.password?.value;manager.draw();if(password)manager.password.value=password;}});
try{$('key').value=sessionStorage.getItem('dd-password') || sessionStorage.getItem('dd-key') || '';}catch{}
function authorization(){
 const password=$('key').value;
 if([...password].length<4 || [...password].length>128 || !password.trim() || /[\u0000-\u001f\u007f]/.test(password))throw Error(t('invalidKey'));
 return 'Basic '+btoa(String.fromCharCode(...new TextEncoder().encode('downloader:'+password)));
}
async function api(path, data){
 const auth=authorization(), password=$('key').value;
 let response;
 try{response=await fetch(path,{method:data?'POST':'GET',headers:{Authorization:auth,...(data?{'Content-Type':data instanceof Blob?'application/x-bittorrent':'application/json'}:{})},body:data instanceof Blob?data:data?JSON.stringify(data):undefined,signal:AbortSignal.timeout(data instanceof Blob?45000:15000),credentials:'omit',redirect:'error'});}catch{throw Error(t('network'));}
 const result=await response.json();if(!response.ok)throw Error(result.error || t('network'));
 try{sessionStorage.setItem('dd-password',password);sessionStorage.removeItem('dd-key');}catch{}
 return result;
}
let selected='';try{selected=sessionStorage.getItem('dd-directory') || '';}catch{}
const panel = new RemotePanel({root:$('destination'),jobs:$('jobs'),live:$('live'),api,language:()=>language,selected,
 save:async path=>{try{sessionStorage.setItem('dd-directory',path);}catch{}},
 stream:signal=>fetch('/api/events',{headers:{Authorization:authorization()},signal,credentials:'omit',redirect:'error'})});
const manager = new ManagerPanel({root:$('manager'),api,language:()=>language,onConnectionChange:change=>{
 panel.stop();
 if(change.password){$('key').value=change.password;try{sessionStorage.setItem('dd-password',change.password);}catch{}panel.start();}
 else {
  manager.close();const receiver=change.receiver;
  say(language==='pl'?'Zapisano ustawienia odbiornika. Połącz się ponownie pod nowym adresem; wyłączony odbiornik włącz w pluginie.':'Receiver settings saved. Reconnect at the new address; re-enable a disabled receiver in the plugin.');
  if(receiver.running){const url=new URL(location.href);url.port=receiver.port;url.pathname='/';url.search='';url.hash='';const link=document.createElement('a');link.href=url.href;link.textContent=url.href;$('message').append(document.createTextNode(' '),link);}
 }
}});
$('settings').onclick=()=>{if(manager.busy)return;$('manager').hidden=false;void manager.open();};
async function run(action){if(busy)return;busy=true;const buttons=[...document.querySelectorAll('button')].filter(b=>!b.closest('#destination,#jobs,#manager,.job-tools,.torrent-upload,.torrent-picker'));buttons.forEach(b=>b.disabled=true);try{await action();}catch(error){say(error.message,true);}finally{busy=false;buttons.forEach(b=>b.disabled=false);}}
async function refresh(){const result=await api('/api/status');panel.render(result);}
$('connect').addEventListener('click',()=>run(async()=>{await refresh();panel.start();say(t('connected'));}));
$('refresh').addEventListener('click',()=>run(refresh));
$('forget').addEventListener('click',()=>{panel.stop();manager.close();try{sessionStorage.removeItem('dd-key');sessionStorage.removeItem('dd-password');sessionStorage.removeItem('dd-directory');}catch{}panel.selected='';panel.folder=null;panel.draw();$('key').value='';$('jobs').replaceChildren();say(t('forgot'));});
$('key').addEventListener('input',()=>{panel.stop();manager.close();});
window.addEventListener('pagehide',()=>{panel.stop();manager.close();});
$('download').addEventListener('submit',event=>{event.preventDefault();run(async()=>{
 await api('/api/downloads',{source:$('source').value.trim(),kind:$('kind').value,quality:$('quality').value,...(panel.selected?{directory:panel.selected}:{})});
 $('source').value='';say(t('accepted'));
 // An accepted POST must not look failed just because the following status read fails.
 try{await refresh();}catch{}
});});
$('kind').addEventListener('change',()=>{$('quality').disabled=$('kind').value!=='video';});
$('quality').disabled=true;
if($('key').value)run(async()=>{await refresh();panel.start();});
'''

STYLE += '''.remote-destination{margin:16px 0;overflow-wrap:anywhere}.remote-destination button{margin:4px 4px 4px 0}.folder-picker{border:1px solid #52666b;border-radius:9px;padding:12px;margin-top:12px}.folder-entries{max-height:260px;overflow:auto;overscroll-behavior:contain}.folder-entries button{display:block;width:100%;text-align:left;overflow-wrap:anywhere}'''

STYLE += '''.torrent-upload,.torrent-picker:not(:empty){border:1px solid #52666b;border-radius:9px;padding:12px;margin:16px 0;overflow-wrap:anywhere}.torrent-picker button{margin:4px;min-height:44px}.torrent-controls{display:flex;flex-wrap:wrap;align-items:center;gap:4px}.torrent-files{max-height:320px;overflow:auto;overscroll-behavior:contain}.torrent-files label{display:flex;flex-direction:row;align-items:center;gap:10px;min-height:44px;margin:0;padding:8px;border-bottom:1px solid #33474a;cursor:pointer}.torrent-files input{width:22px;height:22px;min-height:22px;flex:0 0 22px;margin:0;padding:0}.torrent-files span{min-width:0;overflow-wrap:anywhere}.torrent-upload input{max-width:100%;min-width:0}'''

STYLE += '''[hidden]{display:none!important}#settings{margin-bottom:20px}#manager:empty{display:none}fieldset{border:0;padding:0;margin:0;min-width:0}.settings-tabs,.job-actions,.job-tools{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.job-tools label{flex-basis:100%;margin:8px 0}.job-tools button,.job-actions button{flex:1 1 auto}.settings-tabs button[aria-selected=true]{background:#b5f6c8;color:#10251b}.check-field{flex-direction:row;align-items:center;justify-content:space-between;gap:16px;min-height:46px}.check-field input{width:24px;height:24px;min-height:24px;flex:0 0 24px}#manager button{margin:4px}#manager [role=tabpanel]{padding:18px 0}#manager p,details p{white-space:pre-line;overflow-wrap:anywhere}summary{cursor:pointer;min-height:44px;padding:10px 0}a{color:#90f2cc}'''

ASSETS = {"/": (PAGE, "text/html; charset=utf-8"), "/style.css": (STYLE, "text/css; charset=utf-8"),
          "/app.js": (SCRIPT, "text/javascript; charset=utf-8"),
          "/remote.js": (Path(__file__).with_name('remote.js').read_text(encoding='utf-8'), "text/javascript; charset=utf-8"),
          "/manager.js": (Path(__file__).with_name('manager.js').read_text(encoding='utf-8'), "text/javascript; charset=utf-8")}
