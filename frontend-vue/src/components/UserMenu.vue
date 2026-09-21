<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useIdentityStore } from '@/stores/identity';

const identity = useIdentityStore();
const router = useRouter();

const open = ref(false);
const profileOpen = ref(false);
const loggingOut = ref(false);
const root = ref<HTMLElement | null>(null);
const triggerRef = ref<HTMLButtonElement | null>(null);
const profileCloseRef = ref<HTMLButtonElement | null>(null);
const profileModalRef = ref<HTMLElement | null>(null);

const ROLE_LABELS: Record<string, string> = {
  dev: '开发',
  guest: '游客',
  admin: '管理员',
  internal: '内部',
  user: '用户',
};

const displayName = computed(() => {
  const email = identity.email.trim();
  if (email.includes('@')) return email.split('@')[0];
  return identity.userId || '用户';
});
const roleLabel = computed(() => ROLE_LABELS[identity.role] || identity.role || '用户');
const modeLabel = computed(() => (identity.mode === 'remote' ? '云端' : '本地'));
const initials = computed(() => {
  const source = displayName.value.trim();
  return (source[0] || 'U').toUpperCase();
});

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
  if (event.key === 'Escape') {
    if (profileOpen.value) profileOpen.value = false;
    else if (open.value) close();
    return;
  }
  // 焦点陷阱：资料弹窗标了 aria-modal，但浏览器不自动困住焦点，需手动首尾环绕。
  if (event.key !== 'Tab' || !profileOpen.value) return;
  const modal = profileModalRef.value;
  if (!modal) return;
  const focusables = Array.from(
    modal.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((el) => !el.hasAttribute('disabled') && el.offsetParent !== null);
  if (focusables.length === 0) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  const active = document.activeElement as HTMLElement | null;
  if (event.shiftKey && (active === first || !modal.contains(active))) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && active === last) {
    event.preventDefault();
    first.focus();
  }
}

onMounted(() => {
  document.addEventListener('click', onDocClick);
  document.addEventListener('keydown', onKeydown);
});
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick);
  document.removeEventListener('keydown', onKeydown);
  if (typeof document !== 'undefined') document.body.style.overflow = '';
});

watch(profileOpen, async (value) => {
  if (typeof document === 'undefined') return;
  document.body.style.overflow = value ? 'hidden' : '';
  // 打开时把焦点移入资料弹窗，关闭时归还给头像触发按钮（键盘/读屏可访问性）。
  await nextTick();
  if (value) profileCloseRef.value?.focus();
  else triggerRef.value?.focus();
});

function openProfile() {
  close();
  profileOpen.value = true;
}

function goLogin() {
  close();
  router.push('/login');
}

async function handleLogout() {
  if (loggingOut.value) return;
  loggingOut.value = true;
  try {
    await identity.logout();
  } finally {
    loggingOut.value = false;
    close();
    profileOpen.value = false;
    router.push('/login');
  }
}

const profileRows = computed(() => [
  { label: '用户名', value: identity.userId || '—' },
  { label: '邮箱', value: identity.email.trim() || '未绑定' },
  { label: '角色', value: roleLabel.value },
  { label: '登录方式', value: identity.authType || 'local' },
  { label: '模式', value: modeLabel.value },
  { label: '会话 ID', value: identity.sessionId || '—' },
]);
</script>

<template>
  <div
    ref="root"
    class="user-menu"
  >
    <button
      ref="triggerRef"
      type="button"
      class="avatar-trigger"
      :class="{ active: open }"
      aria-haspopup="menu"
      :aria-expanded="open"
      aria-label="账户菜单"
      title="账户"
      @click.stop="toggle"
    >
      <span
        class="avatar"
        aria-hidden="true"
      >{{ initials }}</span>
    </button>

    <div
      v-if="open"
      class="user-popover"
      role="menu"
      aria-label="账户菜单"
    >
      <div class="pop-head">
        <span
          class="avatar lg"
          aria-hidden="true"
        >{{ initials }}</span>
        <div class="who">
          <strong>{{ displayName }}</strong>
          <span>{{ roleLabel }} · {{ modeLabel }}</span>
        </div>
      </div>

      <div class="pop-divider" />

      <template v-if="identity.isGuest">
        <button
          type="button"
          class="pop-item"
          role="menuitem"
          @click="goLogin"
        >
          <span
            class="ic"
            aria-hidden="true"
          >→</span>
          <span>登录</span>
        </button>
      </template>
      <template v-else>
        <button
          type="button"
          class="pop-item"
          role="menuitem"
          @click="openProfile"
        >
          <span
            class="ic"
            aria-hidden="true"
          >👤</span>
          <span>个人资料</span>
        </button>
        <button
          type="button"
          class="pop-item danger"
          role="menuitem"
          :disabled="loggingOut"
          @click="handleLogout"
        >
          <span
            class="ic"
            aria-hidden="true"
          >⎋</span>
          <span>{{ loggingOut ? '登出中…' : '登出' }}</span>
        </button>
      </template>
    </div>

    <Teleport to="body">
      <div
        v-if="profileOpen"
        class="profile-overlay"
        @click.self="profileOpen = false"
      >
        <div
          ref="profileModalRef"
          class="profile-modal"
          role="dialog"
          aria-modal="true"
          aria-label="个人资料"
        >
          <header class="modal-head">
            <div class="head-id">
              <span
                class="avatar xl"
                aria-hidden="true"
              >{{ initials }}</span>
              <div>
                <strong>{{ displayName }}</strong>
                <p>{{ roleLabel }} · {{ modeLabel }}</p>
              </div>
            </div>
            <button
              ref="profileCloseRef"
              type="button"
              class="close"
              aria-label="关闭"
              @click="profileOpen = false"
            >
              ✕
            </button>
          </header>

          <dl class="profile-rows">
            <div
              v-for="row in profileRows"
              :key="row.label"
              class="profile-row"
            >
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </div>
          </dl>

          <footer class="modal-foot">
            <button
              type="button"
              class="logout"
              :disabled="loggingOut"
              @click="handleLogout"
            >
              {{ loggingOut ? '登出中…' : '登出' }}
            </button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.user-menu {
  position: relative;
  display: inline-flex;
}

.avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 999px;
  background: var(--fin-primary);
  color: #fff;
  font-weight: 800;
  font-size: 13px;
  line-height: 1;
}
.avatar.lg { width: 38px; height: 38px; font-size: 15px; }
.avatar.xl { width: 46px; height: 46px; font-size: 18px; }

.avatar-trigger {
  padding: 3px;
  border: 1px solid var(--fin-border);
  border-radius: 999px;
  background: var(--fin-card-soft);
  cursor: pointer;
  display: inline-flex;
}
.avatar-trigger.active,
.avatar-trigger:hover {
  border-color: var(--fin-border-strong);
}

.user-popover {
  position: absolute;
  top: calc(100% + 10px);
  inset-inline-end: 0;
  width: 248px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: 1px solid var(--fin-border);
  border-radius: var(--fin-radius-lg);
  background: var(--fin-card);
  box-shadow: var(--fin-shadow);
  z-index: 60;
}

.pop-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 8px 10px;
}
.who {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.who strong {
  font-size: 14px;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.who span {
  font-size: 12px;
  color: var(--fin-muted);
}

.pop-divider {
  height: 1px;
  margin: 2px 0 4px;
  background: var(--fin-border);
}

.pop-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 10px;
  border: 0;
  border-radius: var(--fin-radius);
  background: transparent;
  color: var(--fin-text);
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
  text-align: start;
}
.pop-item:hover:not(:disabled) {
  background: var(--fin-card-inset);
}
.pop-item.danger {
  color: var(--fin-danger);
}
.pop-item.danger:hover:not(:disabled) {
  background: var(--fin-danger-soft);
}
.pop-item:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.pop-item .ic {
  width: 18px;
  display: grid;
  place-items: center;
  font-size: 14px;
}

/* ── 个人资料 modal ─────────────── */
.profile-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: grid;
  place-items: center;
  padding: 24px;
  background: var(--fin-overlay);
  backdrop-filter: blur(2px);
}
.profile-modal {
  width: min(440px, 100%);
  max-height: min(86vh, 720px);
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
  padding: 20px 22px 16px;
  border-bottom: 1px solid var(--fin-border);
}
.head-id {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.head-id strong {
  font-size: 17px;
  font-weight: 800;
}
.head-id p {
  margin: 3px 0 0;
  color: var(--fin-muted);
  font-size: 13px;
}
.close {
  border: 0;
  background: transparent;
  color: var(--fin-muted);
  cursor: pointer;
  font-size: 17px;
  line-height: 1;
  padding: 6px;
  border-radius: 8px;
}
.close:hover {
  color: var(--fin-text);
  background: var(--fin-card-inset);
}

.profile-rows {
  margin: 0;
  padding: 8px 22px 18px;
  overflow-y: auto;
}
.profile-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding: 11px 0;
  border-bottom: 1px solid var(--fin-border);
}
.profile-row:last-child {
  border-bottom: 0;
}
.profile-row dt {
  color: var(--fin-muted);
  font-size: 13px;
  flex-shrink: 0;
}
.profile-row dd {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--fin-text);
  text-align: end;
  word-break: break-all;
}

.modal-foot {
  display: flex;
  justify-content: flex-end;
  padding: 14px 22px;
  border-top: 1px solid var(--fin-border);
}
.logout {
  border: 1px solid var(--fin-danger);
  border-radius: 999px;
  padding: 9px 20px;
  background: transparent;
  color: var(--fin-danger);
  cursor: pointer;
  font-size: 13px;
  font-weight: 800;
}
.logout:hover:not(:disabled) {
  background: var(--fin-danger);
  color: #fff;
}
.logout:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
