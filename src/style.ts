export const css = `
.dd-modal { width:min(1140px,94vw)!important; max-width:94vw!important; min-width:0!important; height:min(760px,calc(100vh - 100px))!important; max-height:100%!important; padding:0!important; overflow:hidden!important; border-radius:18px!important; background:#11191f!important; color:#eef4f3!important; box-shadow:0 24px 90px #0009!important; }
.dd-modal .DialogContent_InnerWidth,.dd-modal form { width:100%!important; max-width:none!important; height:100%!important; min-height:0!important; padding:0!important; }
.dd-app { display:flex; flex-direction:column; width:100%; height:100%; min-height:0; color:#eff5f4; font-size:15px; line-height:1.45; }
.dd-app * { box-sizing:border-box; }
.dd-app h1,.dd-app h2,.dd-app h3,.dd-app p { margin:0; }
.dd-header { display:flex; align-items:center; gap:16px; padding:22px 26px 18px; border-bottom:1px solid #ffffff12; flex-shrink:0; }
.dd-header button { width:auto!important; flex-shrink:0; }
.dd-logo { color:#b5f6c3; width:48px; height:48px; background:#b5f6c310; border:1px solid #b5f6c333; border-radius:14px; display:grid; place-items:center; flex-shrink:0; }
.dd-brand { flex:1; min-width:0; }
.dd-brand h1 { font-size:24px; font-weight:650; letter-spacing:-.7px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.dd-subtitle { color:#8c9e9e; font-size:12px; margin-top:3px!important; }
.dd-app button,.dd-sidebar button { min-height:46px!important; min-width:0!important; border-radius:9px!important; padding:10px 16px!important; font-size:14px!important; line-height:1.35!important; color:#e7efed!important; background:#263238!important; border:1px solid #ffffff12!important; box-shadow:none!important; cursor:pointer; touch-action:manipulation; }
.dd-app button:disabled { opacity:.45; cursor:default; }
.dd-app button:hover,.dd-sidebar button:hover { background:#34454b!important; }
.dd-app button:focus-visible,.dd-app button.gpfocus,.dd-app .gpfocus button,.dd-sidebar button.gpfocus { outline:2px solid #b5f6c3!important; outline-offset:2px; background:#344a42!important; }
.dd-app button.dd-primary,.dd-sidebar button.dd-primary { background:#b5f6c3!important; color:#10261b!important; border-color:#b5f6c3!important; font-weight:650!important; }
.dd-app button.dd-primary:hover,.dd-app button.dd-primary.gpfocus { background:#d4ffdd!important; }
.dd-app button.dd-icon { width:46px!important; flex:0 0 46px; padding:6px!important; font-size:24px!important; }
.dd-toolbar { display:flex; align-items:center; gap:8px; padding:14px 24px; flex-shrink:0; }
.dd-toolbar .dd-spacer { flex:1; }
.dd-toolbar button { width:auto!important; white-space:nowrap; }
.dd-body { display:flex; min-height:0; flex:1; overflow:hidden; padding:0 24px 18px; gap:20px; }
.dd-nav { display:flex; flex-direction:column; width:174px; flex:0 0 174px; gap:7px; overflow-y:auto; padding:3px; }
.dd-nav button { display:flex!important; justify-content:space-between; align-items:center; text-align:left!important; width:100%!important; background:transparent!important; border-color:transparent!important; }
.dd-nav button.dd-selected { background:#b5f6c314!important; color:#c0f8cc!important; border-color:#b5f6c333!important; }
.dd-count { font-size:11px; color:#96aaa4; padding-left:8px; }
.dd-nav-note { margin-top:auto; padding:14px 10px 0; color:#7e9490; font-size:11px; line-height:1.6; }
.dd-list { min-height:0; min-width:0; flex:1; display:flex; flex-direction:column; gap:10px; overflow-y:auto; padding:3px 5px 5px 3px; touch-action:pan-y; overscroll-behavior:contain; scrollbar-color:#48615a #15221e; }
.dd-app button.dd-card { display:block!important; width:100%!important; flex-shrink:0; padding:16px 18px!important; text-align:left!important; background:#1b272b!important; border:1px solid #ffffff0d!important; border-radius:12px!important; font-weight:400!important; }
.dd-card-head { display:flex; align-items:center; gap:12px; min-width:0; }
.dd-file-icon { width:38px; height:42px; border-radius:9px; background:#b5f6c30c; display:grid; place-items:center; color:#b5f6c3; flex-shrink:0; font-size:20px; }
.dd-card-title { flex:1; min-width:0; }
.dd-name { display:block; font-weight:600; font-size:15px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.dd-kind { display:block; color:#869b99; font-size:11px; margin-top:2px; }
.dd-badge { color:#9bafa9; font-size:11px; border:1px solid #ffffff14; border-radius:6px; padding:4px 8px; flex-shrink:0; }
.dd-badge.active,.dd-badge.complete,.dd-badge.seeding { color:#b5f6c3; background:#b5f6c30b; }
.dd-badge.error { color:#ffb3a6; background:#ffb3a60c; }
.dd-progress { display:block; position:relative; height:4px; background:#ffffff0b; border-radius:4px; overflow:hidden; margin:13px 0 9px; }
.dd-fill { display:block; height:100%; background:#b5f6c3; border-radius:4px; transition:width .3s linear; }
.dd-progress.paused .dd-fill { background:#b2ad8a; }
.dd-progress.error .dd-fill { background:#d68c7e; }
.dd-progress.indeterminate .dd-fill { width:25%!important; animation:dd-slide 1.8s ease-in-out infinite alternate; }
@keyframes dd-slide { to { transform:translateX(300%); } }
@media (prefers-reduced-motion:reduce) { .dd-fill { transition:none; animation:none!important; } }
.dd-card-meta { display:flex; justify-content:space-between; gap:12px; color:#93a5a1; font-size:11px; font-variant-numeric:tabular-nums; }
.dd-card-meta strong { color:#c6d9cf; font-weight:500; }
.dd-footer { display:flex; align-items:center; gap:16px; flex-shrink:0; padding:11px 26px; border-top:1px solid #ffffff12; color:#8fa39b; font-size:11px; background:#0d1519; }
.dd-footer > span:first-child { flex:1; }
.dd-empty { flex:1; min-height:180px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:14px; text-align:center; padding:24px; color:#8fa49c; }
.dd-empty h2 { color:#e6eee9; font-size:22px; letter-spacing:-.4px; }
.dd-empty p { max-width:420px; line-height:1.6; font-size:14px; }
.dd-empty .dd-hero { color:#b5f6c3; background:#b5f6c30b; width:78px; height:78px; border-radius:24px; display:grid; place-items:center; margin-bottom:5px; }
.dd-empty button { margin-top:8px; width:auto!important; }
.dd-error { margin:10px 24px; padding:12px 16px; border:1px solid #ffb3a633; border-radius:9px; background:#61352730; color:#ffc1b6; white-space:pre-wrap; overflow-wrap:anywhere; font-size:13px; max-height:130px; overflow:auto; flex-shrink:0; }
.dd-notice { padding:12px 16px; border:1px solid #b5f6c333; border-radius:9px; color:#c9e6d0; background:#b5f6c30b; font-size:13px; }
.dd-scroll { flex:1; min-height:0; overflow-y:auto; padding:22px 28px; touch-action:pan-y; overscroll-behavior:contain; }
.dd-form { max-width:760px; margin:0 auto; display:flex; flex-direction:column; gap:18px; padding:3px; }
.dd-form input { min-height:46px!important; font-size:15px!important; }
.dd-form h2 { font-size:20px; }
.dd-help { color:#90a69d; font-size:12px; line-height:1.6; }
.dd-path { overflow-wrap:anywhere; word-break:break-word; font-size:13px; color:#d1e3d6; padding:12px 14px; background:#0e191b; border:1px solid #ffffff12; border-radius:8px; }
.dd-field { display:flex; flex-direction:column; gap:8px; }
.dd-label { color:#b4c6bd; font-size:13px; }
.dd-actions { display:flex; gap:10px; flex-wrap:wrap; }
.dd-actions button { flex:1; min-width:130px!important; width:auto!important; }
.dd-form-footer { flex-shrink:0; display:flex; gap:10px; padding:14px 28px; border-top:1px solid #ffffff12; }
.dd-form-footer button { flex:1; }
.dd-confirm { flex-shrink:0; padding:12px 24px; border-top:1px solid #ffffff12; display:flex; flex-direction:column; gap:8px; }
.dd-confirm h2 { font-size:17px; }
.dd-torrent-files { margin:0 20px; }
.dd-torrent-summary { padding:8px 20px; flex-shrink:0; overflow-wrap:anywhere; font-size:13px; }
@media(max-height:550px) { .dd-torrent-summary .dd-help { display:none; } }
.dd-app button.dd-torrent-file { display:flex; align-items:center; gap:12px; flex-shrink:0; text-align:left!important; overflow-wrap:anywhere; }
.dd-torrent-file small { display:block; color:#90a69d; margin-top:4px; }
.dd-torrent-file[aria-pressed="true"] { border-color:#b5f6c366!important; }
.dd-tabs { flex-wrap:wrap; }
.dd-scroll { scroll-padding-block:12px; }
.dd-form input,.dd-form select,.dd-form [role="combobox"],.dd-form [role="button"] { scroll-margin-top:64px; scroll-margin-bottom:16px; }
.dd-picker-path { margin:0 20px 12px; max-height:80px; overflow:auto; flex-shrink:0; }
.dd-picker-body { display:flex; flex:1; min-height:0; gap:14px; padding:0 20px; }
.dd-places,.dd-folders { display:flex; flex-direction:column; gap:8px; min-height:0; overflow:auto; padding:4px; touch-action:pan-y; }
.dd-places { flex:0 0 32%; min-width:0; }
.dd-folders { flex:1; min-width:0; }
.dd-places h2 { font-size:15px; }
.dd-places button,.dd-folders button { flex-shrink:0; text-align:left!important; overflow-wrap:anywhere; }
.dd-places button span,.dd-places button strong { display:block; }
.dd-places button span { font-size:11px; color:#abc0b5; margin-top:4px; }
.dd-picker-note { padding:8px 24px; flex-shrink:0; }
@media (max-height:550px) { .dd-picker-note { display:none; } .dd-picker-path { max-height:46px; padding:6px 12px; margin-bottom:6px; } }
.dd-stats { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
.dd-stat { padding:16px; border:1px solid #ffffff12; border-radius:10px; background:#1b272b; }
.dd-stat span { display:block; font-size:11px; color:#91a69c; margin-bottom:5px; }
.dd-stat strong { font-weight:500; font-size:18px; }
.dd-runtime { padding:18px; background:#1b272b; border:1px solid #ffffff12; border-radius:12px; display:flex; flex-direction:column; gap:12px; }
.dd-engine { display:flex; justify-content:space-between; gap:10px; font-size:13px; }
.dd-engine span:last-child { color:#b5f6c3; }
.dd-detail-title { overflow-wrap:anywhere; }
.dd-sidebar { display:flex; flex-direction:column; gap:12px; }
.dd-sidebar p { color:#97ada5; font-size:12px; line-height:1.6; margin:0; }
.dd-sidebar-summary { padding:12px; background:#b5f6c30b; border-radius:10px; font-size:13px; line-height:1.8; }
.dd-modal.dd-fullscreen { width:100%!important; max-width:100%!important; height:100%!important; max-height:100%!important; margin:0!important; border-radius:0!important; }
:has(> .dd-modal.dd-fullscreen) { padding:0!important; }
@media (max-width:1300px),(max-height:650px) {
  :has(> .dd-modal.dd-auto) { padding:0!important; }
  .dd-modal.dd-auto { width:100%!important; max-width:100%!important; height:100%!important; max-height:100%!important; margin:0!important; border-radius:0!important; }
  .dd-header { padding:12px 16px; gap:12px; }
  .dd-logo { width:40px; height:40px; border-radius:11px; }
  .dd-brand h1 { font-size:21px; }
  .dd-toolbar { padding:10px 14px; }
  .dd-body { padding:0 14px 12px; gap:12px; }
  .dd-nav { width:150px; flex-basis:150px; }
  .dd-app button.dd-card { padding:13px 14px!important; }
  .dd-footer { padding:8px 16px; }
  .dd-scroll { padding:16px 20px; }
  .dd-form-footer { padding:10px 20px; }
  .dd-nav-note { display:none; }
}
@media (max-width:760px) {
  .dd-subtitle { display:none; }
  .dd-body { flex-direction:column; gap:8px; }
  .dd-nav { width:100%; flex-basis:auto; flex-shrink:0; flex-direction:row; overflow-x:auto; padding:3px; }
  .dd-nav button { width:auto!important; min-width:max-content!important; padding:10px!important; }
  .dd-nav .dd-count { display:none; }
  .dd-toolbar { flex-wrap:wrap; }
  .dd-toolbar button { flex:1; font-size:12px!important; padding:10px!important; }
  .dd-toolbar .dd-spacer { display:none; }
  .dd-card-head { gap:8px; }
  .dd-file-icon { display:none; }
  .dd-badge { font-size:10px; padding:3px 5px; }
  .dd-stats { gap:6px; }
  .dd-stat { padding:10px; }
  .dd-stat strong { font-size:14px; }
}
.dd-modal.dd-keyboard { position:fixed!important; top:var(--dd-keyboard-top)!important; bottom:auto!important; left:2vw!important; width:96vw!important; max-width:96vw!important; height:var(--dd-keyboard-height)!important; max-height:var(--dd-keyboard-height)!important; margin:0!important; border-radius:8px!important; }
.dd-keyboard .dd-header { padding:4px 12px; }
.dd-keyboard .dd-header .dd-logo,.dd-keyboard .dd-header .dd-subtitle,.dd-keyboard .dd-footer { display:none; }
.dd-keyboard .dd-brand h1 { font-size:16px; }
.dd-keyboard .dd-scroll { padding:10px 16px; }
.dd-keyboard .dd-form-footer { padding:6px 16px; }
`;
