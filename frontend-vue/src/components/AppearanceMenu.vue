<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import {
  useThemeStore,
  type AccentChoice,
  type ContentWidthChoice,
  type DensityChoice,
  type DirectionChoice,
  type FontChoice,
  type RadiusChoice,
  type ShellLayoutChoice,
  type SidebarChoice,
  type ThemePreference,
} from '@/stores/theme';

const theme = useThemeStore();

const open = ref(false);
const root = ref<HTMLElement | null>(null);

function toggle() {
  open.value = !open.value;
}
function close() {
  open.value = false;
}

function onDocClick(event: MouseEvent) {
  if (!open.value) return;
  if (root.value && !root.value.contains(event.target as Node)) close();
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && open.value) close();
}

onMounted(() => {
  document.addEventListener('click', onDocClick);
  document.addEventListener('keydown', onKeydown);
});
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick);
  document.removeEventListener('keydown', onKeydown);
});

const modeOptions: Array<{ value: ThemePreference; label: string }> = [
  { value: 'dark', label: '深色' },
  { value: 'light', label: '浅色' },
  { value: 'system', label: '跟随系统' },
];

const accentOptions: Array<{ value: AccentChoice; label: string; swatch: string }> = [
  { value: 'ember', label: '赤橙', swatch: '#cc785c' },
  { value: 'azure', label: '晴蓝', swatch: '#2f6fed' },
  { value: 'emerald', label: '翠绿', swatch: '#1f9d63' },
  { value: 'violet', label: '紫罗兰', swatch: '#7c5cd6' },
  { value: 'rose', label: '玫红', swatch: '#d14f7a' },
];

const fontOptions: Array<{ value: FontChoice; label: string }> = [
  { value: 'sans', label: '默认' },
  { value: 'system', label: '系统' },
  { value: 'serif', label: '衬线' },
  { value: 'rounded', label: '圆体' },
];

const radiusOptions: Array<{ value: RadiusChoice; label: string }> = [
  { value: 'sharp', label: '直角' },
  { value: 'small', label: '小' },
  { value: 'default', label: '默认' },
  { value: 'large', label: '大' },
];

const densityOptions: Array<{ value: DensityChoice; label: string }> = [
  { value: 'compact', label: '紧凑' },
  { value: 'default', label: '标准' },
  { value: 'spacious', label: '宽松' },
];

const sidebarOptions: Array<{ value: SidebarChoice; label: string }> = [
  { value: 'expanded', label: '展开' },
  { value: 'collapsed', label: '收起' },
];

const layoutOptions: Array<{ value: ShellLayoutChoice; label: string }> = [
  { value: 'left', label: '靠左' },
  { value: 'right', label: '靠右' },
];

const directionOptions: Array<{ value: DirectionChoice; label: string }> = [
  { value: 'ltr', label: '从左到右' },
  { value: 'rtl', label: '从右到左' },
];

const contentWidthOptions: Array<{ value: ContentWidthChoice; label: string }> = [
  { value: 'narrow', label: '窄' },
  { value: 'standard', label: '标准' },
  { value: 'wide', label: '宽' },
  { value: 'full', label: '全宽' },
];
</script>

