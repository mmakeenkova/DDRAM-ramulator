<template>
  <UPopover
    :content="{ side: 'bottom', align: 'end', sideOffset: 8, collisionPadding: 12 }"
    :ui="{ content: 'max-w-sm' }"
  >
    <UButton
      label="Settings"
      icon="i-lucide-settings-2"
      color="neutral"
      variant="subtle"
      size="sm"
      class="shrink-0 cursor-pointer"
      aria-label="Trace settings"
    />

    <template #content>
      <div class="flex flex-col gap-3 p-3 w-80">
        <div>
          <p class="text-xs font-semibold text-zinc-300">
            Timeline
          </p>
          <p class="mt-1 text-xs text-zinc-500 leading-snug">
           Configure the timeline display.
          </p>
        </div>

        <div class="rounded-lg bg-zinc-900/50 border border-zinc-800/80 px-3 py-2.5">
          <div class="flex items-center gap-3">
            <div class="min-w-0 flex-1">
              <p class="text-xs font-medium text-zinc-200">
                Display x-axis in nanoseconds
              </p>
              <p class="mt-0.5 text-[11px] text-zinc-500 leading-snug">
                Uses <span class="font-mono">tCK_ps</span>
                <template v-if="tCKPs != null">
                  = {{ tCKPs }} ps.
                </template>
                <template v-else>
                  from the trace spec when available.
                </template>
              </p>
            </div>

            <USwitch
              v-model="displayTimelineInNs"
              :disabled="tCKPs == null"
              aria-label="Display timeline x-axis in nanoseconds"
            />
          </div>
        </div>

        <div>
          <p class="text-xs font-semibold text-zinc-300">
            Command annotations
          </p>
          <p class="mt-1 text-xs text-zinc-500 leading-snug">
            Add semantic overlays without replacing the existing command colors.
          </p>
        </div>

        <div class="rounded-lg bg-zinc-900/50 border border-zinc-800/80 divide-y divide-zinc-800/80">
          <div class="flex items-center gap-3 px-3 py-2.5">
            <div class="min-w-0 flex-1">
              <p class="text-xs font-medium text-zinc-200">Split view A/B lanes</p>
              <p class="mt-0.5 text-[11px] text-zinc-500 leading-snug">
                Places view-specific commands on separate command-bus lanes; the data bus remains shared.
              </p>
            </div>
            <USwitch v-model="splitViewLanes" :disabled="!supportsViewLanes" aria-label="Split DDRAM view lanes" />
          </div>

          <div class="flex items-center gap-3 px-3 py-2.5">
            <div class="min-w-0 flex-1">
              <p class="text-xs font-medium text-zinc-200">Color by operation</p>
              <p class="mt-0.5 text-[11px] text-zinc-500 leading-snug">
                Gives every command in one controller request the same deterministic color.
              </p>
            </div>
            <USwitch v-model="colorByOperation" aria-label="Color commands by controller request" />
          </div>

          <div class="flex items-center gap-3 px-3 py-2.5">
            <div class="min-w-0 flex-1">
              <p class="text-xs font-medium text-zinc-200">Highlight row hits</p>
              <p class="mt-0.5 text-[11px] text-zinc-500 leading-snug">
                Draws a dashed lime box around accesses that required no activation.
              </p>
            </div>
            <USwitch v-model="highlightRowHits" aria-label="Highlight row-hit commands" />
          </div>

          <div class="flex items-center gap-3 px-3 py-2.5">
            <div class="min-w-0 flex-1">
              <p class="text-xs font-medium text-zinc-200">Color borders by view</p>
              <p class="mt-0.5 text-[11px] text-zinc-500 leading-snug">
                Cyan identifies view A and pink identifies view B, including internal refresh.
              </p>
            </div>
            <USwitch v-model="colorByView" aria-label="Color command borders by DDRAM-P view" />
          </div>

          <div class="flex items-center gap-3 px-3 py-2.5">
            <div class="min-w-0 flex-1">
              <p class="text-xs font-medium text-zinc-200">Show auto-precharge phases</p>
              <p class="mt-0.5 text-[11px] text-zinc-500 leading-snug">
                Extends RDA/WRA with recovery and internal nRP operation markers.
              </p>
            </div>
            <USwitch v-model="showAutoPrecharge" aria-label="Show auto-precharge phases" />
          </div>
        </div>
      </div>
    </template>
  </UPopover>
</template>

<script setup lang="ts">
const uiStore = useUIStore();
const sessionStore = useSessionStore();

const tCKPs = computed(() => sessionStore.getTimingValue('tCK_ps'));
const supportsViewLanes = computed(() => sessionStore.spec?.commandNames.some(
  name => /(?:^|_)[AB]$/i.test(name),
) ?? false);

const displayTimelineInNs = computed({
  get: () => uiStore.displayTimelineInNs,
  set: (value: boolean) => uiStore.setDisplayTimelineInNs(value),
});

const highlightRowHits = computed({
  get: () => uiStore.highlightRowHits,
  set: (value: boolean) => uiStore.setHighlightRowHits(value),
});

const colorByView = computed({
  get: () => uiStore.colorByView,
  set: (value: boolean) => uiStore.setColorByView(value),
});

const showAutoPrecharge = computed({
  get: () => uiStore.showAutoPrecharge,
  set: (value: boolean) => uiStore.setShowAutoPrecharge(value),
});

const splitViewLanes = computed({
  get: () => uiStore.splitViewLanes,
  set: (value: boolean) => uiStore.setSplitViewLanes(value),
});

const colorByOperation = computed({
  get: () => uiStore.colorByOperation,
  set: (value: boolean) => uiStore.setColorByOperation(value),
});
</script>
