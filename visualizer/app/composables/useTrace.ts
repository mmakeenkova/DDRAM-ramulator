const MAGIC = "RAM2BIN\0";
const HEADER_SIZE = 64;

export interface TraceHeader {
  version: [number, number];
  flags: number;
  levelCount: number;
  commandCount: number;
  timingCount: number;
  channelWidth: number;
  prefetchSize: number;
  dq: number;
  channelId: number;
  readLatency: number;
  numEntries: number;
  dataOffset: number;
  dramType: string;
}

export interface CommandMeta {
  isOpening: boolean;
  isClosing: boolean;
  isAccessing: boolean;
  isRefreshing: boolean;
  isRowCommand: boolean;
  isColumnCommand: boolean;
  isInternal: boolean;
}

export interface TraceSpec {
  levelNames: string[];
  levelSizes: Uint32Array;
  commandNames: string[];
  commandMeta: CommandMeta[];
  commandCycles: Uint8Array;
  timingNames: string[];
  timingValues: Int32Array;
  timingConstraints: TimingConstraintInfo[];
}

export interface TimingConstraintInfo {
  label: string;
  level: number;
  preceding: number;
  following: number;
  value: number;
  window: number;
  sibling: boolean;
  historyGroup: number;
}

export interface TraceArrays {
  clk: BigInt64Array;
  arrive: BigInt64Array;
  cmdId: Uint8Array;
  typeId: Int8Array;
  sourceId: Int16Array;
  addr: Int32Array[];
  eventId: BigInt64Array;
  requestId: BigInt64Array;
  finalCmdId: Int16Array;
  selectedView: Int8Array;
  viewCommitted: Uint8Array;
  readyAt: BigInt64Array;
  causeEventId: BigInt64Array;
  constraintId: Int32Array;
  constraintLevel: Int16Array;
  /** Request::PudLayout: 0=unspecified, 1=bit-serial. */
  pudLayout: Int8Array;
  requiredView: Int8Array;
  layoutId: BigInt64Array;
  layoutVersion: BigInt64Array;
  /** CSR offsets into the tied-cause arrays; length is event count + 1. */
  tieOffsets: BigUint64Array;
  tieSourceEventId: BigInt64Array;
  tieConstraintId: Int32Array;
  tieConstraintLevel: Int16Array;
}

export interface ParsedTrace {
  buffer: ArrayBuffer;
  header: TraceHeader;
  spec: TraceSpec;
  arrays: TraceArrays;
}

function readNullTerminatedStrings(view: DataView, offset: number, count: number): { strings: string[]; bytesRead: number } {
  const strings: string[] = [];
  let pos = offset;
  for (let i = 0; i < count; i++) {
    let end = pos;
    while (view.getUint8(end) !== 0) end++;
    const bytes = new Uint8Array(view.buffer, pos, end - pos);
    strings.push(new TextDecoder().decode(bytes));
    pos = end + 1;
  }
  return { strings, bytesRead: pos - offset };
}

function readNullTerminatedString(view: DataView, offset: number, maxLen: number): string {
  let end = 0;
  while (end < maxLen && view.getUint8(offset + end) !== 0) end++;
  return new TextDecoder().decode(new Uint8Array(view.buffer, offset, end));
}

function parseHeader(view: DataView): TraceHeader {
  const magicBytes = new Uint8Array(view.buffer, 0, 8);
  const magic = new TextDecoder().decode(magicBytes.slice(0, 7));
  if (magic !== MAGIC.slice(0, 7)) {
    throw new Error(`Invalid magic: expected "RAM2BIN", got "${magic}"`);
  }

  return {
    version: [view.getUint8(8), view.getUint8(9)],
    flags: view.getUint16(10, true),
    levelCount: view.getUint16(12, true),
    commandCount: view.getUint16(14, true),
    timingCount: view.getUint16(16, true),
    channelWidth: view.getUint16(18, true),
    prefetchSize: view.getUint16(20, true),
    dq: view.getUint16(22, true),
    channelId: view.getUint32(24, true),
    readLatency: view.getInt32(28, true),
    numEntries: Number(view.getBigUint64(32, true)),
    dataOffset: Number(view.getBigUint64(40, true)),
    dramType: readNullTerminatedString(view, 48, 16),
  };
}

