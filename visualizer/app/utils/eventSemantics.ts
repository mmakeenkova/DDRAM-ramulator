import type { ParsedTrace, TraceArrays, TraceSpec } from '~/composables/useTrace';

export const ROW_ACCESS_NONE = 0;
export const ROW_ACCESS_MISS = 1;
export const ROW_ACCESS_HIT = 2;

export const VIEW_BORDER_COLORS = {
  A: '#22d3ee',
  B: '#f472b6',
} as const;

export const ROW_HIT_BORDER_COLOR = '#a3e635';
export const AUTO_PRECHARGE_RECOVERY_COLOR = '#a1a1aa';
export const AUTO_PRECHARGE_COLOR = '#fb923c';

export interface AutoPrechargePhases {
  view: 0 | 1;
  operation: 'read' | 'write';
  recoveryLabel: string;
  recoveryCycles: number;
  prechargeCycles: number;
  totalCycles: number;
}

export interface RowHitBucket {
  accesses: number;
  hits: number;
}

export interface RowHitSummary {
  available: boolean;
  accesses: number;
  hits: number;
  misses: number;
  reads: RowHitBucket;
  writes: RowHitBucket;
  viewA: RowHitBucket;
  viewB: RowHitBucket;
}

export interface RowHitAnalysis {
  classification: Uint8Array;
  summary: RowHitSummary;
}

function emptyBucket(): RowHitBucket {
  return { accesses: 0, hits: 0 };
}

function emptySummary(available: boolean): RowHitSummary {
  return {
    available,
    accesses: 0,
    hits: 0,
    misses: 0,
    reads: emptyBucket(),
    writes: emptyBucket(),
    viewA: emptyBucket(),
    viewB: emptyBucket(),
  };
}

/** Resolve view metadata, falling back to DDRAM-P's command-name suffix. */
export function eventView(arrays: TraceArrays, spec: TraceSpec, index: number): number {
  const recorded = arrays.selectedView[index] ?? -1;
  if (recorded === 0 || recorded === 1) return recorded;
  const name = spec.commandNames[arrays.cmdId[index] ?? -1]?.toUpperCase() ?? '';
  if (/(?:^|_)A$/.test(name)) return 0;
  if (/(?:^|_)B$/.test(name)) return 1;
  return -1;
}

/** Human-readable DDRAM-O data-layout contract carried by a request. */
export function eventLayoutLabel(arrays: TraceArrays, index: number): string | null {
  const layout = arrays.pudLayout[index] ?? 0;
  if (layout === 0) return null;
  const kind = layout === 1 ? 'Bit-serial' : `Layout ${layout}`;
  const id = arrays.layoutId[index] ?? -1n;
  const version = arrays.layoutVersion[index] ?? -1n;
  if (id < 0n) return kind;
  return version >= 0n ? `${kind} · layout ${id} v${version}` : `${kind} · layout ${id}`;
}

export function eventLayoutShortLabel(arrays: TraceArrays, index: number): string | null {
  if ((arrays.pudLayout[index] ?? 0) !== 1) return null;
  const id = arrays.layoutId[index] ?? -1n;
  const version = arrays.layoutVersion[index] ?? -1n;
  if (id < 0n) return 'BS';
  return version >= 0n ? `BS L${id}v${version}` : `BS L${id}`;
}

function timingValue(spec: TraceSpec, name: string): number | null {
  const index = spec.timingNames.indexOf(name);
  return index >= 0 ? spec.timingValues[index] ?? null : null;
}

/** Decode the internal recovery and nRP phases carried by DDRAM-P RDA/WRA. */
export function autoPrechargePhases(
  spec: TraceSpec,
  commandId: number,
): AutoPrechargePhases | null {
  const name = spec.commandNames[commandId]?.toUpperCase() ?? '';
  const match = /^(RDA|WRA)_([AB])$/.exec(name);
  if (!match) return null;

  const nRP = timingValue(spec, 'nRP');
  if (nRP == null) return null;
  const view = match[2] === 'A' ? 0 : 1;
  if (match[1] === 'RDA') {
    const nRTP = timingValue(spec, 'nRTP');
    if (nRTP == null) return null;
    return {
      view,
      operation: 'read',
      recoveryLabel: 'nRTP',
      recoveryCycles: nRTP,
      prechargeCycles: nRP,
      totalCycles: nRTP + nRP,
    };
  }

  const nCWL = timingValue(spec, 'nCWL');
  const nBL = timingValue(spec, 'nBL');
  const nWR = timingValue(spec, 'nWR');
  if (nCWL == null || nBL == null || nWR == null) return null;
  const recoveryCycles = nCWL + nBL + nWR;
  return {
    view,
    operation: 'write',
    recoveryLabel: 'nCWL + nBL + nWR',
    recoveryCycles,
    prechargeCycles: nRP,
    totalCycles: recoveryCycles + nRP,
  };
}

/**
 * Classify terminal data accesses using their complete request command stream.
 * A request that issued an opening command needed to establish its row and is
 * therefore a miss; an access with no opening command for that request is a hit.
 */
export function analyzeRowHits(trace: ParsedTrace): RowHitAnalysis {
  const { arrays, spec, header } = trace;
  const count = arrays.clk.length;
  const classification = new Uint8Array(count);
  const hasRequestDiagnostics = header.version[0] > 1
    || (header.version[0] === 1 && header.version[1] >= 2);
  const summary = emptySummary(hasRequestDiagnostics);
  if (!hasRequestDiagnostics) return { classification, summary };

  const openedRequests = new Set<bigint>();
  for (let i = 0; i < count; i++) {
    const requestId = arrays.requestId[i] ?? -1n;
    const typeId = arrays.typeId[i] ?? -1;
    if (requestId >= 0n && (typeId === 0 || typeId === 1)
      && spec.commandMeta[arrays.cmdId[i] ?? -1]?.isOpening) {
      openedRequests.add(requestId);
    }
  }

  for (let i = 0; i < count; i++) {
    const command = spec.commandMeta[arrays.cmdId[i] ?? -1];
    const requestId = arrays.requestId[i] ?? -1n;
    const typeId = arrays.typeId[i] ?? -1;
    if (!command?.isAccessing || requestId < 0n || (typeId !== 0 && typeId !== 1)) continue;

    const hit = !openedRequests.has(requestId);
    classification[i] = hit ? ROW_ACCESS_HIT : ROW_ACCESS_MISS;
    summary.accesses++;
    if (hit) summary.hits++;
    else summary.misses++;

    const operation = typeId === 0 ? summary.reads : summary.writes;
    operation.accesses++;
    if (hit) operation.hits++;

    const view = eventView(arrays, spec, i);
    const viewBucket = view === 0 ? summary.viewA : view === 1 ? summary.viewB : null;
    if (viewBucket) {
      viewBucket.accesses++;
      if (hit) viewBucket.hits++;
    }
  }

  return { classification, summary };
}
