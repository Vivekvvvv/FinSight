<script setup lang="ts">
import { useRouter } from 'vue-router';
import { useIdentityStore } from '@/stores/identity';

const store = useIdentityStore();
const router = useRouter();

function goLogin() {
  router.push('/login');
}

async function handleLogout() {
  await store.logout();
  router.push('/login');
}
</script>

<template>
  <div class="identity-panel">
    <div
      v-if="store.isGuest"
      class="guest-mode"
    >
      <span class="label">游客模式</span>
      <button
        class="btn-login"
        @click="goLogin"
      >
        登录
      </button>
    </div>

    <div
      v-else
      class="user-info"
    >
      <div class="user-text">
        <span class="user-id">{{ store.userId }}</span>
        <span class="user-role">({{ store.role }})</span>
        <span
          v-if="store.isAdmin"
          class="admin-badge"
        >🛡️ 管理员</span>
      </div>
      <button
        class="btn-logout"
        @click="handleLogout"
      >
        退出
      </button>
    </div>
  </div>
</template>

<style scoped>
.identity-panel {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.guest-mode {
  display: flex;
  align-items: center;
  gap: 8px;
}

.label {
  font-size: 13px;
  color: var(--fin-muted);
}

.btn-login {
  padding: 6px 16px;
  border: 1px solid var(--fin-primary);
  border-radius: 8px;
  background: transparent;
  color: var(--fin-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-login:hover {
  background: var(--fin-primary);
  color: #fff;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  border: 1px solid var(--fin-border);
  border-radius: 10px;
  background: var(--fin-card);
}

.user-text {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.user-id {
  font-weight: 600;
  color: var(--fin-text);
}

.user-role {
  color: var(--fin-muted);
}

.admin-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--fin-warning-soft);
  color: var(--fin-warning);
}

.btn-logout {
  padding: 4px 12px;
  border: 1px solid var(--fin-border);
  border-radius: 6px;
  background: transparent;
  color: var(--fin-text-2);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-logout:hover {
  background: var(--fin-danger);
  border-color: var(--fin-danger);
  color: #fff;
}
</style>
