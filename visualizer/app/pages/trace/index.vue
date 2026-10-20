<template>
  <div class="relative w-full h-screen flex flex-col overflow-hidden bg-neutral-900">
    <div class="tab-bar">
      <div class="tab-bar-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.value"
          class="browser-tab"
          :class="{ active: uiStore.viewMode === tab.value }"
          @click="uiStore.setViewMode(tab.value)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="tab-bar-range">
        <template v-if="rangeStats">
          <span class="range-stat">
            <span class="range-stat-label">Range</span>{{ formatCycles(rangeStats.durationCycles) }} cyc
          </span>
          <span class="range-sep" />
          <UTooltip text="Read commands in the range">
            <span class="range-stat">
              <span class="range-stat-label">RD</span>{{ formatCycles(rangeStats.readCommands) }}
            </span>
          </UTooltip> 
          <UTooltip text="Write commands in the range">
            <span class="range-stat">
              <span class="range-stat-label">WR</span>{{ formatCycles(rangeStats.writeCommands) }}
            </span>
          </UTooltip>
          <UTooltip text="Other commands in the range">
            <span class="range-stat">
              <span class="range-stat-label">Other</span>{{ formatCycles(rangeStats.otherCommands) }}
            </span>
          </UTooltip>
          <span class="range-sep" />
          <UTooltip text="Commands per cycle on the command bus">
            <span class="range-stat">
              <span class="range-stat-label">CMD</span>{{ rangeStats.cmdBusThroughput.toFixed(3) }} cmd/cyc
            </span>
          </UTooltip>
          <UTooltip
            v-if="uiStore.viewMode === 'throughput' && throughputRangeStats"
            text="Average data-bus utilization across selected bins"
          >
            <span class="range-stat">
              <span class="range-stat-label">AVG DATA</span>
              {{ (throughputRangeStats.dataMeanUtil * 100).toFixed(1) }}%
            </span>
          </UTooltip>
          <UTooltip
            v-if="uiStore.viewMode === 'throughput' && throughputRangeStats"
            text="Average command-bus utilization across selected bins"
          >
            <span class="range-stat">
              <span class="range-stat-label">AVG CMD</span>
              {{ (throughputRangeStats.cmdMeanUtil * 100).toFixed(1) }}%
            </span>
          </UTooltip>
        </template>
        <span v-else class="range-hint">Shift+drag to select range · Ctrl+drag to zoom.</span>
      </div>

      <div class="tab-bar-cursor tab-bar-action" :class="{ 'is-open': cursorMode }">
        <UTooltip :kbds="['C']" :text="cursorMode ? 'Cursor mode active: click the canvas to place it.' : 'Enable cursor mode.'">
          <UButton
            icon="i-lucide-crosshair"
            label="Cursor"
            size="sm"
            :color="cursorMode ? 'primary' : 'neutral'"
            :variant="cursorMode ? 'soft' : 'subtle'"
            class="tab-bar-cursor-button"
            @click="toggleCursorMode"
          />
        </UTooltip>

        <Transition name="cursor-toolkit">
          <div v-if="cursorMode" class="cursor-toolkit">
            <span v-if="cursorTime != null" class="cursor-readout">
              <span class="cursor-readout-label">CUR</span>{{ formatCycles(cursorTime) }} clk
            </span>
            <span v-else class="cursor-readout is-empty">
              click to place
            </span>

            <span class="cursor-toolkit-sep" />

            <UTooltip text="Jump to previous event start in this view">
              <UButton
                icon="i-lucide-skip-back"
                size="xs"
                color="neutral"
                variant="ghost"
                :disabled="!canJumpCursor"
                aria-label="Previous cursor event"
                @click="jumpCursor('prev')"
              />
            </UTooltip>
            <UTooltip text="Jump to next event start in this view">
              <UButton
                icon="i-lucide-skip-forward"
                size="xs"
                color="neutral"
                variant="ghost"
                :disabled="!canJumpCursor"
                aria-label="Next cursor event"
                @click="jumpCursor('next')"
              />
            </UTooltip>
            <UTooltip text="Remove cursor">
              <UButton
                icon="i-lucide-x"
                size="xs"
                color="error"
                variant="ghost"
                :disabled="cursorTime == null"
                aria-label="Remove cursor"
                @click="clearCursor"
              />
            </UTooltip>
          </div>
        </Transition>
      </div>

      <div v-if="isLiveStream || streamStatus === 'done'" class="tab-bar-stream">
        <span class="tab-bar-stream-dot" :class="{ 'bg-emerald-500': isLiveStream, 'bg-zinc-500': !isLiveStream, 'animate-none': !isLiveStream }" />
        <span class="tab-bar-stream-count font-mono">
          {{ streamEventCount.toLocaleString() }} cmd
          <span v-if="!isLiveStream" class="text-zinc-500 ml-1">(done)</span>
        </span>
        <label v-if="isLiveStream" class="tab-bar-stream-follow">
          <input v-model="followLive" type="checkbox" class="accent-emerald-500">
          Follow live
        </label>
      </div>

      <div class="tab-bar-actions">
        <UButton
          v-if="!embeddedPanel"
          icon="i-lucide-columns-2"
          label="Compare"
          color="neutral"
          variant="subtle"
          size="sm"
          to="/compare"
        />
        <TraceRowHitStats class="tab-bar-action" />
        <TraceTimingBottlenecks class="tab-bar-action" />
        <TraceSettingsPopover class="tab-bar-action" />
        <TraceCommandColorLegend v-if="sessionStore.spec" class="tab-bar-action" />
      </div>
    </div>
    <div class="relative flex-1 min-h-0 overflow-hidden">
      <div
        v-if="compareAlignMode"
        class="absolute z-30 top-2 left-1/2 -translate-x-1/2 rounded-md border border-amber-400/40 bg-neutral-950/90 px-3 py-1.5 text-xs text-amber-200 shadow-lg pointer-events-none"
      >
        Select a command to align this trace
      </div>
      <canvas ref="canvas" class="block h-full w-full" :class="hoveredEvent && !cursorMode ? 'cursor-pointer' : 'cursor-crosshair'" />
      <canvas
        ref="labelCanvas"
        class="pointer-events-none absolute inset-0 h-full w-full"
        aria-hidden="true"
      />
    </div>
    <TraceTimeline
      :view-state="viewState"
      :cursor-time="cursorTime"
      @seek="(s: number, d: number) => { viewState.start = s; viewState.duration = d; }"
    />

    <!-- Tooltip -->
    <div
      v-if="hoveredEvent || throughputHover"
      ref="tooltip"
      class="fixed z-50 bg-zinc-800/95 backdrop-blur-sm px-3 py-2.5 rounded-lg shadow-xl border border-zinc-700/50 pointer-events-none text-zinc-200"
      :style="tooltipStyle"
    >
      <!-- Throughput view tooltip -->
      <template v-if="throughputHover">
        <div class="flex items-center gap-2">
          <div
            class="size-3 rounded shrink-0"
            :style="{ backgroundColor: throughputHover.series === 'data' ? '#3b82f6' : '#f59e0b' }"
          />
          <span class="font-semibold text-sm">
            {{ throughputHover.series === 'data' ? 'Data Bus Utilization' : 'CMD Bus Utilization' }}
          </span>
        </div>
        <div class="flex items-center gap-3 mt-1.5 text-xs font-mono">
          <span><span class="text-zinc-500">value</span> {{ (throughputHover.value * 100).toFixed(2) }}%</span>
        </div>
        <div class="text-xs font-mono mt-0.5">
          <span class="text-zinc-500">bin</span>
          {{ formatCycles(throughputHover.binStartTime) }} - {{ formatCycles(throughputHover.binEndTime) }} clk
        </div>
        <div class="text-[10px] text-zinc-500 mt-1">
          Grouping Bin Size: (nBL*32 cycles)
        </div>
      </template>

      <!-- Request view tooltip -->
      <template v-else-if="hoveredEvent?.bus === 'request'">
        <div class="flex items-center gap-2">
          <div
            class="size-3 rounded shrink-0"
            :style="{ backgroundColor: sessionStore.getRequestTypeColor(hoveredEvent.typeId) }"
          />
          <span class="font-semibold text-sm">{{ sessionStore.getRequestTypeName(hoveredEvent.typeId) }}</span>
          <span
            class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-400"
          >REQ</span>
        </div>

        <div class="flex flex-col gap-0.5 mt-1.5 text-xs font-mono">
          <div class="flex items-center gap-3">
            <span><span class="text-zinc-500">arrive</span> {{ hoveredEvent.clk }} clk</span>
          </div>
          <div class="flex items-center gap-3">
            <span><span class="text-zinc-500">queued</span> {{ hoveredEvent.queueDelay }} clk</span>
            <span><span class="text-zinc-500">active</span> {{ hoveredEvent.duration }} clk</span>
          </div>
          <div v-if="hoveredEvent.sourceId >= 0" class="flex items-center gap-3">
            <span><span class="text-zinc-500">src</span> {{ hoveredEvent.sourceId }}</span>
          </div>
          <div v-if="hoveredEvent.requestId != null && hoveredEvent.requestId >= 0n" class="flex items-center gap-3">
            <span><span class="text-zinc-500">request</span> #{{ hoveredEvent.requestId }}</span>
            <span v-if="hoveredEvent.selectedView != null && hoveredEvent.selectedView >= 0">
              <span class="text-zinc-500">view</span> {{ viewName(hoveredEvent.selectedView) }}
            </span>
          </div>
        </div>
      </template>

      <!-- Command view tooltip -->
      <template v-else-if="hoveredEvent">
        <div class="flex items-center gap-2">
          <div
            :style="{ backgroundColor: sessionStore.getCommandColor(hoveredEvent.cmdId) }"
            class="size-3 rounded shrink-0"
          />
          <span class="font-semibold text-sm">{{ sessionStore.getCommandName(hoveredEvent.cmdId) }}</span>
          <span
            class="text-[10px] font-mono px-1.5 py-0.5 rounded"
            :class="hoveredEvent.isInternal
              ? 'bg-fuchsia-500/15 text-fuchsia-300'
              : hoveredEvent.bus === 'command'
                ? 'bg-emerald-500/15 text-emerald-400'
                : 'bg-sky-500/15 text-sky-400'"
          >
            {{ hoveredEvent.isInternal ? 'INTERNAL' : hoveredEvent.bus === 'command' ? 'CMD' : 'DATA' }}
          </span>
          <span
            v-if="hoveredEvent.selectedView != null && hoveredEvent.selectedView >= 0"
            class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300"
          >VIEW {{ viewName(hoveredEvent.selectedView) }}</span>
          <span
            v-if="hoveredEvent.isRowHit"
            class="text-[10px] font-mono px-1.5 py-0.5 rounded border border-lime-400/70 bg-lime-400/10 text-lime-300"
          >ROW HIT</span>
          <span
            v-if="hoveredAutoPrecharge"
            class="text-[10px] font-mono px-1.5 py-0.5 rounded border border-orange-400/60 bg-orange-400/10 text-orange-300"
          >AUTO-PRECHARGE</span>
        </div>

        <div class="flex items-center gap-3 mt-1.5 text-xs font-mono">
          <span><span class="text-zinc-500">t</span> {{ hoveredEvent.clk }} clk</span>
          <span><span class="text-zinc-500">dur</span> {{ hoveredEvent.duration }} clk</span>
        </div>
        <div v-if="hoveredEvent.bus === 'data' && hoveredEvent.busClk != null" class="text-xs font-mono mt-0.5">
          <span class="text-zinc-500">t_data</span> {{ hoveredEvent.busClk }} clk
        </div>
        <div v-if="hoveredEvent.requestId != null && hoveredEvent.requestId >= 0n" class="text-xs font-mono mt-0.5">
          <span class="text-zinc-500">request</span> #{{ hoveredEvent.requestId }}
          <span v-if="hoveredEvent.finalCmdId != null && hoveredEvent.finalCmdId >= 0" class="ml-3">
            <span class="text-zinc-500">final</span> {{ sessionStore.getCommandName(hoveredEvent.finalCmdId) }}
          </span>
          <span v-if="hoveredEvent.viewCommitted" class="ml-2 text-amber-300">committed</span>
        </div>
        <div v-if="hoveredAutoPrecharge" class="mt-2 pt-1.5 border-t border-zinc-700/50 text-xs font-mono">
          <div>
            <span class="text-zinc-500">recovery</span>
            {{ hoveredAutoPrecharge.recoveryLabel }} = {{ hoveredAutoPrecharge.recoveryCycles }} cyc
          </div>
          <div>
            <span class="text-zinc-500">internal precharge</span>
            nRP = {{ hoveredAutoPrecharge.prechargeCycles }} cyc
          </div>
          <div>
            <span class="text-zinc-500">view {{ viewName(hoveredAutoPrecharge.view) }} reusable</span>
            {{ hoveredAutoPrecharge.readyClk }} clk
          </div>
          <div class="mt-1 text-[10px] text-zinc-500">
            Combined with this command; no separate PRE is issued.
          </div>
        </div>
        <div v-if="hoveredTiming" class="mt-2 pt-1.5 border-t border-zinc-700/50 text-xs font-mono">
          <div>
            <span class="text-zinc-500">earliest</span> {{ hoveredTiming.readyAt }} clk
            <span class="ml-3"><span class="text-zinc-500">slack</span> {{ hoveredTiming.slack }} cyc</span>
          </div>
          <div v-if="hoveredTiming.causes.length" class="mt-1 space-y-0.5">
            <div v-if="hoveredTiming.causes.length > 1" class="text-zinc-500">
              {{ hoveredTiming.causes.length }} equally strict constraints
            </div>
            <div v-for="(cause, idx) in hoveredTiming.causes" :key="`${cause.constraintId}-${cause.sourceEventId}-${idx}`" class="flex items-start gap-1.5">
              <span class="size-2 rounded-full shrink-0 mt-1" :style="{ backgroundColor: cause.color }" />
              <span>
                <span class="text-zinc-500">limited by</span>
                {{ cause.description }}
                <span v-if="cause.sourceCommand" class="ml-2 text-zinc-400">
                  {{ cause.sourceCommand }} @ {{ cause.sourceClk }} (event #{{ cause.sourceEventId }})
                </span>
                <span v-else-if="cause.sourceEventId >= 0n" class="ml-2 text-zinc-400">event #{{ cause.sourceEventId }}</span>
              </span>
            </div>
          </div>
        </div>
      </template>

      <template v-if="hoveredEvent">
        <div class="border-t border-zinc-700/50 my-2" />

        <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono w-full">
          <span v-for="(val, idx) in hoveredEvent.addr" :key="idx">
            <span class="text-zinc-500">{{ sessionStore.getLevelName(idx) }}</span>
            {{ val }}
          </span>
        </div>

        <div class="border-t border-zinc-700/50 mt-2 pt-1.5 text-[10px] text-zinc-500 text-center">
          click to jump to {{ hoveredEvent.bus === 'request' ? 'commands' : 'request' }}
        </div>
      </template>
    </div>

    <div
      v-if="traceLoadStatus"
      class="absolute inset-0 z-40 flex items-center justify-center bg-neutral-950/92 backdrop-blur-[2px]"
    >
      <TraceLoadingStatus :message="traceLoadStatus" />
    </div>

  </div>
</template>

<script setup lang="ts">
import { getEventTimingCauses, timingCauseDescription } from '~/utils/timingCauses';
import { autoPrechargePhases } from '~/utils/eventSemantics';
import { isCompareHostMessage, type ComparePanelId, type ComparePanelMessage } from '~/utils/compareProtocol';
import type { HitResult } from '~/composables/useRenderer';

definePageMeta({ layout: 'trace' });

const route = useRoute();
const embeddedPanel = computed<ComparePanelId | null>(() => {
  if (route.query.embedded !== '1') return null;
  return route.query.panel === 'bottom' ? 'bottom' : 'top';
});

const uiStore = useUIStore();
const tabs = [
  { label: 'Command View', value: 'command' as const },
  { label: 'Request View', value: 'request' as const },
  { label: 'Throughput', value: 'throughput' as const },
];

const sessionStore = useSessionStore();
const { parseTraceAsync } = useTrace();
const traceLoadStatus = useTraceLoadStatus();
const { isLive: isLiveStream, eventCount: streamEventCount, status: streamStatus } = useStreamSession();
/** When true, viewport snaps to the latest cycles as streamed data grows. */
const followLive = ref(true);
const canvas = ref<HTMLCanvasElement | null>(null);
const labelCanvas = ref<HTMLCanvasElement | null>(null);
const tooltip = ref<HTMLDivElement | null>(null);
const compareAlignMode = ref(false);

function selectCompareAnchor(hit: HitResult): boolean {
  const panel = embeddedPanel.value;
  if (!panel || !compareAlignMode.value || hit.bus === 'request') return false;
  const arrays = sessionStore.arrays;
  if (!arrays) return false;
  postCompareMessage({
    type: 'ramulator-compare-anchor',
    panel,
    clk: Number(hit.clk),
    eventId: String(arrays.eventId[hit.index] ?? hit.index),
    command: sessionStore.getCommandName(hit.cmdId),
    address: [...hit.addr],
  });
  compareAlignMode.value = false;
  return true;
}

const {
  viewState,
  stats,
  hoveredEvent,
  throughputHover,
  throughputRangeStats,
  mouseX,
  mouseY,
  rangeSelection,
  rangeStats,
  cursorMode,
  cursorTime,
  setCursorMode,
  setCursorTime,
  clearCursor,
  jumpCursor,
} = useRenderer(canvas, labelCanvas, followLive, selectCompareAnchor);

const canJumpCursor = computed(() => cursorTime.value != null && uiStore.viewMode !== 'throughput');

function toggleCursorMode() {
  setCursorMode(!cursorMode.value);
}

defineShortcuts({
  c: () => toggleCursorMode(),
});

function formatCycles(n: number): string {
  return Math.round(n).toLocaleString('en-US');
}

function viewName(view: number): string {
  return view === 0 ? 'A' : view === 1 ? 'B' : String(view);
}

const hoveredTiming = computed(() => {
  const event = hoveredEvent.value;
  if (!event || event.readyAt == null || event.readyAt < 0n) return null;
  const arrays = sessionStore.arrays;
  const spec = sessionStore.spec;
  return {
    readyAt: event.readyAt,
    slack: event.clk - event.readyAt,
    causes: arrays && spec
      ? getEventTimingCauses(arrays, spec, event.index).map(cause => ({
          ...cause,
          description: timingCauseDescription(cause, arrays, spec, event.index),
        }))
      : [],
  };
});

const hoveredAutoPrecharge = computed(() => {
  const event = hoveredEvent.value;
  const spec = sessionStore.spec;
  if (!event || !spec || event.bus !== 'command') return null;
  const phases = autoPrechargePhases(spec, event.cmdId);
  return phases
    ? { ...phases, readyClk: event.clk + BigInt(phases.totalCycles) }
    : null;
});

const tooltipStyle = computed(() => {
  const offset = 12;
  const padding = 8;
  let left = mouseX.value + offset;
  let top = mouseY.value + offset;

  if (!import.meta.client) {
    return { left: `${left}px`, top: `${top}px` };
  }

  const tw = tooltip.value?.offsetWidth ?? 260;
  const th = tooltip.value?.offsetHeight ?? 120;

  if (left + tw > window.innerWidth - padding) left = mouseX.value - tw - offset;
  if (top + th > window.innerHeight - padding) top = mouseY.value - th - offset;

  return {
    left: `${Math.max(padding, left)}px`,
    top: `${Math.max(padding, top)}px`,
  };
});

function postCompareMessage(message: ComparePanelMessage) {
  if (!embeddedPanel.value || window.parent === window) return;
  window.parent.postMessage(message, window.location.origin);
}

let applyingCompareViewport = false;
let applyingCompareCursor = false;

function applyCompareViewport(start: number, duration: number) {
  const span = Math.max(0, viewState.maxTime - viewState.minTime);
  if (span <= 0) return;
  const nextDuration = Math.max(
    Math.min(viewState.minDuration, span),
    Math.min(duration, span, viewState.maxDuration),
  );
  const maxStart = viewState.maxTime - nextDuration;
  applyingCompareViewport = true;
  viewState.duration = nextDuration;
  viewState.start = Math.max(viewState.minTime, Math.min(start, maxStart));
  nextTick(() => { applyingCompareViewport = false; });
}

function applyCompareCursor(time: number | null) {
  applyingCompareCursor = true;
  setCursorTime(time);
  nextTick(() => { applyingCompareCursor = false; });
}

async function onCompareHostMessage(event: MessageEvent) {
  const panel = embeddedPanel.value;
  if (!panel || event.origin !== window.location.origin || event.source !== window.parent) return;
  if (!isCompareHostMessage(event.data) || event.data.panel !== panel) return;
  if (event.data.type === 'ramulator-compare-set-viewport') {
    applyCompareViewport(event.data.start, event.data.duration);
    return;
  }
  if (event.data.type === 'ramulator-compare-set-cursor') {
    applyCompareCursor(event.data.time);
    return;
  }
  if (event.data.type === 'ramulator-compare-align-mode') {
    compareAlignMode.value = event.data.enabled;
    if (event.data.enabled) {
      uiStore.setViewMode('command');
      setCursorMode(false);
    }
    return;
  }
  if (event.data.type !== 'ramulator-compare-load') return;

  traceLoadStatus.value = `Loading ${event.data.name}…`;
  try {
    const trace = await parseTraceAsync(event.data.buffer, {
      onProgress: message => { traceLoadStatus.value = message; },
    });
    sessionStore.loadTrace(trace);
    uiStore.setViewMode('command');
    traceLoadStatus.value = null;
    postCompareMessage({
      type: 'ramulator-compare-loaded',
      panel,
      name: event.data.name,
      dramType: trace.header.dramType,
      events: trace.header.numEntries,
    });
  } catch (error) {
    traceLoadStatus.value = null;
    postCompareMessage({
      type: 'ramulator-compare-error',
      panel,
      message: error instanceof Error ? error.message : String(error),
    });
  }
}

watch(
  () => [viewState.start, viewState.duration] as const,
  ([start, duration]) => {
    const panel = embeddedPanel.value;
    if (!panel || !sessionStore.isLoaded || applyingCompareViewport) return;
    postCompareMessage({ type: 'ramulator-compare-viewport', panel, start, duration });
  },
  { flush: 'post' },
);

watch(cursorTime, (time) => {
  const panel = embeddedPanel.value;
  if (!panel || !sessionStore.isLoaded || applyingCompareCursor) return;
  postCompareMessage({ type: 'ramulator-compare-cursor', panel, time });
}, { flush: 'post' });

onMounted(() => {
  uiStore.hydrateSettings();
  if (embeddedPanel.value) {
    window.addEventListener('message', onCompareHostMessage);
    postCompareMessage({ type: 'ramulator-compare-ready', panel: embeddedPanel.value });
  }
});

onUnmounted(() => {
  window.removeEventListener('message', onCompareHostMessage);
});
</script>

<style scoped>
.tab-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px;
  height: 40px;
  background: var(--ui-bg-muted);
  gap: 8px;
  border-bottom: 1px solid color-mix(in srgb, var(--ui-border) 50%, transparent);
}

