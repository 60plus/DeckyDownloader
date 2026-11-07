import fs from 'node:fs/promises';
import path from 'node:path';
import { rollup } from 'rollup';
import { nodeResolve } from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';
import replace from '@rollup/plugin-replace';
import ts from 'typescript';

await fs.mkdir('.work/preview', { recursive: true });
const bundle = await rollup({
  input: 'tests/ui/main.tsx',
  plugins: [
    { name: 'steam-adapter', resolveId(source) { if (source === '@decky/ui') return path.resolve('tests/ui/ui.tsx'); if (source === '@decky/api') return path.resolve('tests/ui/api.ts'); } },
    { name: 'preview-images', async load(id) { if (id.endsWith('.png')) return `export default ${JSON.stringify('data:image/png;base64,' + (await fs.readFile(id)).toString('base64'))}`; } },
    replace({ preventAssignment: true, 'process.env.NODE_ENV': JSON.stringify('production') }),
    { name: 'tsx', transform(code, id) { if (/\.tsx?$/.test(id)) return { code: ts.transpileModule(code, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } }).outputText, map: null }; } },
    nodeResolve({ extensions: ['.js', '.jsx', '.ts', '.tsx'] }), commonjs(),
  ],
});
await bundle.write({ file: '.work/preview/app.js', format: 'iife' });
await bundle.close();
await fs.writeFile('.work/preview/index.html', `<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Decky Downloader · UI preview</title><style>
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 20% 20%,#254547,#101a29 65%);color:#eee;font-family:Arial,sans-serif}.preview-modal-frame{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;padding:0}button,input,select{font:inherit}button{width:100%}.preview-field{display:flex;flex-direction:column;gap:8px;font-size:13px;color:#b4c6bd}.preview-field input,.preview-field select{width:100%;min-height:46px;border:1px solid #40524b;border-radius:8px;background:#1b272b;color:#eee;padding:10px}#root{height:100vh}
</style><div id="root"></div><script src="app.js"></script></html>`);
console.log('UI preview: .work/preview/index.html (mock Steam components and download data)');
