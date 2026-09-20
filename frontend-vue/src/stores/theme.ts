import { computed, ref } from 'vue';
import { defineStore } from 'pinia';

export type ThemePreference = 'dark' | 'light' | 'system';
export type ResolvedTheme = 'dark' | 'light';
export type AccentChoice =
  | 'default'
  | 'anthropic'
  | 'bigfont'
  | 'midnight'
  | 'rosegarden'
  | 'lake'
  | 'sunset'
  | 'forest'
  | 'seabreeze'
  | 'lavender';
export type FontChoice = 'auto' | 'sans' | 'serif';
export type RadiusChoice = 'auto' | '0' | '0.3' | '0.5' | '0.75' | '1.0';
export type DensityChoice = 'compact' | 'default' | 'spacious' | 'xl';
export type SidebarChoice = 'inset' | 'floating' | 'rail';
export type ShellLayoutChoice = 'default' | 'compact' | 'full';
export type DirectionChoice = 'ltr' | 'rtl';
export type ContentWidthChoice = 'full' | 'centered';

export interface AppearanceState {
  mode: ThemePreference;
  accent: AccentChoice;
  font: FontChoice;
  radius: RadiusChoice;
  density: DensityChoice;
  sidebar: SidebarChoice;
  layout: ShellLayoutChoice;
  direction: DirectionChoice;
  contentWidth: ContentWidthChoice;
}

const STORAGE_KEY = 'finsight-appearance';
const LEGACY_THEME_KEY = 'finsight-theme';
const QUERY = '(prefers-color-scheme: dark)';

export const DEFAULT_APPEARANCE: AppearanceState = {
  mode: 'system',
  accent: 'default',
  font: 'auto',
  radius: 'auto',
  density: 'default',
  sidebar: 'inset',
  layout: 'default',
  direction: 'ltr',
  contentWidth: 'full',
};

const MODES: ThemePreference[] = ['dark', 'light', 'system'];
const ACCENTS: AccentChoice[] = [
  'default', 'anthropic', 'bigfont', 'midnight', 'rosegarden',
  'lake', 'sunset', 'forest', 'seabreeze', 'lavender',
];
const FONTS: FontChoice[] = ['auto', 'sans', 'serif'];
const RADII: RadiusChoice[] = ['auto', '0', '0.3', '0.5', '0.75', '1.0'];
const DENSITIES: DensityChoice[] = ['compact', 'default', 'spacious', 'xl'];
const SIDEBARS: SidebarChoice[] = ['inset', 'floating', 'rail'];
const LAYOUTS: ShellLayoutChoice[] = ['default', 'compact', 'full'];
const DIRECTIONS: DirectionChoice[] = ['ltr', 'rtl'];
const CONTENT_WIDTHS: ContentWidthChoice[] = ['full', 'centered'];

function pick<T>(candidate: unknown, allowed: T[], fallback: T): T {
  return allowed.includes(candidate as T) ? (candidate as T) : fallback;
}

function readAppearance(): AppearanceState {
  if (typeof window === 'undefined') return { ...DEFAULT_APPEARANCE };
  const state: AppearanceState = { ...DEFAULT_APPEARANCE };

  // 迁移旧的单一主题偏好键，保留用户已有选择。
  const legacy = window.localStorage.getItem(LEGACY_THEME_KEY);
  if (legacy === 'dark' || legacy === 'light' || legacy === 'system') {
    state.mode = legacy;
  }

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as Partial<AppearanceState>;
      state.mode = pick(parsed.mode, MODES, state.mode);
      state.accent = pick(parsed.accent, ACCENTS, state.accent);
      state.font = pick(parsed.font, FONTS, state.font);
      state.radius = pick(parsed.radius, RADII, state.radius);
      state.density = pick(parsed.density, DENSITIES, state.density);
      state.sidebar = pick(parsed.sidebar, SIDEBARS, state.sidebar);
      state.layout = pick(parsed.layout, LAYOUTS, state.layout);
      state.direction = pick(parsed.direction, DIRECTIONS, state.direction);
      state.contentWidth = pick(parsed.contentWidth, CONTENT_WIDTHS, state.contentWidth);
    } catch {
      // 损坏的偏好不应阻断渲染，回退默认值即可（非用户业务数据，无需备份）。
    }
  }
  return state;
}

