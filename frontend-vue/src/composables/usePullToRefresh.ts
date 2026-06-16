/**
 * 下拉刷新 composable
 * 用法：const { isRefreshing, pullStyle } = usePullToRefresh(onRefresh)
 */
import { ref, onMounted, onUnmounted, type Ref } from 'vue';

export function usePullToRefresh(
  onRefresh: () => Promise<void>,
  options: { threshold?: number; el?: Ref<HTMLElement | null> } = {}
) {
  const threshold = options.threshold ?? 80;
  const isRefreshing = ref(false);
  const pullDistance = ref(0);
  const pulling = ref(false);

  let startY = 0;

  const pullStyle = {
    get transform() {
      return `translateY(${Math.min(pullDistance.value, threshold + 20)}px)`;
    },
    get transition() {
      return pulling.value ? 'none' : 'transform 0.3s ease';
    },
  };

  function onTouchStart(e: TouchEvent) {
    const scrollEl = options.el?.value ?? document.documentElement;
    if (scrollEl.scrollTop > 0) return;
    startY = e.touches[0].clientY;
    pulling.value = true;
  }

  function onTouchMove(e: TouchEvent) {
    if (!pulling.value) return;
    const dy = e.touches[0].clientY - startY;
    if (dy > 0) {
      pullDistance.value = dy * 0.5; // 阻尼
      if (dy > threshold / 2) e.preventDefault();
    }
  }

  async function onTouchEnd() {
    if (!pulling.value) return;
    pulling.value = false;
    if (pullDistance.value >= threshold && !isRefreshing.value) {
      isRefreshing.value = true;
      pullDistance.value = threshold / 2;
      try {
        await onRefresh();
      } finally {
        isRefreshing.value = false;
        pullDistance.value = 0;
      }
    } else {
      pullDistance.value = 0;
    }
  }

  onMounted(() => {
    document.addEventListener('touchstart', onTouchStart, { passive: false });
    document.addEventListener('touchmove', onTouchMove, { passive: false });
    document.addEventListener('touchend', onTouchEnd);
  });

  onUnmounted(() => {
    document.removeEventListener('touchstart', onTouchStart);
    document.removeEventListener('touchmove', onTouchMove);
    document.removeEventListener('touchend', onTouchEnd);
  });

  return { isRefreshing, pullDistance, pullStyle };
}
