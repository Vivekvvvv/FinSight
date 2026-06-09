<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import { useIdentityStore } from '@/stores/identity';

const router = useRouter();
const identity = useIdentityStore();
const email = ref('');
const password = ref('');
const loading = ref(false);
const errorMsg = ref<string | null>(null);

const stats = [
  ['7', '研究智能体'],
  ['12+', '核心 API'],
  ['48/48', 'E2E 基线'],
  ['5', '研究闭环模块'],
];

const capabilities = ['Portfolio Risk Lens', 'Research Notebook', 'Evidence Timeline', 'What Changed', 'Research Quality'];

async function handleLogin() {
  if (!email.value || !password.value) {
    errorMsg.value = '请输入邮箱和密码';
    return;
  }
  loading.value = true;
  errorMsg.value = null;
  try {
    const resp = await apiClient.login({ email: email.value, password: password.value });
    identity.saveLocalIdentity({
      userId: resp.user_id,
      sessionId: `user:${resp.user_id}:vue-shadow`,
      email: resp.email || email.value,
      accessToken: resp.token,
    });
    await identity.bootstrap();
    await router.push('/welcome');
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || e.message || '登录失败，请检查后端服务或账号配置';
  } finally {
    loading.value = false;
  }
}

function enterGuest() {
  identity.saveLocalIdentity({
    userId: 'guest_researcher',
    sessionId: 'public:anonymous:vue-demo',
    email: 'guest@finsight.local',
    accessToken: '',
  });
  router.push('/welcome');
}

function fillDemo(role: 'admin' | 'user') {
  email.value = role === 'admin' ? 'admin@finsight.local' : 'user@finsight.local';
  password.value = role === 'admin' ? 'admin123' : 'user123';
}
</script>

<template>
  <main class="login-terminal">
    <section class="hero-panel">
      <div class="terminal-line">
        <span>FINSIGHT TERMINAL</span>
        <span>SESSION / RESEARCH</span>
        <span>MARKET OPEN</span>
      </div>

      <div class="hero-copy">
        <p class="eyebrow">Evidence-driven financial research</p>
        <h1>把市场、持仓、报告和证据压缩成每天能行动的研究工作台。</h1>
        <p class="subcopy">
          FinSight 不是交易按钮，而是一套可复查的研究基础设施：它告诉你发生了什么、为什么重要、该去哪里复核。
        </p>
      </div>

      <div class="stat-grid">
        <article v-for="[value, label] in stats" :key="label">
          <strong>{{ value }}</strong>
          <span>{{ label }}</span>
        </article>
      </div>

      <div class="capability-strip">
        <span v-for="item in capabilities" :key="item">{{ item }}</span>
      </div>

      <div class="market-footer">
        <span>AAPL +1.19%</span>
        <span>NVDA -6.25%</span>
        <span>SPY +0.42%</span>
        <span>QQQ +0.77%</span>
      </div>
    </section>

    <section class="auth-panel">
      <div class="auth-card">
        <p class="eyebrow">Secure workspace</p>
        <h2>进入研究空间</h2>
        <p class="auth-note">公开演示默认走本地身份；生产环境请配置 JWT、API key 与有效 LLM key。</p>

        <form @submit.prevent="handleLogin">
          <label>
            <span>邮箱</span>
            <input v-model="email" type="email" autocomplete="email" placeholder="your@email.com">
          </label>
          <label>
            <span>密码</span>
            <input v-model="password" type="password" autocomplete="current-password" placeholder="••••••••">
          </label>

          <p v-if="errorMsg" class="error-box">{{ errorMsg }}</p>

          <button class="primary-action" type="submit" :disabled="loading">
            {{ loading ? '正在登录…' : '登录并进入工作台' }}
          </button>
        </form>

        <div class="demo-actions">
          <button @click="fillDemo('admin')">填入管理员演示账号</button>
          <button @click="fillDemo('user')">填入普通用户演示账号</button>
          <button class="ghost-action" @click="enterGuest">匿名体验</button>
        </div>

        <p class="risk-note">仅供学习与研究复查，不构成投资建议。</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-terminal {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(380px, 0.85fr);
  background:
    linear-gradient(135deg, rgba(215, 255, 114, 0.18), transparent 32%),
    radial-gradient(circle at 85% 20%, rgba(45, 212, 191, 0.18), transparent 28%),
    #0e1412;
  color: #eef7ee;
}

