import { defineStore } from 'pinia';

export const useEntitlementsStore = defineStore('entitlements', () => {
  function hasFeature(feature: string): boolean {
    void feature;
    return true;
  }
  function plan(): string { return 'free'; }
  async function load(): Promise<void> {}
  return { hasFeature, plan, load };
});
