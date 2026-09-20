<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
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
function show() {
  open.value = true;
}
function close() {
  open.value = false;
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && open.value) close();
}

onMounted(() => document.addEventListener('keydown', onKeydown));
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown));

// 打开时锁定 body 滚动，关闭时恢复。
watch(open, (value) => {
  if (typeof document === 'undefined') return;
  document.body.style.overflow = value ? 'hidden' : '';
});

const modeOptions: Array<{ value: ThemePreference; label: string }> = [
  { value: 'system', label: '系统' },
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
];

const accentOptions: Array<{ value: AccentChoice; label: string; gradient: string }> = [
  { value: 'default', label: '默认', gradient: 'linear-gradient(135deg,#f43f5e,#f59e0b 30%,#22c55e 55%,#3b82f6 78%,#a855f7)' },
  { value: 'anthropic', label: 'Anthropic', gradient: 'linear-gradient(160deg,#f3d9c9,#cc785c)' },
  { value: 'bigfont', label: '超大字体简易', gradient: 'linear-gradient(180deg,#111827,#e5e7eb)' },
  { value: 'midnight', label: '暗夜', gradient: 'linear-gradient(160deg,#475569,#0f172a)' },
  { value: 'rosegarden', label: '玫瑰花园', gradient: 'linear-gradient(160deg,#f472b6,#db2777)' },
  { value: 'lake', label: '湖光', gradient: 'linear-gradient(160deg,#2dd4bf,#0d9488)' },
  { value: 'sunset', label: '日落霞光', gradient: 'linear-gradient(160deg,#fb923c,#ea580c)' },
  { value: 'forest', label: '森林低语', gradient: 'linear-gradient(160deg,#134e4a,#15803d)' },
  { value: 'seabreeze', label: '海风', gradient: 'linear-gradient(160deg,#3b82f6,#1d4ed8)' },
  { value: 'lavender', label: '薰衣草梦', gradient: 'linear-gradient(160deg,#8b5cf6,#a78bfa)' },
];

const fontOptions: Array<{ value: FontChoice; label: string; family: string }> = [
  { value: 'auto', label: 'Auto', family: 'var(--fin-font)' },
  { value: 'sans', label: 'Sans', family: 'system-ui, sans-serif' },
  { value: 'serif', label: 'Serif', family: 'Georgia, "Songti SC", serif' },
];

const radiusOptions: Array<{ value: RadiusChoice; label: string; px: string }> = [
  { value: 'auto', label: 'Auto', px: '8px' },
  { value: '0', label: '0', px: '0px' },
  { value: '0.3', label: '0.3', px: '5px' },
  { value: '0.5', label: '0.5', px: '9px' },
  { value: '0.75', label: '0.75', px: '14px' },
  { value: '1.0', label: '1.0', px: '20px' },
];

const densityOptions: Array<{ value: DensityChoice; label: string; lines: number; gap: number }> = [
  { value: 'compact', label: '紧凑', lines: 5, gap: 4 },
  { value: 'default', label: '默认', lines: 4, gap: 7 },
  { value: 'spacious', label: '宽松', lines: 3, gap: 11 },
  { value: 'xl', label: '超大', lines: 2, gap: 16 },
];

const sidebarOptions: Array<{ value: SidebarChoice; label: string }> = [
  { value: 'inset', label: '内嵌' },
  { value: 'floating', label: '浮动' },
  { value: 'rail', label: '侧边栏' },
];

const layoutOptions: Array<{ value: ShellLayoutChoice; label: string }> = [
  { value: 'default', label: '默认' },
  { value: 'compact', label: '紧凑' },
  { value: 'full', label: '全屏布局' },
];

const contentWidthOptions: Array<{ value: ContentWidthChoice; label: string }> = [
  { value: 'full', label: '全宽' },
  { value: 'centered', label: '居中' },
];

const directionOptions: Array<{ value: DirectionChoice; label: string }> = [
  { value: 'ltr', label: '从左到右' },
  { value: 'rtl', label: '从右到左' },
];
</script>

