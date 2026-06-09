<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { RouterView, useRoute } from 'vue-router';
import AppShell from '@/components/AppShell.vue';
import { useIdentityStore } from '@/stores/identity';

const route = useRoute();
const identity = useIdentityStore();
const isLogin = computed(() => route.path === '/login');

onMounted(() => {
  identity.bootstrap().catch(() => undefined);
});
</script>

<template>
  <RouterView v-if="isLogin" />
  <AppShell v-else>
    <RouterView />
  </AppShell>
</template>
