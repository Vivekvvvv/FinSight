// 运行时配置: API base url.
// 当前默认走 Python FastAPI 8000; 容器内由 nginx 同源反代到 backend:8000。
const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

function normalize(value: string): string {
  return value.replace(/\/+$/, '');
}

function resolveBrowserDefault(): string {
  if (typeof window === 'undefined') return DEFAULT_API_BASE_URL;
  const { protocol, hostname, port } = window.location;
  if (port === '5173' || port === '5174') {
    return `${protocol}//${hostname}:8000`;
  }
  return normalize(`${protocol}//${hostname}${port ? `:${port}` : ''}`);
}

export const API_BASE_URL: string = (() => {
  const raw = (import.meta.env.VITE_API_BASE_URL ?? '').trim();
  return raw ? normalize(raw) : resolveBrowserDefault();
})();