<template>
  <div class="appearance-menu">
    <button
      type="button"
      class="appearance-trigger"
      :class="{ active: open }"
      aria-haspopup="dialog"
      aria-label="外观设置"
      title="外观设置"
      @click="show"
    >
      <span
        class="gear"
        aria-hidden="true"
      >⚙</span>
      <em>外观</em>
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        class="appearance-overlay"
        @click.self="close"
      >
        <div
          class="appearance-modal"
          role="dialog"
          aria-modal="true"
          aria-label="主题设置"
        >
          <header class="modal-head">
            <div>
              <strong>主题设置</strong>
              <p>调整外观和布局以适应您的偏好。</p>
            </div>
            <button
              type="button"
              class="close"
              aria-label="关闭"
              @click="close"
            >
              ✕
            </button>
          </header>

          <div class="modal-body">
            <!-- 主题 -->
            <section class="group">
              <h3>主题</h3>
              <div class="cards cols-3">
                <button
                  v-for="opt in modeOptions"
                  :key="opt.value"
                  type="button"
                  class="card"
                  :class="{ on: theme.mode === opt.value }"
                  :aria-pressed="theme.mode === opt.value"
                  @click="theme.setMode(opt.value)"
                >
                  <span
                    class="preview mock"
                    :class="`mock-${opt.value}`"
                    aria-hidden="true"
                  >
                    <span class="mock-side" />
                    <span class="mock-main">
                      <span class="mock-bar" />
                      <span class="mock-dot" />
                    </span>
                  </span>
                  <span class="card-label">{{ opt.label }}</span>
                  <span
                    v-if="theme.mode === opt.value"
                    class="check"
                    aria-hidden="true"
                  >✓</span>
                </button>
              </div>
            </section>

            <!-- 颜色预设 -->
            <section class="group">
              <h3>颜色预设</h3>
              <div class="cards cols-4">
                <button
                  v-for="opt in accentOptions"
                  :key="opt.value"
                  type="button"
                  class="card"
                  :class="{ on: theme.accent === opt.value }"
                  :aria-pressed="theme.accent === opt.value"
                  @click="theme.setAccent(opt.value)"
                >
                  <span
                    class="preview swatch"
                    :style="{ backgroundImage: opt.gradient }"
                    aria-hidden="true"
                  />
                  <span class="card-label">{{ opt.label }}</span>
                  <span
                    v-if="theme.accent === opt.value"
                    class="check"
                    aria-hidden="true"
                  >✓</span>
                </button>
              </div>
            </section>

            <!-- 字体 -->
            <section class="group">
              <h3>字体</h3>
              <div class="cards cols-3">
                <button
                  v-for="opt in fontOptions"
                  :key="opt.value"
                  type="button"
                  class="card"
                  :class="{ on: theme.font === opt.value }"
                  :aria-pressed="theme.font === opt.value"
                  @click="theme.setFont(opt.value)"
                >
                  <span
                    class="preview aa"
                    :style="{ fontFamily: opt.family }"
                    aria-hidden="true"
                  >Aa</span>
                  <span class="card-label">{{ opt.label }}</span>
                  <span
                    v-if="theme.font === opt.value"
                    class="check"
                    aria-hidden="true"
                  >✓</span>
                </button>
              </div>
            </section>

            <!-- 圆角 -->
            <section class="group">
              <h3>圆角</h3>
              <div class="cards cols-6">
                <button
                  v-for="opt in radiusOptions"
                  :key="opt.value"
                  type="button"
                  class="card"
                  :class="{ on: theme.radius === opt.value }"
                  :aria-pressed="theme.radius === opt.value"
                  @click="theme.setRadius(opt.value)"
                >
                  <span
                    class="preview radius"
                    aria-hidden="true"
                  >
                    <span
                      class="radius-box"
                      :style="{ borderTopLeftRadius: opt.px }"
                    />
                  </span>
                  <span class="card-label">{{ opt.label }}</span>
                  <span
                    v-if="theme.radius === opt.value"
                    class="check"
                    aria-hidden="true"
                  >✓</span>
                </button>
              </div>
            </section>

            <!-- 密度 -->
            <section class="group">
              <h3>密度</h3>
              <div class="cards cols-4">
                <button
                  v-for="opt in densityOptions"
                  :key="opt.value"
                  type="button"
                  class="card"
                  :class="{ on: theme.density === opt.value }"
                  :aria-pressed="theme.density === opt.value"
                  @click="theme.setDensity(opt.value)"
                >
                  <span
                    class="preview lines"
                    :style="{ gap: `${opt.gap}px` }"
                    aria-hidden="true"
                  >
                    <span
                      v-for="n in opt.lines"
                      :key="n"
                    />
                  </span>
                  <span class="card-label">{{ opt.label }}</span>
                  <span
                    v-if="theme.density === opt.value"
                    class="check"
                    aria-hidden="true"
                  >✓</span>
                </button>
              </div>
            </section>

            <!-- 侧边栏 -->
            <section class="group">
              <h3>侧边栏</h3>
              <div class="cards cols-3">
                <button
                  v-for="opt in sidebarOptions"
                  :key="opt.value"
                  type="button"
                  class="card"
                  :class="{ on: theme.sidebar === opt.value }"
                  :aria-pressed="theme.sidebar === opt.value"
                  @click="theme.setSidebar(opt.value)"
                >
                  <span
                    class="preview mock"
                    :class="`sb-${opt.value}`"
                    aria-hidden="true"
                  >
                    <span class="mock-side" />
                    <span class="mock-main"><span class="mock-bar" /></span>
                  </span>
                  <span class="card-label">{{ opt.label }}</span>
                  <span
                    v-if="theme.sidebar === opt.value"
                    class="check"
                    aria-hidden="true"
                  >✓</span>
                </button>
              </div>
            </section>

            <!-- 布局 -->
            <section class="group">
              <h3>布局</h3>
              <div class="cards cols-3">
                <button
                  v-for="opt in layoutOptions"
                  :key="opt.value"
                  type="button"
                  class="card"
                  :class="{ on: theme.layout === opt.value }"
                  :aria-pressed="theme.layout === opt.value"
                  @click="theme.setLayout(opt.value)"
                >
                  <span
                    class="preview mock"
                    :class="`ly-${opt.value}`"
                    aria-hidden="true"
                  >
                    <span class="mock-side" />
                    <span class="mock-main">
                      <span class="mock-bar" />
                      <span class="mock-dot" />
                    </span>
                  </span>
                  <span class="card-label">{{ opt.label }}</span>
                  <span
                    v-if="theme.layout === opt.value"
                    class="check"
                    aria-hidden="true"
                  >✓</span>
                </button>
              </div>
            </section>

            <!-- 内容宽度 -->
            <section class="group">
              <h3>内容宽度</h3>
              <div class="cards cols-2">
                <button
                  v-for="opt in contentWidthOptions"
                  :key="opt.value"
                  type="button"
                  class="card"
                  :class="{ on: theme.contentWidth === opt.value }"
                  :aria-pressed="theme.contentWidth === opt.value"
                  @click="theme.setContentWidth(opt.value)"
                >
                  <span
                    class="preview cw"
                    :class="`cw-${opt.value}`"
                    aria-hidden="true"
                  >
                    <span /><span /><span />
                  </span>
                  <span class="card-label">{{ opt.label }}</span>
                  <span
                    v-if="theme.contentWidth === opt.value"
                    class="check"
                    aria-hidden="true"
                  >✓</span>
                </button>
              </div>
            </section>

            <!-- 方向 -->
            <section class="group">
              <h3>方向</h3>
              <div class="cards cols-2">
                <button
                  v-for="opt in directionOptions"
                  :key="opt.value"
                  type="button"
                  class="card"
                  :class="{ on: theme.direction === opt.value }"
                  :aria-pressed="theme.direction === opt.value"
                  @click="theme.setDirection(opt.value)"
                >
                  <span
                    class="preview mock"
                    :class="`dir-${opt.value}`"
                    aria-hidden="true"
                  >
                    <span class="mock-side" />
                    <span class="mock-main"><span class="mock-bar" /></span>
                  </span>
                  <span class="card-label">{{ opt.label }}</span>
                  <span
                    v-if="theme.direction === opt.value"
                    class="check"
                    aria-hidden="true"
                  >✓</span>
                </button>
              </div>
            </section>
          </div>

          <footer class="modal-foot">
            <button
              type="button"
              class="reset"
              :disabled="theme.isDefault"
              @click="theme.reset()"
            >
              重置为默认
            </button>
            <button
              type="button"
              class="done"
              @click="close"
            >
              完成
            </button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.appearance-menu {
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

/* ── modal ─────────────────────────────────────────────── */
.appearance-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: grid;
  place-items: center;
  padding: 24px;
  background: var(--fin-overlay);
  backdrop-filter: blur(2px);
}

