<template>
  <div class="absolute inset-x-0 top-0 h-9 border-b border-neutral-800 bg-neutral-900 flex items-center gap-3 px-3 z-20">
    <span class="uppercase tracking-wider text-[10px] text-zinc-500 w-12">{{ panel }}</span>
    <span class="truncate text-xs font-mono text-zinc-300">{{ state.name || 'No trace loaded' }}</span>
    <span v-if="state.detail" class="text-[11px] text-zinc-500">{{ state.detail }}</span>
    <span v-if="state.error" class="text-[11px] text-red-400 truncate">{{ state.error }}</span>
    <label class="ml-auto">
      <input class="sr-only" type="file" accept=".ram2bin" :disabled="state.loading || !state.ready" @change="selectFile">
      <span class="inline-flex items-center rounded-md px-2.5 py-1 text-xs cursor-pointer bg-neutral-800 hover:bg-neutral-700 text-zinc-200">
        {{ state.loading ? 'Loading…' : state.name ? 'Replace' : 'Load trace' }}
      </span>
    </label>
  </div>
</template>

<script setup lang="ts">
import type { ComparePanelId } from '~/utils/compareProtocol';

defineProps<{
  panel: ComparePanelId;
  state: { ready: boolean; loaded: boolean; loading: boolean; name: string; detail: string; error: string };
}>();
const emit = defineEmits<{ load: [file: File] }>();

function selectFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) emit('load', file);
  input.value = '';
}
</script>