<template>
  <div
    ref="root"
    class="appearance-menu"
  >
    <button
      type="button"
      class="appearance-trigger"
      :class="{ active: open }"
      :aria-expanded="open"
      aria-haspopup="dialog"
      aria-label="外观设置"
      title="外观设置"
      @click.stop="toggle"
    >
      <span
        class="gear"
        aria-hidden="true"
      >⚙</span>
      <em>外观</em>
    </button>

    <div
      v-if="open"
      class="appearance-popover"
      role="dialog"
      aria-label="外观设置面板"
    >
      <header class="pop-head">
        <strong>外观设置</strong>
        <button
          type="button"
          class="reset"
          :disabled="theme.isDefault"
          @click="theme.reset()"
        >
          重置
        </button>
      </header>

      <section class="pop-row">
        <p class="pop-label">主题</p>
        <div class="seg">
          <button
            v-for="opt in modeOptions"
            :key="opt.value"
            type="button"
            :class="{ on: theme.mode === opt.value }"
            :aria-pressed="theme.mode === opt.value"
            @click="theme.setMode(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </section>

      <section class="pop-row">
        <p class="pop-label">颜色</p>
        <div class="swatches">
          <button
            v-for="opt in accentOptions"
            :key="opt.value"
            type="button"
            class="swatch"
            :class="{ on: theme.accent === opt.value }"
            :style="{ '--swatch': opt.swatch }"
            :aria-pressed="theme.accent === opt.value"
            :aria-label="opt.label"
            :title="opt.label"
            @click="theme.setAccent(opt.value)"
          >
            <span aria-hidden="true" />
          </button>
        </div>
      </section>

      <section class="pop-row">
        <p class="pop-label">字体</p>
        <div class="seg">
          <button
            v-for="opt in fontOptions"
            :key="opt.value"
            type="button"
            :class="{ on: theme.font === opt.value }"
            :aria-pressed="theme.font === opt.value"
            @click="theme.setFont(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </section>

      <section class="pop-row">
        <p class="pop-label">圆角</p>
        <div class="seg">
          <button
            v-for="opt in radiusOptions"
            :key="opt.value"
            type="button"
            :class="{ on: theme.radius === opt.value }"
            :aria-pressed="theme.radius === opt.value"
            @click="theme.setRadius(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </section>

      <section class="pop-row">
        <p class="pop-label">密度</p>
        <div class="seg">
          <button
            v-for="opt in densityOptions"
            :key="opt.value"
            type="button"
            :class="{ on: theme.density === opt.value }"
            :aria-pressed="theme.density === opt.value"
            @click="theme.setDensity(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </section>

      <section class="pop-row">
        <p class="pop-label">侧边栏</p>
        <div class="seg">
          <button
            v-for="opt in sidebarOptions"
            :key="opt.value"
            type="button"
            :class="{ on: theme.sidebar === opt.value }"
            :aria-pressed="theme.sidebar === opt.value"
            @click="theme.setSidebar(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </section>

      <section class="pop-row">
        <p class="pop-label">布局</p>
        <div class="seg">
          <button
            v-for="opt in layoutOptions"
            :key="opt.value"
            type="button"
            :class="{ on: theme.layout === opt.value }"
            :aria-pressed="theme.layout === opt.value"
            @click="theme.setLayout(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </section>

      <section class="pop-row">
        <p class="pop-label">方向</p>
        <div class="seg">
          <button
            v-for="opt in directionOptions"
            :key="opt.value"
            type="button"
            :class="{ on: theme.direction === opt.value }"
            :aria-pressed="theme.direction === opt.value"
            @click="theme.setDirection(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </section>

      <section class="pop-row">
        <p class="pop-label">内容宽度</p>
        <div class="seg">
          <button
            v-for="opt in contentWidthOptions"
            :key="opt.value"
            type="button"
            :class="{ on: theme.contentWidth === opt.value }"
            :aria-pressed="theme.contentWidth === opt.value"
            @click="theme.setContentWidth(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.appearance-menu {
  position: relative;
  display: inline-flex;
}

.appearance-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--fin-border);
  border-radius: 999px;
  background: var(--fin-card-soft);
  color: var(--fin-text);
  cursor: pointer;
  font-weight: 800;
  white-space: nowrap;
}

.appearance-trigger.active,
.appearance-trigger:hover {
  border-color: var(--fin-border-strong);
  color: var(--fin-primary);
}

.appearance-trigger .gear {
  font-size: 15px;
  line-height: 1;
}

.appearance-trigger em {
  font-style: normal;
  font-size: 13px;
}

.appearance-popover {
  position: absolute;
  top: calc(100% + 10px);
  inset-inline-end: 0;
  width: 300px;
  max-width: calc(100vw - 32px);
  max-height: min(72vh, 620px);
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border: 1px solid var(--fin-border);
  border-radius: var(--fin-radius-lg);
  background: var(--fin-card);
  box-shadow: var(--fin-shadow);
  z-index: 60;
}

.pop-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.pop-head strong {
  font-size: 15px;
}

.reset {
  border: 1px solid var(--fin-border);
  border-radius: 999px;
  padding: 5px 12px;
  background: transparent;
  color: var(--fin-text-2);
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
}

.reset:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.pop-row {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.pop-label {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--fin-muted);
}

.seg {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 4px;
  border: 1px solid var(--fin-border);
  border-radius: 999px;
  background: var(--fin-card-inset);
}

.seg button {
  flex: 1 1 auto;
  min-width: 48px;
  border: 0;
  border-radius: 999px;
  padding: 7px 10px;
  background: transparent;
  color: var(--fin-text-2);
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.seg button.on {
  background: var(--fin-primary);
  color: var(--fin-bg);
}

.swatches {
  display: flex;
  gap: 10px;
}

.swatch {
  width: 34px;
  height: 34px;
  padding: 0;
  border: 2px solid transparent;
  border-radius: 999px;
  background: transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
}

.swatch span {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: var(--swatch);
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.12);
}

.swatch.on {
  border-color: var(--swatch);
}
</style>