.appearance-modal {
  width: min(680px, 100%);
  max-height: min(86vh, 900px);
  display: flex;
  flex-direction: column;
  background: var(--fin-card);
  border: 1px solid var(--fin-border);
  border-radius: var(--fin-radius-lg);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.28);
  overflow: hidden;
}

.modal-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 22px 24px 16px;
  border-bottom: 1px solid var(--fin-border);
}
.modal-head strong {
  font-size: 19px;
  font-weight: 800;
}
.modal-head p {
  margin: 4px 0 0;
  color: var(--fin-muted);
  font-size: 13px;
}
.close {
  border: 0;
  background: transparent;
  color: var(--fin-muted);
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  padding: 6px;
  border-radius: 8px;
}
.close:hover {
  color: var(--fin-text);
  background: var(--fin-card-inset);
}

.modal-body {
  overflow-y: auto;
  padding: 8px 24px 20px;
}

.group {
  padding: 16px 0;
  border-bottom: 1px solid var(--fin-border);
}
.group:last-child {
  border-bottom: 0;
}
.group h3 {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.02em;
  color: var(--fin-text-2);
}

.cards {
  display: grid;
  gap: 12px;
}
.cols-2 { grid-template-columns: repeat(2, 1fr); }
.cols-3 { grid-template-columns: repeat(3, 1fr); }
.cols-4 { grid-template-columns: repeat(4, 1fr); }
.cols-6 { grid-template-columns: repeat(6, 1fr); }

