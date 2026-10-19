import type { TimingConstraintInfo, TraceArrays, TraceSpec } from '~/composables/useTrace';

export interface EventTimingCause {
  constraintId: number;
  constraint?: TimingConstraintInfo;
  sourceEventId: bigint;
  sourceIndex: number;
  sourceCommand?: string;
  sourceClk?: bigint;
  level: number;
  color: string;
}

const FALLBACK_COLORS = ['#22c55e', '#38bdf8', '#f59e0b', '#a78bfa', '#f43f5e', '#14b8a6'];

/** Stable semantic colors make common DRAM timing families recognizable across traces. */
export function timingConstraintColor(label: string): string {
  const name = label.toUpperCase();
  if (/NRCD/.test(name)) return '#22c55e';
  if (/NRRD|NFAW|NXACT/.test(name)) return '#f59e0b';
  if (/NCCD|CMD|COMMAND/.test(name)) return '#3b82f6';
  if (/NWTR|NRTW|TURN/.test(name)) return '#a78bfa';
  if (/NRFC|REF|RFM/.test(name)) return '#ec4899';
  if (/NRP|NRAS|NRTP|NWR/.test(name)) return '#f97316';

  let hash = 0;
  for (let i = 0; i < label.length; i++) hash = ((hash << 5) - hash + label.charCodeAt(i)) | 0;
  return FALLBACK_COLORS[Math.abs(hash) % FALLBACK_COLORS.length]!;
}

function readableCommand(name: string | undefined): string {
  return (name ?? 'command').replaceAll('_', ' ');
}

/** Human-facing edge text, while retaining the exact spec label and value. */
export function timingCauseDescription(
  cause: EventTimingCause,
  arrays: TraceArrays,
  spec: TraceSpec,
  targetIndex: number,
): string {
  const source = readableCommand(cause.sourceCommand);
  const target = readableCommand(spec.commandNames[arrays.cmdId[targetIndex]!]);
  const constraint = cause.constraint;
  if (!constraint) return `${source} → ${target} delay`;
  const unit = constraint.value === 1 ? 'cycle' : 'cycles';
  return `${source} → ${target} delay · ${constraint.label} = ${constraint.value} ${unit}`;
}

function sourceIndexFor(arrays: TraceArrays, sourceEventId: bigint): number {
  const likely = Number(sourceEventId);
  if (likely >= 0 && likely < arrays.eventId.length && arrays.eventId[likely] === sourceEventId) return likely;
  // Event IDs are normally dense, but imported/combined traces need not be.
  for (let i = 0; i < arrays.eventId.length; i++) {
    if (arrays.eventId[i] === sourceEventId) return i;
  }
  return -1;
}

function makeCause(
  arrays: TraceArrays,
  spec: TraceSpec,
  constraintId: number,
  sourceEventId: bigint,
  level: number,
): EventTimingCause {
  const constraint = constraintId >= 0 ? spec.timingConstraints[constraintId] : undefined;
  const sourceIndex = sourceEventId >= 0n ? sourceIndexFor(arrays, sourceEventId) : -1;
  return {
    constraintId,
    constraint,
    sourceEventId,
    sourceIndex,
    sourceCommand: sourceIndex >= 0 ? spec.commandNames[arrays.cmdId[sourceIndex]!] : undefined,
    sourceClk: sourceIndex >= 0 ? arrays.clk[sourceIndex] : undefined,
    level,
    color: timingConstraintColor(constraint?.label ?? `constraint-${constraintId}`),
  };
}

/** Return every equally strict cause when v1.3 data exists, otherwise the v1.2 primary cause. */
export function getEventTimingCauses(
  arrays: TraceArrays,
  spec: TraceSpec,
  eventIndex: number,
): EventTimingCause[] {
  if (eventIndex < 0 || eventIndex >= arrays.clk.length) return [];
  if (arrays.tieOffsets.length > eventIndex + 1) {
    const start = Number(arrays.tieOffsets[eventIndex]!);
    const end = Number(arrays.tieOffsets[eventIndex + 1]!);
    if (end > start) {
      const result: EventTimingCause[] = [];
      for (let i = start; i < end; i++) {
        result.push(makeCause(
          arrays,
          spec,
          arrays.tieConstraintId[i] ?? -1,
          arrays.tieSourceEventId[i] ?? -1n,
          arrays.tieConstraintLevel[i] ?? -1,
        ));
      }
      return result;
    }
  }

  const constraintId = arrays.constraintId[eventIndex] ?? -1;
  const sourceEventId = arrays.causeEventId[eventIndex] ?? -1n;
  if (constraintId < 0 && sourceEventId < 0n) return [];
  return [makeCause(arrays, spec, constraintId, sourceEventId, arrays.constraintLevel[eventIndex] ?? -1)];
}
