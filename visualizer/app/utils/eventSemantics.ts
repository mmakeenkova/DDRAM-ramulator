import type { ParsedTrace, TraceArrays, TraceSpec } from '~/composables/useTrace';

export const ROW_ACCESS_NONE = 0;
export const ROW_ACCESS_MISS = 1;
export const ROW_ACCESS_HIT = 2;

export const VIEW_BORDER_COLORS = {
  A: '#22d3ee',
  B: '#f472b6',
} as const;

export const ROW_HIT_BORDER_COLOR = '#a3e635';

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
