import { computed, ref } from 'vue';
import { defineStore } from 'pinia';

export type ThemePreference = 'dark' | 'light' | 'system';
export type ResolvedTheme = 'dark' | 'light';

const STORAGE_KEY = 'finsight-theme';
const QUERY = '(prefers-color-scheme: dark)';

function readPreference(): ThemePreference {
  if (typeof window === 'undefined') return 'system';
  const value = window.localStorage.getItem(STORAGE_KEY);
  return value === 'dark' || value === 'light' || value === 'system' ? value : 'system';
}

function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference !== 'system') return preference;
  if (typeof window === 'undefined') return 'dark';
  return window.matchMedia(QUERY).matches ? 'dark' : 'light';
}

function applyTheme(theme: ResolvedTheme): void {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.theme = theme;
}

export const useThemeStore = defineStore('theme', () => {
  const preference = ref<ThemePreference>(readPreference());
  const systemDark = ref(typeof window !== 'undefined' ? window.matchMedia(QUERY).matches : true);
  const initialized = ref(false);

  const resolved = computed<ResolvedTheme>(() => {
    if (preference.value !== 'system') return preference.value;
    return systemDark.value ? 'dark' : 'light';
  });

  function persist(next: ThemePreference): void {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_KEY, next);
  }

  function setPreference(next: ThemePreference): void {
    preference.value = next;
    persist(next);
    applyTheme(resolved.value);
  }

  function cycle(): void {
    const order: ThemePreference[] = ['dark', 'light', 'system'];
    const current = order.indexOf(preference.value);
    setPreference(order[(current + 1) % order.length]);
  }

  function init(): void {
    if (initialized.value || typeof window === 'undefined') {
      applyTheme(resolveTheme(preference.value));
      return;
    }
    const media = window.matchMedia(QUERY);
    systemDark.value = media.matches;
    applyTheme(resolved.value);
    media.addEventListener('change', (event) => {
      systemDark.value = event.matches;
      applyTheme(resolved.value);
    });
    initialized.value = true;
  }

  return {
    preference,
    resolved,
    initialized,
    init,
    setPreference,
    cycle,
  };
});