function parseSpec(buf: ArrayBuffer, header: TraceHeader): TraceSpec {
  const view = new DataView(buf);
  let offset = HEADER_SIZE;

  const { strings: levelNames, bytesRead: lnBytes } =
    readNullTerminatedStrings(view, offset, header.levelCount);
  offset += lnBytes;

  const levelSizes = new Uint32Array(header.levelCount);
  for (let i = 0; i < header.levelCount; i++)
    levelSizes[i] = view.getUint32(offset + i * 4, true);
  offset += header.levelCount * 4;

  const { strings: commandNames, bytesRead: cnBytes } =
    readNullTerminatedStrings(view, offset, header.commandCount);
  offset += cnBytes;

  const commandMeta: CommandMeta[] = [];
  for (let i = 0; i < header.commandCount; i++) {
    const bits = view.getUint8(offset + i);
    commandMeta.push({
      isOpening:       !!(bits & (1 << 0)),
      isClosing:       !!(bits & (1 << 1)),
      isAccessing:     !!(bits & (1 << 2)),
      isRefreshing:    !!(bits & (1 << 3)),
      isRowCommand:    !!(bits & (1 << 4)),
      isColumnCommand: !!(bits & (1 << 5)),
      isInternal:      !!(bits & (1 << 6)),
    });
  }
  offset += header.commandCount;

  const commandCycles = new Uint8Array(header.commandCount);
  const hasCommandCycles = header.version[0] > 1 || (header.version[0] === 1 && header.version[1] >= 1);
  if (hasCommandCycles) {
    for (let i = 0; i < header.commandCount; i++)
      commandCycles[i] = view.getUint8(offset + i);
    offset += header.commandCount;
  } else {
    commandCycles.fill(1);
  }

  const { strings: timingNames, bytesRead: tnBytes } =
    readNullTerminatedStrings(view, offset, header.timingCount);
  offset += tnBytes;

  const timingValues = new Int32Array(header.timingCount);
  for (let i = 0; i < header.timingCount; i++)
    timingValues[i] = view.getInt32(offset + i * 4, true);
  offset += header.timingCount * 4;

  const timingConstraints: TimingConstraintInfo[] = [];
  const hasDiagnostics = header.version[0] > 1 || (header.version[0] === 1 && header.version[1] >= 2);
  if (hasDiagnostics && offset + 4 <= header.dataOffset) {
    const count = view.getUint32(offset, true);
    offset += 4;
    for (let i = 0; i < count; i++) {
      const parsed = readNullTerminatedStrings(view, offset, 1);
      const label = parsed.strings[0] ?? '';
      offset += parsed.bytesRead;
      const level = view.getInt16(offset, true); offset += 2;
      const preceding = view.getInt16(offset, true); offset += 2;
      const following = view.getInt16(offset, true); offset += 2;
      const value = view.getInt32(offset, true); offset += 4;
      const window = view.getInt16(offset, true); offset += 2;
      const sibling = view.getUint8(offset) !== 0; offset += 1;
      const historyGroup = view.getInt16(offset, true); offset += 2;
      timingConstraints.push({ label, level, preceding, following, value, window, sibling, historyGroup });
    }
  }

  return { levelNames, levelSizes, commandNames, commandMeta, commandCycles, timingNames, timingValues, timingConstraints };
}