.tab-bar-tabs {
  display: flex;
  align-items: flex-end;
  align-self: flex-end;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.tab-bar-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  align-self: center;
}

.tab-bar-action {
  flex-shrink: 0;
  align-self: center;
}

.browser-tab {
  position: relative;
  padding: 6px 16px;
  font-size: 13px;
  color: var(--ui-text-dimmed);
  background: transparent;
  border: none;
  cursor: pointer;
  border-radius: 8px 8px 0 0;
  transition: background 0.15s, color 0.15s;
  margin-bottom: -1px;
  white-space: nowrap;
}

.browser-tab:hover:not(.active) {
  background: color-mix(in srgb, var(--ui-bg-elevated) 60%, transparent);
  color: var(--ui-text-muted);
}

.browser-tab.active {
  background: var(--ui-bg);
  color: var(--ui-text);
  border: 1px solid color-mix(in srgb, var(--ui-border) 50%, transparent);
  border-bottom-color: var(--ui-bg);
}

/* ── Range selection inline stats / hint ─────────────────── */

.tab-bar-range {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  align-self: center;
  border-radius: 8px;
  background: color-mix(in srgb, var(--ui-bg-elevated) 34%, transparent);
}

.range-stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #d4d4d8;
  line-height: 1.25;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  background: color-mix(in srgb, var(--ui-bg-muted) 55%, transparent);
}

