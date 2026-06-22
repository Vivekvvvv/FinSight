<script setup lang="ts">
withDefaults(defineProps<{
  title: string;
  hint?: string;
  icon?: string;
  actionLabel?: string;
  secondaryActionLabel?: string;
  compact?: boolean;
}>(), {
  hint: '',
  icon: '',
  actionLabel: '',
  secondaryActionLabel: '',
  compact: false,
});

const emit = defineEmits<{
  action: [];
  secondaryAction: [];
}>();
</script>

<template>
  <section class="finsight-empty-state" :class="{ compact }">
    <div class="empty-mark" aria-hidden="true">{{ icon || '—' }}</div>
    <div class="empty-copy">
      <strong>{{ title }}</strong>
      <p v-if="hint">{{ hint }}</p>
      <slot />
    </div>
    <div v-if="actionLabel || secondaryActionLabel" class="empty-actions">
      <button v-if="actionLabel" type="button" class="primary" @click="emit('action')">{{ actionLabel }}</button>
      <button v-if="secondaryActionLabel" type="button" class="secondary" @click="emit('secondaryAction')">{{ secondaryActionLabel }}</button>
    </div>
  </section>
</template>

<style scoped>
.finsight-empty-state {
  display: grid;
  justify-items: center;
  gap: 10px;
  padding: 34px 20px;
  border: 1px dashed var(--fin-border);
  border-radius: 8px;
  background: var(--fin-card-soft);
  text-align: center;
}

.compact {
  padding: 22px 16px;
}

.empty-mark {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border: 1px solid var(--fin-border);
  border-radius: 999px;
  color: var(--fin-primary);
  background: var(--fin-card);
  font-weight: 800;
}

.empty-copy {
  display: grid;
  gap: 4px;
}

.empty-copy strong {
  color: var(--fin-text);
  font-size: 15px;
}

.empty-copy p {
  max-width: 420px;
  margin: 0;
  color: var(--fin-muted);
  font-size: 13px;
  line-height: 1.6;
}

.empty-actions {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
}

.empty-actions button {
  min-height: 34px;
  padding: 7px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
}

.primary {
  border: 1px solid var(--fin-primary);
  background: var(--fin-primary);
  color: #111827;
}

.secondary {
  border: 1px solid var(--fin-border);
  background: var(--fin-card);
  color: var(--fin-text-2);
}
</style>