.hero-panel,
.auth-panel {
  padding: 48px;
}

.hero-panel {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 100vh;
  border-right: 1px solid rgba(214, 255, 226, 0.12);
}

.terminal-line,
.market-footer,
.capability-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.terminal-line span,
.market-footer span,
.capability-strip span {
  border: 1px solid rgba(214, 255, 226, 0.18);
  border-radius: 999px;
  padding: 8px 12px;
  color: rgba(238, 247, 238, 0.66);
  background: rgba(238, 247, 238, 0.045);
  font-size: 12px;
}

.eyebrow {
  margin: 0 0 12px;
  color: #d7ff72;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  font-size: 11px;
}

.hero-copy {
  max-width: 820px;
}

.hero-copy h1 {
  margin: 0;
  font-size: clamp(40px, 6vw, 76px);
  line-height: 0.96;
  letter-spacing: -0.06em;
}

.subcopy,
.auth-note,
.risk-note {
  color: rgba(238, 247, 238, 0.64);
  line-height: 1.8;
}

.subcopy {
  max-width: 640px;
  font-size: 17px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 36px 0;
}

.stat-grid article {
  border: 1px solid rgba(214, 255, 226, 0.12);
  border-radius: 24px;
  padding: 18px;
  background: rgba(238, 247, 238, 0.05);
}

.stat-grid strong {
  display: block;
  font-size: 30px;
  color: #d7ff72;
}

.stat-grid span {
  color: rgba(238, 247, 238, 0.62);
}

.auth-panel {
  display: grid;
  place-items: center;
}

.auth-card {
  width: min(100%, 460px);
  border: 1px solid rgba(214, 255, 226, 0.14);
  border-radius: 32px;
  padding: 32px;
  background: rgba(247, 243, 232, 0.94);
  color: #17211d;
  box-shadow: 0 30px 120px rgba(0, 0, 0, 0.36);
}

.auth-card .eyebrow {
  color: #2f6f57;
}

.auth-card h2 {
  margin: 0 0 8px;
  font-size: 30px;
}

.auth-note,
.risk-note {
  color: #66746c;
}

form {
  display: grid;
  gap: 16px;
  margin-top: 24px;
}

label span {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 800;
  color: #405047;
}

input {
  width: 100%;
  border: 1px solid rgba(23, 33, 29, 0.14);
  border-radius: 16px;
  padding: 14px 16px;
  background: #fffaf0;
  color: #17211d;
}

input:focus {
  outline: 2px solid rgba(47, 111, 87, 0.22);
  border-color: #2f6f57;
}

.error-box {
  margin: 0;
  border: 1px solid rgba(196, 69, 69, 0.22);
  border-radius: 14px;
  padding: 12px;
  color: #9f2f2f;
  background: rgba(196, 69, 69, 0.08);
}

.primary-action,
.ghost-action,
.demo-actions button {
  border: 0;
  border-radius: 16px;
  padding: 13px 16px;
  cursor: pointer;
}

.primary-action {
  background: #17211d;
  color: #d7ff72;
  font-weight: 900;
}

.demo-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 18px;
}

.demo-actions button {
  border: 1px solid rgba(23, 33, 29, 0.12);
  background: #efe9d8;
  color: #17211d;
}

.demo-actions .ghost-action {
  grid-column: 1 / -1;
  background: #dff7df;
  color: #174936;
  font-weight: 900;
}

@media (max-width: 980px) {
  .login-terminal {
    grid-template-columns: 1fr;
  }

  .hero-panel {
    min-height: auto;
    border-right: 0;
    gap: 34px;
  }

  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .hero-panel,
  .auth-panel {
    padding: 24px;
  }

  .stat-grid,
  .demo-actions {
    grid-template-columns: 1fr;
  }

  .demo-actions .ghost-action {
    grid-column: auto;
  }
}
</style>
