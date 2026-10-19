<template>
  <main class="h-screen w-screen overflow-hidden bg-neutral-950 text-zinc-200 flex flex-col">
    <header class="h-12 shrink-0 border-b border-neutral-800 flex items-center gap-3 px-3">
      <UButton icon="i-lucide-arrow-left" label="Single view" color="neutral" variant="ghost" size="sm" to="/" />
      <div class="font-medium text-sm">Trace comparison</div>
      <div v-if="alignmentLabel" class="text-xs font-mono text-amber-300 truncate max-w-[42vw]">
        {{ alignmentLabel }}
      </div>
      <div v-else class="text-xs text-zinc-500">Load one trace into each panel</div>
      <div class="ml-auto flex items-center gap-4 text-xs text-zinc-400">
        <label class="flex items-center gap-1.5 cursor-pointer">
          <input v-model="syncNavigation" type="checkbox" class="accent-sky-500">
          Sync navigation
        </label>
        <label class="flex items-center gap-1.5 cursor-pointer">
          <input v-model="linkCursor" type="checkbox" class="accent-sky-500">
          Linked cursor
        </label>
        <UButton
          :icon="aligning ? 'i-lucide-mouse-pointer-click' : 'i-lucide-align-horizontal-space-around'"
          :label="aligning ? 'Cancel alignment' : aligned ? 'Realign' : 'Align commands'"
          :color="aligning ? 'warning' : 'neutral'"
          :variant="aligning ? 'soft' : 'subtle'"
          size="sm"
          :disabled="!bothLoaded()"
          @click="aligning ? cancelAlignment() : beginAlignment()"
        />
        <UButton
          v-if="aligned"
          icon="i-lucide-unlink"
          label="Clear"
          color="neutral"
          variant="ghost"
          size="sm"
          @click="clearAlignment"
        />
      </div>
    </header>

    <section ref="splitRoot" class="relative flex-1 min-h-0">
      <div class="absolute inset-x-0 top-0" :style="{ height: `${splitPercent}%` }">
        <ComparePanelHeader panel="top" :state="panels.top" @load="loadFile('top', $event)" />
        <iframe
          ref="topFrame"
          title="Top trace"
          src="/trace?embedded=1&panel=top"
          class="absolute inset-x-0 bottom-0 w-full border-0"
          style="top: 36px; height: calc(100% - 36px)"
        />
      </div>

      <button
        type="button"
        class="absolute inset-x-0 z-30 h-2 -translate-y-1/2 cursor-row-resize bg-neutral-700/40 hover:bg-primary-500/70 transition-colors"
        :style="{ top: `${splitPercent}%` }"
        aria-label="Resize comparison panels"
        @pointerdown="startResize"
      />

      <div class="absolute inset-x-0 bottom-0" :style="{ top: `${splitPercent}%` }">
        <ComparePanelHeader panel="bottom" :state="panels.bottom" @load="loadFile('bottom', $event)" />
        <iframe
          ref="bottomFrame"
          title="Bottom trace"
          src="/trace?embedded=1&panel=bottom"
          class="absolute inset-x-0 bottom-0 w-full border-0"
          style="top: 36px; height: calc(100% - 36px)"
        />
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import type { ComparePanelId, ComparePanelMessage, CompareHostMessage } from '~/utils/compareProtocol';

definePageMeta({ layout: false });

interface PanelState {
  ready: boolean;
  loaded: boolean;
  loading: boolean;
  name: string;
  detail: string;
  error: string;
}

interface AlignmentAnchor {
  clk: number;
  eventId: string;
  command: string;
  address: number[];
}

const panels = reactive<Record<ComparePanelId, PanelState>>({
  top: { ready: false, loaded: false, loading: false, name: '', detail: '', error: '' },
  bottom: { ready: false, loaded: false, loading: false, name: '', detail: '', error: '' },
});
const syncNavigation = ref(true);
const linkCursor = ref(true);
const anchors = reactive<Record<ComparePanelId, number>>({ top: 0, bottom: 0 });
const viewports = reactive<Record<ComparePanelId, { start: number; duration: number } | null>>({
  top: null,
  bottom: null,
});
const alignmentSelections = reactive<Record<ComparePanelId, AlignmentAnchor | null>>({
  top: null,
  bottom: null,
});
const aligning = ref(false);
const aligned = computed(() => alignmentSelections.top !== null && alignmentSelections.bottom !== null);
const alignmentLabel = computed(() => {
  if (aligning.value) {
    const waiting = (['top', 'bottom'] as ComparePanelId[])
      .filter(panel => !alignmentSelections[panel])
      .join(' and ');
    return `Select a command in ${waiting}`;
  }
  if (!aligned.value) return '';
  const top = alignmentSelections.top!;
  const bottom = alignmentSelections.bottom!;
  return `${top.command} #${top.eventId} @ ${top.clk} ↔ ${bottom.command} #${bottom.eventId} @ ${bottom.clk}`;
});
const topFrame = ref<HTMLIFrameElement | null>(null);
const bottomFrame = ref<HTMLIFrameElement | null>(null);
const splitRoot = ref<HTMLElement | null>(null);
const splitPercent = ref(50);
let resizing = false;

function frameFor(panel: ComparePanelId): HTMLIFrameElement | null {
  return panel === 'top' ? topFrame.value : bottomFrame.value;
}

