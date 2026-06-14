<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { RouterView, useRoute } from 'vue-router';
import AppShell from '@/components/AppShell.vue';
import GlobalLoading from '@/components/GlobalLoading.vue';
import { useIdentityStore } from '@/stores/identity';
import { useThemeStore } from '@/stores/theme';

const route = useRoute();
const identity = useIdentityStore();
const theme = useThemeStore();
const isLogin = computed(() => route.path === '/login');

onMounted(() => {
  theme.init();
  identity.bootstrap().catch(() => undefined);
});
</script>

<template>
  <GlobalLoading />
  <RouterView v-if="isLogin" />
  <AppShell v-else>
    <RouterView />
  </AppShell>
</template>