.card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--fin-text);
  cursor: pointer;
  text-align: center;
}

.preview {
  position: relative;
  width: 100%;
  border: 2px solid var(--fin-border);
  border-radius: 12px;
  overflow: hidden;
  transition: border-color 0.16s var(--fin-ease), box-shadow 0.16s var(--fin-ease);
}
.card:hover .preview {
  border-color: var(--fin-border-strong);
}
.card.on .preview {
  border-color: var(--fin-primary);
  box-shadow: 0 0 0 3px var(--fin-primary-soft);
}

.card-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--fin-text-2);
}
.card.on .card-label {
  color: var(--fin-text);
}

.check {
  position: absolute;
  top: -7px;
  inset-inline-end: -7px;
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: var(--fin-primary);
  color: #fff;
  font-size: 11px;
  font-weight: 900;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
}

/* ── preview: 主题 / 侧边栏 / 布局 / 方向 mock ─────────────── */
.mock {
  aspect-ratio: 16 / 10;
  display: flex;
  padding: 8px;
  gap: 6px;
  background: #f4f5f7;
}
.mock-side {
  width: 26%;
  border-radius: 5px;
  background: #c7cbd1;
}
.mock-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.mock-bar {
  height: 34%;
  border-radius: 5px;
  background: #dfe2e7;
}
.mock-dot {
  flex: 1;
  border-radius: 5px;
  background: #dfe2e7;
}

