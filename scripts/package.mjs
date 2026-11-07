import { spawnSync } from 'node:child_process';
const candidates = process.env.PYTHON ? [process.env.PYTHON] : ['python3', 'python'];
let found = false;
for (const executable of candidates) {
  const check = spawnSync(executable, ['--version'], { stdio: 'ignore', windowsHide: true });
  if (check.status !== 0) continue;
  found = true;
  const result = spawnSync(executable, ['scripts/package.py'], { stdio: 'inherit', windowsHide: true });
  process.exitCode = result.status ?? 1;
  break;
}
if (!found) throw new Error('Python 3 is required. Set PYTHON to its executable or run python3 scripts/package.py.');