.range-stat-label {
  color: #71717a;
  letter-spacing: 0.02em;
}

.range-sep {
  width: 1px;
  height: 14px;
  background: color-mix(in srgb, var(--ui-border) 55%, transparent);
  flex-shrink: 0;
}

.range-hint {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 6px;
  font-size: 11px;
  color: #7c7c8a;
  line-height: 1.25;
  white-space: nowrap;
  background: color-mix(in srgb, var(--ui-bg-muted) 35%, transparent);
}

.tab-bar-cursor {
  display: flex;
  align-items: center;
  gap: 0;
  flex-shrink: 0;
  align-self: center;
  overflow: hidden;
  border-radius: 9px;
  background: transparent;
  transition: background 0.15s ease, box-shadow 0.15s ease;
}

.tab-bar-cursor.is-open {
  background: color-mix(in srgb, var(--ui-bg-elevated) 42%, rgba(251, 191, 36, 0.08));
  box-shadow: inset 0 0 0 1px rgba(251, 191, 36, 0.22);
}

.tab-bar-cursor-button {
  cursor: pointer;
  border-radius: 8px;
}

.cursor-toolkit {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  min-width: 0;
  padding: 0 3px 0 4px;
  border-left: 1px solid color-mix(in srgb, var(--ui-border) 48%, transparent);
}