function post(panel: ComparePanelId, message: CompareHostMessage, transfer?: Transferable[]) {
  frameFor(panel)?.contentWindow?.postMessage(message, window.location.origin, transfer ?? []);
}

async function loadFile(panel: ComparePanelId, file: File) {
  if (aligned.value || aligning.value) clearAlignment();
  const state = panels[panel];
  state.loading = true;
  state.loaded = false;
  state.error = '';
  state.name = file.name;
  try {
    const buffer = await file.arrayBuffer();
    post(panel, { type: 'ramulator-compare-load', panel, name: file.name, buffer }, [buffer]);
  } catch (error) {
    state.loading = false;
    state.error = error instanceof Error ? error.message : String(error);
  }
}

function otherPanel(panel: ComparePanelId): ComparePanelId {
  return panel === 'top' ? 'bottom' : 'top';
}

function bothLoaded(): boolean {
  return panels.top.loaded && panels.bottom.loaded;
}

function setAlignmentMode(enabled: boolean) {
  for (const panel of ['top', 'bottom'] as ComparePanelId[]) {
    if (panels[panel].ready) {
      post(panel, { type: 'ramulator-compare-align-mode', panel, enabled });
    }
  }
}

function beginAlignment() {
  if (!bothLoaded()) return;
  alignmentSelections.top = null;
  alignmentSelections.bottom = null;
  aligning.value = true;
  setAlignmentMode(true);
}

function cancelAlignment() {
  aligning.value = false;
  alignmentSelections.top = null;
  alignmentSelections.bottom = null;
  setAlignmentMode(false);
}

function clearAlignment() {
  cancelAlignment();
  anchors.top = 0;
  anchors.bottom = 0;
  const source = viewports.top;
  if (syncNavigation.value && bothLoaded() && source) {
    post('bottom', {
      type: 'ramulator-compare-set-viewport',
      panel: 'bottom',
      start: source.start,
      duration: source.duration,
    });
  }
}

function completeAlignment() {
  const top = alignmentSelections.top;
  const bottom = alignmentSelections.bottom;
  if (!top || !bottom) return;
  anchors.top = top.clk;
  anchors.bottom = bottom.clk;
  aligning.value = false;
  setAlignmentMode(false);

  const duration = viewports.top?.duration ?? viewports.bottom?.duration ?? 100;
  post('top', {
    type: 'ramulator-compare-set-viewport',
    panel: 'top',
    start: top.clk - duration / 2,
    duration,
  });
  post('bottom', {
    type: 'ramulator-compare-set-viewport',
    panel: 'bottom',
    start: bottom.clk - duration / 2,
    duration,
  });
  if (linkCursor.value) {
    post('top', { type: 'ramulator-compare-set-cursor', panel: 'top', time: top.clk });
    post('bottom', { type: 'ramulator-compare-set-cursor', panel: 'bottom', time: bottom.clk });
  }
}

function onMessage(event: MessageEvent<ComparePanelMessage>) {
  if (event.origin !== window.location.origin) return;
  const message = event.data;
  if (!message || !('panel' in message) || !(message.panel in panels)) return;
  if (event.source !== frameFor(message.panel)?.contentWindow) return;
  const state = panels[message.panel];
  if (message.type === 'ramulator-compare-ready') {
    state.ready = true;
  } else if (message.type === 'ramulator-compare-loaded') {
    state.loading = false;
    state.loaded = true;
    state.name = message.name;
    state.detail = `${message.dramType} · ${message.events.toLocaleString()} commands`;
  } else if (message.type === 'ramulator-compare-error') {
    state.loading = false;
    state.loaded = false;
    state.error = message.message;
  } else if (message.type === 'ramulator-compare-viewport') {
    viewports[message.panel] = { start: message.start, duration: message.duration };
    if (!syncNavigation.value || !bothLoaded()) return;
    const target = otherPanel(message.panel);
    const relativeStart = message.start - anchors[message.panel];
    post(target, {
      type: 'ramulator-compare-set-viewport',
      panel: target,
      start: relativeStart + anchors[target],
      duration: message.duration,
    });
  } else if (message.type === 'ramulator-compare-cursor') {
    if (!linkCursor.value || !bothLoaded()) return;
    const target = otherPanel(message.panel);
    const targetTime = message.time == null
      ? null
      : message.time - anchors[message.panel] + anchors[target];
    post(target, { type: 'ramulator-compare-set-cursor', panel: target, time: targetTime });
  } else if (message.type === 'ramulator-compare-anchor') {
    if (!aligning.value) return;
    alignmentSelections[message.panel] = {
      clk: message.clk,
      eventId: message.eventId,
      command: message.command,
      address: message.address,
    };
    completeAlignment();
  }
}

function startResize(event: PointerEvent) {
  resizing = true;
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function resize(event: PointerEvent) {
  if (!resizing || !splitRoot.value) return;
  const rect = splitRoot.value.getBoundingClientRect();
  splitPercent.value = Math.max(25, Math.min(75, ((event.clientY - rect.top) / rect.height) * 100));
}

function stopResize() {
  resizing = false;
}

onMounted(() => {
  window.addEventListener('message', onMessage);
  window.addEventListener('pointermove', resize);
  window.addEventListener('pointerup', stopResize);
});

onUnmounted(() => {
  window.removeEventListener('message', onMessage);
  window.removeEventListener('pointermove', resize);
  window.removeEventListener('pointerup', stopResize);
});
</script>
