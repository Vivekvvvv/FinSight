import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { apiClient } from '@/api/client';
import type { MeResponse } from '@/api/types';

const USER_KEY = 'finsight-user-id';
const SESSION_KEY = 'finsight-session-id';
const EMAIL_KEY = 'finsight-subscription-email';
const TOKEN_KEY = 'finsight-access-token';

function readStorage(key: string, fallback = ''): string {
  if (typeof window === 'undefined') return fallback;
  return window.localStorage.getItem(key) || fallback;
}

function writeStorage(key: string, value: string): void {
  if (typeof window === 'undefined') return;
  const normalized = String(value || '').trim();
  if (!normalized) {
    window.localStorage.removeItem(key);
    return;
  }
  window.localStorage.setItem(key, normalized);
}

function normalizeUserId(value: string): string {
  const normalized = String(value || '').trim();
  return normalized || 'default_user';
}

function normalizeSessionId(value: string): string {
  const normalized = String(value || '').trim();
  return normalized || 'public:anonymous:vue-dev';
}

function buildUserSessionId(userId: string): string {
  return `user:${normalizeUserId(userId)}:vue-shadow`;
}

function resolveBootstrapError(error: unknown): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const status = Number((error as { response?: { status?: number } }).response?.status || 0);
    if (status === 404) {
      return '当前 API 未暴露 /api/me，已回退到本地身份骨架。';
    }
  }
  return error instanceof Error ? error.message : String(error);
}

export const useIdentityStore = defineStore('identity', () => {
  const userId = ref(readStorage(USER_KEY, 'default_user'));
  const sessionId = ref(readStorage(SESSION_KEY, 'public:anonymous:vue-dev'));
  const email = ref(readStorage(EMAIL_KEY));
  const accessToken = ref(readStorage(TOKEN_KEY));
  const mode = ref<'local' | 'remote'>('local');
  const authType = ref('local');
  const role = ref('dev');
  const ready = ref(false);
  const loading = ref(false);
  const error = ref<string | null>(null);

  function setUserId(value: string): void {
    userId.value = normalizeUserId(value);
    writeStorage(USER_KEY, userId.value);
  }

  function setSessionId(value: string): void {
    sessionId.value = normalizeSessionId(value);
    writeStorage(SESSION_KEY, sessionId.value);
  }

  function setEmail(value: string): void {
    email.value = String(value || '').trim();
    writeStorage(EMAIL_KEY, email.value);
  }

  function setAccessToken(value: string): void {
    accessToken.value = String(value || '').trim();
    writeStorage(TOKEN_KEY, accessToken.value);
  }

  function applyRemoteIdentity(payload: MeResponse): void {
    mode.value = 'remote';
    authType.value = String(payload.auth_type || 'remote');
    role.value = String(payload.role || 'user');
    setUserId(payload.user_id || userId.value);
    if (payload.email) setEmail(payload.email);
    if (sessionId.value.startsWith('public:anonymous:') || sessionId.value === 'public:anonymous:vue-dev') {
      setSessionId(buildUserSessionId(payload.user_id || userId.value));
    }
  }

  async function bootstrap(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const payload = await apiClient.getMe();
      applyRemoteIdentity(payload);
    } catch (e) {
      mode.value = 'local';
      authType.value = 'local';
      role.value = 'dev';
      error.value = resolveBootstrapError(e);
    } finally {
      ready.value = true;
      loading.value = false;
    }
  }

  function saveLocalIdentity(payload: {
    userId: string;
    sessionId: string;
    email: string;
    accessToken: string;
  }): void {
    setUserId(payload.userId);
    setSessionId(payload.sessionId);
    setEmail(payload.email);
    setAccessToken(payload.accessToken);
    mode.value = 'local';
    authType.value = accessToken.value ? 'bearer_local' : 'local';
  }

  const summary = computed(() => {
    const primary = email.value || userId.value;
    return `${primary} · ${sessionId.value}`;
  });

  const isGuest = computed(() => role.value === 'guest');
  const isAdmin = computed(() => role.value === 'admin' || role.value === 'internal');

  async function logout(): Promise<void> {
    try {
      await apiClient.logout();
    } catch {
      // ignore
    }
    // 清空本地存储
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(USER_KEY);
      window.localStorage.removeItem(SESSION_KEY);
      window.localStorage.removeItem(EMAIL_KEY);
      window.localStorage.removeItem(TOKEN_KEY);
    }
    userId.value = 'default_user';
    sessionId.value = 'public:anonymous:vue-dev';
    email.value = '';
    accessToken.value = '';
    mode.value = 'local';
    authType.value = 'local';
    role.value = 'guest';
    ready.value = false;
  }

  return {
    userId,
    sessionId,
    email,
    accessToken,
    mode,
    authType,
    role,
    ready,
    loading,
    error,
    summary,
    isGuest,
    isAdmin,
    bootstrap,
    saveLocalIdentity,
    logout,
    setUserId,
    setSessionId,
    setEmail,
    setAccessToken,
  };
});