.cursor-toolkit-sep {
  width: 1px;
  height: 14px;
  margin: 0 2px;
  background: color-mix(in srgb, var(--ui-border) 52%, transparent);
  flex-shrink: 0;
}

.cursor-toolkit-enter-active,
.cursor-toolkit-leave-active {
  transition: max-width 0.18s ease, opacity 0.12s ease, transform 0.18s ease;
}

.cursor-toolkit-enter-from,
.cursor-toolkit-leave-to {
  max-width: 0;
  opacity: 0;
  transform: translateX(-6px);
}

.cursor-toolkit-enter-to,
.cursor-toolkit-leave-from {
  max-width: 260px;
  opacity: 1;
  transform: translateX(0);
}

.cursor-readout {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  line-height: 1.25;
  color: #fef3c7;
  background: rgba(251, 191, 36, 0.11);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.cursor-readout.is-empty {
  color: #a1a1aa;
  background: transparent;
}

.cursor-readout-label {
  color: #fbbf24;
  letter-spacing: 0.02em;
}

.tab-bar-stream {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  font-size: 11px;
  color: #a1a1aa;
}

.tab-bar-stream-dot {
  width: 8px;
  height: 8px;
  border-radius: 9999px;
}

.tab-bar-stream-dot.bg-emerald-500 {
  animation: stream-pulse 1.2s ease-in-out infinite;
}

@keyframes stream-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.tab-bar-stream-follow {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
</style>