function parseArrays(buf: ArrayBuffer, header: TraceHeader): TraceArrays {
  const D = header.dataOffset;
  const N = header.numEntries;
  const L = header.levelCount;

  const clk      = new BigInt64Array(buf, D,            N);
  const arrive    = new BigInt64Array(buf, D + 8 * N,    N);
  const cmdId     = new Uint8Array(buf,   D + 16 * N,   N);
  const typeId    = new Int8Array(buf,    D + 17 * N,   N);
  const sourceId  = new Int16Array(buf,   D + 18 * N,   N);

  const addr: Int32Array[] = [];
  for (let k = 0; k < L; k++) {
    addr.push(new Int32Array(buf, D + (20 + 4 * k) * N, N));
  }

  const eventId = new BigInt64Array(N);
  const requestId = new BigInt64Array(N);
  const finalCmdId = new Int16Array(N); finalCmdId.fill(-1);
  const selectedView = new Int8Array(N); selectedView.fill(-1);
  const viewCommitted = new Uint8Array(N);
  const readyAt = new BigInt64Array(N); readyAt.fill(-1n);
  const causeEventId = new BigInt64Array(N); causeEventId.fill(-1n);
  const constraintId = new Int32Array(N); constraintId.fill(-1);
  const constraintLevel = new Int16Array(N); constraintLevel.fill(-1);
  const pudLayout = new Int8Array(N);
  const requiredView = new Int8Array(N); requiredView.fill(-1);
  const layoutId = new BigInt64Array(N); layoutId.fill(-1n);
  const layoutVersion = new BigInt64Array(N); layoutVersion.fill(-1n);
  let tieOffsets = new BigUint64Array(N + 1);
  let tieSourceEventId = new BigInt64Array(0);
  let tieConstraintId = new Int32Array(0);
  let tieConstraintLevel = new Int16Array(0);

  const hasDiagnostics = header.version[0] > 1 || (header.version[0] === 1 && header.version[1] >= 2);
  if (hasDiagnostics) {
    const view = new DataView(buf);
    let offset = D + (20 + 4 * L) * N;
    const readI64 = (out: BigInt64Array) => {
      for (let i = 0; i < N; i++) out[i] = view.getBigInt64(offset + i * 8, true);
      offset += N * 8;
    };
    readI64(eventId);
    readI64(requestId);
    for (let i = 0; i < N; i++) finalCmdId[i] = view.getInt16(offset + i * 2, true);
    offset += N * 2;
    for (let i = 0; i < N; i++) selectedView[i] = view.getInt8(offset + i);
    offset += N;
    for (let i = 0; i < N; i++) viewCommitted[i] = view.getUint8(offset + i);
    offset += N;
    readI64(readyAt);
    readI64(causeEventId);
    for (let i = 0; i < N; i++) constraintId[i] = view.getInt32(offset + i * 4, true);
    offset += N * 4;
    for (let i = 0; i < N; i++) constraintLevel[i] = view.getInt16(offset + i * 2, true);
    offset += N * 2;
    const hasTies = header.version[0] > 1 || (header.version[0] === 1 && header.version[1] >= 3);
    if (hasTies) {
      for (let i = 0; i <= N; i++) tieOffsets[i] = view.getBigUint64(offset + i * 8, true);
      offset += (N + 1) * 8;
      const tieCount = Number(tieOffsets[N]);
      tieSourceEventId = new BigInt64Array(tieCount);
      tieConstraintId = new Int32Array(tieCount);
      tieConstraintLevel = new Int16Array(tieCount);
      for (let i = 0; i < tieCount; i++) tieSourceEventId[i] = view.getBigInt64(offset + i * 8, true);
      offset += tieCount * 8;
      for (let i = 0; i < tieCount; i++) tieConstraintId[i] = view.getInt32(offset + i * 4, true);
      offset += tieCount * 4;
      for (let i = 0; i < tieCount; i++) tieConstraintLevel[i] = view.getInt16(offset + i * 2, true);
      offset += tieCount * 2;
    }
    const hasOperationMetadata = header.version[0] > 1
      || (header.version[0] === 1 && header.version[1] >= 4);
    if (hasOperationMetadata && (header.flags & 4) !== 0) {
      for (let i = 0; i < N; i++) pudLayout[i] = view.getInt8(offset + i);
      offset += N;
      for (let i = 0; i < N; i++) requiredView[i] = view.getInt8(offset + i);
      offset += N;
      for (let i = 0; i < N; i++) layoutId[i] = view.getBigInt64(offset + i * 8, true);
      offset += N * 8;
      for (let i = 0; i < N; i++) layoutVersion[i] = view.getBigInt64(offset + i * 8, true);
    }
  } else {
    for (let i = 0; i < N; i++) eventId[i] = BigInt(i);
  }

  return { clk, arrive, cmdId, typeId, sourceId, addr, eventId, requestId, finalCmdId,
    selectedView, viewCommitted, readyAt, causeEventId, constraintId, constraintLevel,
    pudLayout, requiredView, layoutId, layoutVersion,
    tieOffsets, tieSourceEventId, tieConstraintId, tieConstraintLevel };
}

export function parseTrace(buf: ArrayBuffer): ParsedTrace {
  const view = new DataView(buf);
  const header = parseHeader(view);
  const spec = parseSpec(buf, header);
  const arrays = parseArrays(buf, header);
  return { buffer: buf, header, spec, arrays };
}

function yieldToMain(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

export interface ParseTraceAsyncOptions {
  /** Called before each parse step (after the preceding yield) so the UI can show progress. */
  onProgress?: (message: string) => void;
}

/** Same as {@link parseTrace}, but yields so the UI can paint between phases. */
export async function parseTraceAsync(
  buffer: ArrayBuffer,
  options?: ParseTraceAsyncOptions,
): Promise<ParsedTrace> {
  const report = options?.onProgress;
  report?.('Reading header…');
  await yieldToMain();
  const view = new DataView(buffer);
  const header = parseHeader(view);
  report?.('Reading spec (levels, commands, timings)…');
  await yieldToMain();
  const spec = parseSpec(buffer, header);
  report?.('Mapping event arrays…');
  await yieldToMain();
  const arrays = parseArrays(buffer, header);
  return { buffer, header, spec, arrays };
}

export function useTrace() {
  return { parseTrace, parseTraceAsync };
}
