<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';

interface NotificationOptions {
  title: string;
  body: string;
  icon?: string;
  tag?: string;
}

const notificationEnabled = ref(false);
const notificationPermission = ref<NotificationPermission>('default');

onMounted(() => {
  if ('Notification' in window) {
    notificationPermission.value = Notification.permission;
    notificationEnabled.value = Notification.permission === 'granted';
  }
});

async function requestPermission(): Promise<boolean> {
  if (!('Notification' in window)) {
    console.warn('浏览器不支持通知API');
    return false;
  }

  if (Notification.permission === 'granted') {
    notificationEnabled.value = true;
    return true;
  }

  if (Notification.permission !== 'denied') {
    const permission = await Notification.requestPermission();
    notificationPermission.value = permission;
    notificationEnabled.value = permission === 'granted';
    return permission === 'granted';
  }

  return false;
}

function showNotification(options: NotificationOptions): void {
  if (!notificationEnabled.value) {
    console.warn('通知未启用');
    return;
  }

  try {
    const notification = new Notification(options.title, {
      body: options.body,
      icon: options.icon || '/logo.svg',
      tag: options.tag || 'finsight-notification',
      requireInteraction: false,
    });

    // 3秒后自动关闭
    setTimeout(() => {
      notification.close();
    }, 3000);

    notification.onclick = () => {
      window.focus();
      notification.close();
    };
  } catch (error) {
    console.error('显示通知失败:', error);
  }
}

// 监听数据源降级事件
let degradationTimer: ReturnType<typeof setInterval> | null = null;

function watchDataSourceDegradation() {
  // 每30秒检查一次健康状态
  const checkInterval = 30000;

  degradationTimer = setInterval(async () => {
    if (!notificationEnabled.value) return;

    try {
      const response = await fetch('/api/system/health');
      const health = await response.json();

      // 检查降级源
      if (health.degraded_sources && health.degraded_sources.length > 0) {
        const sources = health.degraded_sources.join(', ');
        showNotification({
          title: '⚠️ 数据源降级警告',
          body: `以下数据源已降级：${sources}。系统已自动切换备用源。`,
          tag: 'datasource-degraded',
        });
      }

      // 检查严重状态
      if (health.overall_status === 'critical') {
        showNotification({
          title: '🔴 系统健康严重',
          body: '多个数据源不可用，数据可能不准确。请检查系统健康页面。',
          tag: 'system-critical',
        });
      }
    } catch (error) {
      console.error('健康检查失败:', error);
    }
  }, checkInterval);
}

// 暴露给外部使用
defineExpose({
  requestPermission,
  showNotification,
  notificationEnabled,
});

// 组件挂载后自动开始监听（如果已授权）
onMounted(() => {
  if (notificationEnabled.value) {
    watchDataSourceDegradation();
  }
});

// 卸载须停止轮询，否则 30s 健康检查在组件销毁后永久运行
onUnmounted(() => {
  if (degradationTimer !== null) {
    clearInterval(degradationTimer);
    degradationTimer = null;
  }
});
</script>

<template>
  <div class="notification-manager">
    <!-- 通知权限请求按钮（仅在未授权时显示） -->
    <button
      v-if="notificationPermission !== 'granted' && notificationPermission !== 'denied'"
      class="notification-request-btn"
      @click="requestPermission"
    >
      🔔 启用桌面通知
    </button>

    <!-- 已授权提示 -->
    <div
      v-if="notificationEnabled"
      class="notification-enabled"
    >
      ✅ 桌面通知已启用
    </div>

    <!-- 已拒绝提示 -->
    <div
      v-if="notificationPermission === 'denied'"
      class="notification-denied"
    >
      ❌ 桌面通知已被拒绝，请在浏览器设置中允许
    </div>
  </div>
</template>

<style scoped>
.notification-manager {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.notification-request-btn {
  padding: 6px 12px;
  border: 1.5px solid var(--fin-primary);
  border-radius: 8px;
  background: transparent;
  color: var(--fin-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.notification-request-btn:hover {
  background: var(--fin-primary);
  color: #fff;
}

.notification-enabled {
  font-size: 12px;
  color: var(--fin-success);
  font-weight: 600;
}

.notification-denied {
  font-size: 12px;
  color: var(--fin-muted);
}
</style>
