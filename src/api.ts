import { callable } from '@decky/api';
import { useSyncExternalStore } from 'react';

export type Status = 'queued' | 'active' | 'paused' | 'complete' | 'cancelled' | 'error' | 'selecting' | 'seeding' | 'seed_waiting';
export type Job = { id: string; name: string; source: string; kind: string; directory: string; status: Status;
  completed: number; total: number; speed: number; error: string; phase: string; quality: string; created: number;
  file_count: number; selection_mode: string; uploaded: number; upload_speed: number; ratio_limit: number };
export type Settings = { directory: string; parallel: number; limit_kib: number; torrent_ports: string;
  upload_limit_kib: number; bt_max_peers: number; bt_dht: boolean; bt_pex: boolean; bt_lpd: boolean; bt_encryption: boolean; bt_upnp: boolean;
  bt_select_files: boolean; bt_seed: boolean; bt_seed_ratio: number;
  video_auto_update: boolean;
  receiver_mode: 'off' | 'local' | 'lan'; receiver_port: number;
  display: 'auto' | 'window' | 'fullscreen'; language: 'en' | 'pl' };
export type ReceiverStatus = { running: boolean; error: string; port: number; urls: string[]; password_set: boolean };
export type State = { jobs: Job[]; settings: Settings; handheld: boolean; free: number | null;
  runtime: { flatpak: boolean; varia: boolean; aria2: string; video: string; ffmpeg: boolean; video_version?: string; video_managed?: boolean };
  video_install?: { status: string; error: string; version?: string; automatic?: boolean };
  install: { status: string; error: string }; receiver?: ReceiverStatus; network?: { job_id: string; status: string; error?: string; port?: number }[] };
type Reply<T> = { ok: true; data: T } | { ok: false; error: string };
const request = callable<[string, Record<string, unknown>?], Reply<unknown>>('request');
export async function api<T = unknown>(method: string, args?: Record<string, unknown>, timeoutMs?: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const pending = request(method, args);
    const response = await (timeoutMs ? Promise.race([pending, new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error('Request timed out. Refresh to check the result before retrying.')), timeoutMs);
    })]) : pending);
    if (!response.ok) throw new Error(response.error);
    return response.data as T;
  } finally { if (timer) clearTimeout(timer); }
}

let snapshot: { state?: State; error: string } = { error: '' };
let pending: Promise<void> | undefined, timer: ReturnType<typeof setInterval> | undefined;
let disposed = false;
const listeners = new Set<() => void>();
function emit() { if (!disposed) listeners.forEach(listener => listener()); }
export function refresh(): Promise<void> {
  if (pending) return pending;
  pending = api<State>('state').then(state => { snapshot = { state, error: '' }; emit(); })
    .catch(error => { snapshot = { ...snapshot, error: String(error.message || error) }; emit(); })
    .finally(() => { pending = undefined; });
  return pending;
}
export async function mutate(method: string, args?: Record<string, unknown>) {
  const result = await api(method, args);
  if (pending) await pending;
  await refresh();
  return result;
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!timer && !disposed) { void refresh(); timer = setInterval(() => void refresh(), 1200); }
  return () => {
    listeners.delete(listener);
    if (!listeners.size && timer) { clearInterval(timer); timer = undefined; }
  };
}
export function useDownloads() { return useSyncExternalStore(subscribe, () => snapshot); }
export function dispose() { disposed = true; if (timer) clearInterval(timer); timer = undefined; listeners.clear(); }

export function bytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0 B';
  const unit = Math.min(4, Math.floor(Math.log(value) / Math.log(1024)));
  return `${(value / 1024 ** unit).toFixed(unit ? 1 : 0)} ${['B', 'KiB', 'MiB', 'GiB', 'TiB'][unit]}`;
}
export function percent(job: Job) { return job.status === 'complete' ? 100 : job.total ? Math.min(100, Math.max(0, job.completed / job.total * 100)) : 0; }
export function eta(job: Job) {
  if (!job.speed || !job.total || job.completed >= job.total) return '-';
  const seconds = Math.ceil((job.total - job.completed) / job.speed);
  return seconds >= 3600 ? `${Math.floor(seconds / 3600)}h ${Math.ceil(seconds % 3600 / 60)}m` : seconds >= 60 ? `${Math.ceil(seconds / 60)}m` : `${seconds}s`;
}