.mock-light { background: #f4f5f7; }
.mock-light .mock-side { background: #cfd3da; }
.mock-dark { background: #1f2430; }
.mock-dark .mock-side { background: #3a4152; }
.mock-dark .mock-bar,
.mock-dark .mock-dot { background: #333a49; }
.mock-system {
  background: linear-gradient(120deg, #f4f5f7 0 50%, #1f2430 50% 100%);
}
.mock-system .mock-side { background: linear-gradient(120deg, #cfd3da 0 55%, #3a4152 55% 100%); }
.mock-system .mock-bar,
.mock-system .mock-dot { background: linear-gradient(120deg, #dfe2e7 0 45%, #333a49 45% 100%); }

/* 选中项预览用品牌色点缀 */
.card.on .mock-side { background: var(--fin-primary); }

/* 侧边栏形态 */
.sb-inset .mock-side { background: var(--fin-primary); }
.sb-floating {
  padding: 10px;
  gap: 8px;
}
.sb-floating .mock-side {
  border-radius: 7px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
  background: var(--fin-primary);
}
.sb-rail .mock-side { width: 12%; background: #9aa0aa; }
.card.on .sb-rail .mock-side { background: var(--fin-primary); }

/* 布局形态 */
.ly-default .mock-side { background: var(--fin-primary); }
.ly-compact .mock-side { width: 12%; }
.ly-compact { padding: 6px; gap: 4px; }
.ly-full .mock-side { width: 8%; }
.ly-full { padding: 5px; gap: 4px; }

/* 方向：从右到左镜像 */
.dir-rtl { flex-direction: row-reverse; }
.card.on .dir-ltr .mock-side,
.card.on .dir-rtl .mock-side { background: var(--fin-primary); }

/* ── preview: 颜色 ─────────────── */
.swatch {
  aspect-ratio: 16 / 10;
  background-size: cover;
  background-position: center;
  border-color: rgba(0, 0, 0, 0.08);
}

/* ── preview: 字体 ─────────────── */
.aa {
  aspect-ratio: 16 / 10;
  display: grid;
  place-items: center;
  font-size: 26px;
  font-weight: 700;
  color: var(--fin-text);
  background: var(--fin-card-inset);
}

/* ── preview: 圆角 ─────────────── */
.radius {
  aspect-ratio: 16 / 10;
  display: grid;
  place-items: center;
  background: var(--fin-card-inset);
}
.radius-box {
  width: 46%;
  height: 62%;
  border: 2px solid var(--fin-primary);
  border-inline-end: 0;
  border-bottom: 0;
}

/* ── preview: 密度 ─────────────── */
.lines {
  aspect-ratio: 16 / 10;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 14px;
  background: var(--fin-card-inset);
}
.lines span {
  height: 3px;
  border-radius: 2px;
  background: var(--fin-muted);
}

/* ── preview: 内容宽度 ─────────────── */
.cw {
  aspect-ratio: 21 / 6;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  padding: 10px 14px;
  background: var(--fin-card-inset);
}
.cw span {
  height: 4px;
  border-radius: 2px;
  background: var(--fin-muted);
}
.cw-full span { width: 100%; }
.cw-centered {
  align-items: center;
}
.cw-centered span { width: 62%; }

/* ── footer ─────────────── */
.modal-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--fin-border);
}
.reset {
  border: 1px solid var(--fin-border);
  border-radius: 999px;
  padding: 9px 16px;
  background: transparent;
  color: var(--fin-text-2);
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
}
.reset:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.done {
  border: 0;
  border-radius: 999px;
  padding: 9px 22px;
  background: var(--fin-primary);
  color: #fff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 800;
}

@media (max-width: 560px) {
  .cols-4 { grid-template-columns: repeat(3, 1fr); }
  .cols-6 { grid-template-columns: repeat(4, 1fr); }
}
</style>
