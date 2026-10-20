<template>
  <UPopover
    v-if="sessionStore.spec && sessionStore.arrays"
    :content="{ side: 'bottom', align: 'end', sideOffset: 8, collisionPadding: 12 }"
    :ui="{ content: 'max-w-md' }"
  >
    <UButton
      label="Row hits"
      icon="i-lucide-target"
      color="neutral"
      variant="subtle"
      size="sm"
      class="shrink-0 cursor-pointer"
    />

    <template #content>
      <div class="p-3 w-96 max-w-[calc(100vw-2rem)]">
        <div class="text-sm font-medium text-zinc-200">Row-hit summary</div>
        <div class="mt-0.5 text-[11px] text-zinc-500">
          An access is a hit when its request issued no opening command.
        </div>

        <template v-if="summary?.available">
          <div class="grid grid-cols-3 gap-2 my-3 text-center">
            <div class="rounded bg-zinc-900 p-2">
              <div class="font-mono text-sm text-zinc-200">{{ summary.accesses.toLocaleString() }}</div>
              <div class="text-[10px] text-zinc-500">accesses</div>
            </div>
            <div class="rounded bg-zinc-900 p-2">
              <div class="font-mono text-sm text-lime-300">{{ summary.hits.toLocaleString() }}</div>
              <div class="text-[10px] text-zinc-500">row hits</div>
            </div>
            <div class="rounded bg-zinc-900 p-2">
              <div class="font-mono text-sm text-zinc-200">{{ percent(summary.hits, summary.accesses) }}</div>
              <div class="text-[10px] text-zinc-500">hit rate</div>
            </div>
          </div>

          <div class="space-y-1.5">
            <div
              v-for="row in rows"
              :key="row.label"
              class="grid grid-cols-[minmax(0,1fr)_4.5rem_4.5rem] items-center gap-2 text-xs"
            >
              <div class="flex items-center gap-2 min-w-0">
                <span class="size-2.5 rounded-sm shrink-0 border-2" :style="{ borderColor: row.color }" />
                <span class="font-mono text-zinc-300">{{ row.label }}</span>
              </div>
              <span class="font-mono text-right text-zinc-400">{{ row.bucket.hits }}/{{ row.bucket.accesses }}</span>
              <span class="font-mono text-right text-zinc-400">{{ percent(row.bucket.hits, row.bucket.accesses) }}</span>
            </div>
          </div>

          <div class="mt-3 pt-2 border-t border-zinc-800 text-[10px] text-zinc-500 leading-relaxed">
            <span class="inline-block size-2.5 align-[-1px] mr-1 border-2 border-dashed" :style="{ borderColor: ROW_HIT_BORDER_COLOR }" />
            Dashed lime boxes mark row-hit commands in the timeline.<br>
            Misses combine requests that required activation after either a closed-view miss or a row conflict.
          </div>
        </template>
        <div v-else class="py-5 text-center text-xs text-zinc-500">
          Row-hit analysis requires a RAM2BIN v1.2+ trace with request IDs.
        </div>
      </div>
    </template>
  </UPopover>
</template>

<script setup lang="ts">
import { ROW_HIT_BORDER_COLOR, VIEW_BORDER_COLORS } from '~/utils/eventSemantics';

const sessionStore = useSessionStore();
const summary = computed(() => sessionStore.rowHitSummary);

const rows = computed(() => {
  const value = summary.value;
  if (!value) return [];
  return [
    { label: 'Reads', bucket: value.reads, color: '#3b82f6' },
    { label: 'Writes', bucket: value.writes, color: '#f97316' },
    { label: 'View A', bucket: value.viewA, color: VIEW_BORDER_COLORS.A },
    { label: 'View B', bucket: value.viewB, color: VIEW_BORDER_COLORS.B },
  ];
});

function percent(hits: number, accesses: number): string {
  return accesses > 0 ? `${(hits * 100 / accesses).toFixed(1)}%` : '—';
}
</script>
