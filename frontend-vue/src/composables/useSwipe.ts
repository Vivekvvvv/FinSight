/**
 * 左右滑动切换 Tab composable
 * 用法：
 *   const { onTouchStart, onTouchEnd } = useSwipe({ onLeft, onRight })
 *   <div @touchstart="onTouchStart" @touchend="onTouchEnd">
 */
export function useSwipe(handlers: {
  onLeft?: () => void;
  onRight?: () => void;
  minDistance?: number;
}) {
  const min = handlers.minDistance ?? 60;
  let startX = 0;

  function onTouchStart(e: TouchEvent) {
    startX = e.touches[0].clientX;
  }

  function onTouchEnd(e: TouchEvent) {
    const dx = e.changedTouches[0].clientX - startX;
    if (Math.abs(dx) < min) return;
    if (dx < 0) handlers.onLeft?.();
    else handlers.onRight?.();
  }

  return { onTouchStart, onTouchEnd };
}
