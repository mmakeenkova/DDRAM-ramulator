<template>
  <UPopover
    v-if="sessionStore.spec && sessionStore.arrays"
    :content="{ side: 'bottom', align: 'end', sideOffset: 8, collisionPadding: 12 }"
    :ui="{ content: 'max-w-md' }"
  >
    <UButton
      label="Bottlenecks"
      icon="i-lucide-gauge"
      color="neutral"
      variant="subtle"
      size="sm"
      class="shrink-0 cursor-pointer"
    />

    <template #content>
      <div class="p-3 w-96 max-w-[calc(100vw-2rem)]">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-sm font-medium text-zinc-200">Strictest timing constraints</div>
            <div class="mt-0.5 text-[11px] text-zinc-500">
              Counts the constraint(s) that established each command's earliest issue cycle.
            </div>
          </div>
          <span class="text-[10px] rounded px-1.5 py-0.5 bg-zinc-800 text-zinc-400 whitespace-nowrap">
            {{ recordsEqualTies ? 'all ties' : 'primary only' }}
          </span>
        </div>

        <div class="grid grid-cols-3 gap-2 my-3 text-center">
          <div class="rounded bg-zinc-900 p-2">
            <div class="font-mono text-sm text-zinc-200">{{ summary.timedEvents.toLocaleString() }}</div>
            <div class="text-[10px] text-zinc-500">timed commands</div>
          </div>
          <div class="rounded bg-zinc-900 p-2">
            <div class="font-mono text-sm text-zinc-200">{{ summary.atBoundary.toLocaleString() }}</div>
            <div class="text-[10px] text-zinc-500">at boundary</div>
          </div>
          <div class="rounded bg-zinc-900 p-2">
            <div class="font-mono text-sm text-zinc-200">{{ summary.withSlack.toLocaleString() }}</div>
            <div class="text-[10px] text-zinc-500">with slack</div>
          </div>
        </div>

        <div v-if="summary.rows.length" class="space-y-1.5 max-h-80 overflow-y-auto pr-1">
          <div
            v-for="row in summary.rows"
            :key="row.id"
            class="grid grid-cols-[minmax(0,1fr)_4.5rem_4.5rem] items-center gap-2 text-xs"
          >
            <div class="flex items-center gap-2 min-w-0">
              <span class="size-2.5 rounded-full shrink-0" :style="{ backgroundColor: row.color }" />
              <span class="font-mono text-zinc-300 truncate" :title="row.label">{{ row.label }}</span>
            </div>
            <span class="font-mono text-right text-zinc-400" :title="'Strictest-cause occurrences'">
              {{ row.occurrences.toLocaleString() }} causes
            </span>
            <span class="font-mono text-right text-zinc-400" :title="'Commands issued exactly at the earliest legal cycle'">
              {{ row.atBoundary.toLocaleString() }} exact
            </span>
          </div>
        </div>
        <div v-else class="py-5 text-center text-xs text-zinc-500">
          This trace has no timing-provenance records.
        </div>

        <div class="mt-3 pt-2 border-t border-zinc-800 text-[10px] text-zinc-500 leading-relaxed">
          “With slack” means scheduling or another resource delayed issue beyond the recorded earliest legal cycle; it is not attributed to a DRAM timing constraint.
        </div>
      </div>
    </template>
  </UPopover>
</template>

<script setup lang="ts">
import { getEventTimingCauses } from '~/utils/timingCauses';

const sessionStore = useSessionStore();

const recordsEqualTies = computed(() => {
  const a = sessionStore.arrays;
  return !!a && a.tieOffsets.length === a.clk.length + 1 && a.tieConstraintId.length > 0;
});

const summary = computed(() => {
  const arrays = sessionStore.arrays;
  const spec = sessionStore.spec;
  const empty = { timedEvents: 0, atBoundary: 0, withSlack: 0, rows: [] as Array<{
    id: number; label: string; color: string; occurrences: number; atBoundary: number;
  }> };
  if (!arrays || !spec) return empty;

  const counts = new Map<number, { id: number; label: string; color: string; occurrences: number; atBoundary: number }>();
  let timedEvents = 0;
  let atBoundary = 0;
  let withSlack = 0;
  for (let i = 0; i < arrays.clk.length; i++) {
    const readyAt = arrays.readyAt[i]!;
    if (readyAt < 0n) continue;
    timedEvents++;
    const exact = arrays.clk[i] === readyAt;
    if (exact) atBoundary++;
    else withSlack++;
    for (const cause of getEventTimingCauses(arrays, spec, i)) {
      const id = cause.constraintId;
      const existing = counts.get(id) ?? {
        id,
        label: cause.constraint?.label ?? `constraint ${id}`,
        color: cause.color,
        occurrences: 0,
        atBoundary: 0,
      };
      existing.occurrences++;
      if (exact) existing.atBoundary++;
      counts.set(id, existing);
    }
  }

  const rows = [...counts.values()].sort((a, b) =>
    b.atBoundary - a.atBoundary || b.occurrences - a.occurrences || a.label.localeCompare(b.label));
  return { timedEvents, atBoundary, withSlack, rows };
});
</script>