export const useThemeStore = defineStore('theme', () => {
  const persisted = readAppearance();
  const mode = ref<ThemePreference>(persisted.mode);
  const accent = ref<AccentChoice>(persisted.accent);
  const font = ref<FontChoice>(persisted.font);
  const radius = ref<RadiusChoice>(persisted.radius);
  const density = ref<DensityChoice>(persisted.density);
  const sidebar = ref<SidebarChoice>(persisted.sidebar);
  const layout = ref<ShellLayoutChoice>(persisted.layout);
  const direction = ref<DirectionChoice>(persisted.direction);
  const contentWidth = ref<ContentWidthChoice>(persisted.contentWidth);

  const systemDark = ref(typeof window !== 'undefined' ? window.matchMedia(QUERY).matches : true);
  const initialized = ref(false);

  const resolved = computed<ResolvedTheme>(() => {
    if (mode.value !== 'system') return mode.value;
    return systemDark.value ? 'dark' : 'light';
  });

  // 向后兼容旧字段名 preference（App.vue / 图表组件在用 resolved / preference）。
  const preference = mode;

  function snapshot(): AppearanceState {
    return {
      mode: mode.value,
      accent: accent.value,
      font: font.value,
      radius: radius.value,
      density: density.value,
      sidebar: sidebar.value,
      layout: layout.value,
      direction: direction.value,
      contentWidth: contentWidth.value,
    };
  }

  function persist(): void {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot()));
    // 保留旧键，避免尚未升级的其它入口读到空值。
    window.localStorage.setItem(LEGACY_THEME_KEY, mode.value);
  }

  function apply(): void {
    if (typeof document === 'undefined') return;
    const root = document.documentElement;
    root.dataset.theme = resolved.value;
    root.dataset.accent = accent.value;
    root.dataset.font = font.value;
    root.dataset.radius = radius.value;
    root.dataset.density = density.value;
    root.dataset.sidebar = sidebar.value;
    root.dataset.shellLayout = layout.value;
    root.dataset.contentWidth = contentWidth.value;
    root.dir = direction.value;
  }

  function commit(): void {
    apply();
    persist();
  }

  function setMode(next: ThemePreference): void {
    mode.value = pick(next, MODES, mode.value);
    commit();
  }
  function setAccent(next: AccentChoice): void {
    accent.value = pick(next, ACCENTS, accent.value);
    commit();
  }
  function setFont(next: FontChoice): void {
    font.value = pick(next, FONTS, font.value);
    commit();
  }
  function setRadius(next: RadiusChoice): void {
    radius.value = pick(next, RADII, radius.value);
    commit();
  }
  function setDensity(next: DensityChoice): void {
    density.value = pick(next, DENSITIES, density.value);
    commit();
  }
  function setSidebar(next: SidebarChoice): void {
    sidebar.value = pick(next, SIDEBARS, sidebar.value);
    commit();
  }
  function setLayout(next: ShellLayoutChoice): void {
    layout.value = pick(next, LAYOUTS, layout.value);
    commit();
  }
  function setDirection(next: DirectionChoice): void {
    direction.value = pick(next, DIRECTIONS, direction.value);
    commit();
  }
  function setContentWidth(next: ContentWidthChoice): void {
    contentWidth.value = pick(next, CONTENT_WIDTHS, contentWidth.value);
    commit();
  }

  function reset(): void {
    mode.value = DEFAULT_APPEARANCE.mode;
    accent.value = DEFAULT_APPEARANCE.accent;
    font.value = DEFAULT_APPEARANCE.font;
    radius.value = DEFAULT_APPEARANCE.radius;
    density.value = DEFAULT_APPEARANCE.density;
    sidebar.value = DEFAULT_APPEARANCE.sidebar;
    layout.value = DEFAULT_APPEARANCE.layout;
    direction.value = DEFAULT_APPEARANCE.direction;
    contentWidth.value = DEFAULT_APPEARANCE.contentWidth;
    commit();
  }

  const isDefault = computed(() =>
    mode.value === DEFAULT_APPEARANCE.mode
    && accent.value === DEFAULT_APPEARANCE.accent
    && font.value === DEFAULT_APPEARANCE.font
    && radius.value === DEFAULT_APPEARANCE.radius
    && density.value === DEFAULT_APPEARANCE.density
    && sidebar.value === DEFAULT_APPEARANCE.sidebar
    && layout.value === DEFAULT_APPEARANCE.layout
    && direction.value === DEFAULT_APPEARANCE.direction
    && contentWidth.value === DEFAULT_APPEARANCE.contentWidth);

  // 向后兼容旧 API 名。
  function setPreference(next: ThemePreference): void {
    setMode(next);
  }
  function cycle(): void {
    const current = MODES.indexOf(mode.value);
    setMode(MODES[(current + 1) % MODES.length]);
  }

  function init(): void {
    if (initialized.value || typeof window === 'undefined') {
      apply();
      return;
    }
    const media = window.matchMedia(QUERY);
    systemDark.value = media.matches;
    apply();
    media.addEventListener('change', (event) => {
      systemDark.value = event.matches;
      apply();
    });
    initialized.value = true;
  }

  return {
    // state
    mode,
    preference,
    resolved,
    accent,
    font,
    radius,
    density,
    sidebar,
    layout,
    direction,
    contentWidth,
    initialized,
    isDefault,
    // actions
    init,
    setMode,
    setAccent,
    setFont,
    setRadius,
    setDensity,
    setSidebar,
    setLayout,
    setDirection,
    setContentWidth,
    reset,
    // legacy
    setPreference,
    cycle,
  };
});
