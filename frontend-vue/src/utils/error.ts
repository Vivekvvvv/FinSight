export function toFriendlyError(error: unknown, fallback = '操作失败，请稍后重试。'): string {
  const response = (error as { response?: { status?: number; data?: unknown } } | null)?.response;
  const status = response?.status;
  const data = response?.data as { detail?: unknown; message?: unknown; error?: unknown } | string | undefined;

  if (status === 401) return '登录状态已过期，请重新登录后再试。';
  if (status === 403) return '当前账号没有权限执行这个操作。';
  if (status === 404) return '没有找到对应数据，可以换个条件再试。';
  if (status === 429) return '请求太频繁了，请稍等片刻再试。';
  if (status && status >= 500) return '服务暂时不可用，请稍后刷新重试。';

  if (typeof data === 'string' && data.trim()) return data;
  if (data && typeof data === 'object') {
    const serverMessage = [data.detail, data.message, data.error].find((item) => typeof item === 'string' && item.trim());
    if (typeof serverMessage === 'string') return serverMessage;
  }

  const message = error instanceof Error ? error.message : String(error || '');
  if (message.includes('Network Error')) return '网络连接失败，请检查后端服务是否已启动。';
  if (message.toLowerCase().includes('timeout')) return '请求超时，请稍后重试。';

  return fallback;
}

export function reportFriendlyError(error: unknown, fallback?: string): string {
  console.error(error);
  return toFriendlyError(error, fallback);
}
