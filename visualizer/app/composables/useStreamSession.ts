/**
 * Browser-side WebSocket client for receiving live-streamed trace data.
 *
 * Stream sessions are rendered incrementally:
 * - `init` creates an empty trace and makes it available to the viewer
 * - `events` are appended to growing typed arrays (O(new_events), not O(total))
 * - `done` performs a final refresh and leaves the trace visible
 *
 * Performance design
 * ------------------
 * Instead of keeping a `StreamEvent[]` JS object array and rebuilding all N
 * typed arrays on every batch, we maintain pre-allocated typed arrays that
 * grow with amortized doubling. Appending a batch is O(batch_size). Building
 * the ParsedTrace is O(1): we just hand out subarray views into the backing
 * buffers — no copy, no BigInt re-conversion.
 */
import type {
  TraceHeader,
  TraceSpec,
  TraceArrays,
  ParsedTrace,
  CommandMeta,
} from '~/composables/useTrace';
import { useSessionStore } from '~/stores/session';

export type StreamStatus = 'idle' | 'connecting' | 'streaming' | 'finalizing' | 'done';

interface StreamEvent {
  clk: number;
  arrive: number;
  cmdId: number;
  typeId: number;
  sourceId: number;
  addr: number[];
  eventId?: number;
  requestId?: number;
  finalCmdId?: number;
  selectedView?: number;
  viewCommitted?: boolean;
  readyAt?: number;
  causeEventId?: number;
  constraintId?: number;
  constraintLevel?: number;
}

interface StreamHeader {
  version: [number, number];
  levelCount: number;
  commandCount: number;
  timingCount: number;
  channelWidth: number;
  prefetchSize: number;
  dq: number;
  channelId: number;
  readLatency: number;
  dramType: string;
}

interface StreamSpec {
  levelNames: string[];
  levelSizes: number[];
  commandNames: string[];
  commandMeta: CommandMeta[];
  commandCycles?: number[];
  timingNames: string[];
  timingValues: number[];
  timingConstraints?: TraceSpec['timingConstraints'];
}

// ── Incremental typed-array state ────────────────────────────────────────────

let _count = 0;
let _capacity = 0;
let _levelCount = 0;
let _clkBuf = new BigInt64Array(0);
let _arriveBuf = new BigInt64Array(0);
let _cmdIdBuf = new Uint8Array(0);
let _typeIdBuf = new Int8Array(0);
let _sourceIdBuf = new Int16Array(0);
let _eventIdBuf = new BigInt64Array(0);
let _requestIdBuf = new BigInt64Array(0);
let _finalCmdIdBuf = new Int16Array(0);
let _selectedViewBuf = new Int8Array(0);
let _viewCommittedBuf = new Uint8Array(0);
let _readyAtBuf = new BigInt64Array(0);
let _causeEventIdBuf = new BigInt64Array(0);
let _constraintIdBuf = new Int32Array(0);
let _constraintLevelBuf = new Int16Array(0);
let _addrBufs: Int32Array[] = [];

/** Cached TraceSpec (does not change during a session). */
let _cachedSpec: TraceSpec | null = null;

function _growBuffers(minCapacity: number) {
  if (minCapacity <= _capacity) return;
  let cap = Math.max(256, _capacity);
  while (cap < minCapacity) cap = cap * 2;

  const newClk = new BigInt64Array(cap);
  const newArrive = new BigInt64Array(cap);
  const newCmdId = new Uint8Array(cap);
  const newTypeId = new Int8Array(cap);
  const newSourceId = new Int16Array(cap);
  const newEventId = new BigInt64Array(cap);
  const newRequestId = new BigInt64Array(cap); newRequestId.fill(-1n);
  const newFinalCmdId = new Int16Array(cap); newFinalCmdId.fill(-1);
  const newSelectedView = new Int8Array(cap); newSelectedView.fill(-1);
  const newViewCommitted = new Uint8Array(cap);
  const newReadyAt = new BigInt64Array(cap); newReadyAt.fill(-1n);
  const newCauseEventId = new BigInt64Array(cap); newCauseEventId.fill(-1n);
  const newConstraintId = new Int32Array(cap); newConstraintId.fill(-1);
  const newConstraintLevel = new Int16Array(cap); newConstraintLevel.fill(-1);

  if (_count > 0) {
    newClk.set(_clkBuf.subarray(0, _count));
    newArrive.set(_arriveBuf.subarray(0, _count));
    newCmdId.set(_cmdIdBuf.subarray(0, _count));
    newTypeId.set(_typeIdBuf.subarray(0, _count));
    newSourceId.set(_sourceIdBuf.subarray(0, _count));
    newEventId.set(_eventIdBuf.subarray(0, _count));
    newRequestId.set(_requestIdBuf.subarray(0, _count));
    newFinalCmdId.set(_finalCmdIdBuf.subarray(0, _count));
    newSelectedView.set(_selectedViewBuf.subarray(0, _count));
    newViewCommitted.set(_viewCommittedBuf.subarray(0, _count));
    newReadyAt.set(_readyAtBuf.subarray(0, _count));
    newCauseEventId.set(_causeEventIdBuf.subarray(0, _count));
    newConstraintId.set(_constraintIdBuf.subarray(0, _count));
    newConstraintLevel.set(_constraintLevelBuf.subarray(0, _count));
    for (let k = 0; k < _levelCount; k++) {
      const newAddr = new Int32Array(cap);
      newAddr.set(_addrBufs[k]!.subarray(0, _count));
      _addrBufs[k] = newAddr;
    }
  } else {
    _addrBufs = Array.from({ length: _levelCount }, () => new Int32Array(cap));
  }

  _clkBuf = newClk;
  _arriveBuf = newArrive;
  _cmdIdBuf = newCmdId;
  _typeIdBuf = newTypeId;
  _sourceIdBuf = newSourceId;
  _eventIdBuf = newEventId;
  _requestIdBuf = newRequestId;
  _finalCmdIdBuf = newFinalCmdId;
  _selectedViewBuf = newSelectedView;
  _viewCommittedBuf = newViewCommitted;
  _readyAtBuf = newReadyAt;
  _causeEventIdBuf = newCauseEventId;
  _constraintIdBuf = newConstraintId;
  _constraintLevelBuf = newConstraintLevel;
  _capacity = cap;
}

function _resetBuffers(levelCount: number) {
  _count = 0;
  _capacity = 0;
  _levelCount = levelCount;
  _clkBuf = new BigInt64Array(0);
  _arriveBuf = new BigInt64Array(0);
  _cmdIdBuf = new Uint8Array(0);
  _typeIdBuf = new Int8Array(0);
  _sourceIdBuf = new Int16Array(0);
  _eventIdBuf = new BigInt64Array(0);
  _requestIdBuf = new BigInt64Array(0);
  _finalCmdIdBuf = new Int16Array(0);
  _selectedViewBuf = new Int8Array(0);
  _viewCommittedBuf = new Uint8Array(0);
  _readyAtBuf = new BigInt64Array(0);
  _causeEventIdBuf = new BigInt64Array(0);
  _constraintIdBuf = new Int32Array(0);
  _constraintLevelBuf = new Int16Array(0);
  _addrBufs = Array.from({ length: levelCount }, () => new Int32Array(0));
  _cachedSpec = null;
}

function _appendEvents(events: StreamEvent[]) {
  const M = events.length;
  if (M === 0) return;
  _growBuffers(_count + M);
  for (let i = 0; i < M; i++) {
    const e = events[i]!;
    const j = _count + i;
    _clkBuf[j] = BigInt(e.clk);
    _arriveBuf[j] = BigInt(e.arrive);
    _cmdIdBuf[j] = e.cmdId;
    _typeIdBuf[j] = e.typeId;
    _sourceIdBuf[j] = e.sourceId;
    _eventIdBuf[j] = BigInt(e.eventId ?? j);
    _requestIdBuf[j] = BigInt(e.requestId ?? -1);
    _finalCmdIdBuf[j] = e.finalCmdId ?? -1;
    _selectedViewBuf[j] = e.selectedView ?? -1;
    _viewCommittedBuf[j] = e.viewCommitted ? 1 : 0;
    _readyAtBuf[j] = BigInt(e.readyAt ?? -1);
    _causeEventIdBuf[j] = BigInt(e.causeEventId ?? -1);
    _constraintIdBuf[j] = e.constraintId ?? -1;
    _constraintLevelBuf[j] = e.constraintLevel ?? -1;
    for (let k = 0; k < _levelCount; k++) {
      _addrBufs[k]![j] = e.addr[k] ?? 0;
    }
  }
  _count += M;
}

/**
 * Build a ParsedTrace using subarray views into the backing buffers.
 * O(1) — no copies, no allocations proportional to N.
 */
function _buildTrace(header: StreamHeader, spec: StreamSpec, copyArrays = false): ParsedTrace {
  if (!_cachedSpec) {
    _cachedSpec = {
      levelNames: spec.levelNames,
      levelSizes: new Uint32Array(spec.levelSizes),
      commandNames: spec.commandNames,
      commandMeta: spec.commandMeta,
      commandCycles: new Uint8Array(spec.commandCycles ?? Array(spec.commandNames.length).fill(1)),
      timingNames: spec.timingNames,
      timingValues: new Int32Array(spec.timingValues),
      timingConstraints: spec.timingConstraints ?? [],
    };
  }

  const N = _count;
  const L = header.levelCount;
  const clk = _clkBuf.subarray(0, N) as BigInt64Array;
  const arrive = _arriveBuf.subarray(0, N) as BigInt64Array;
  const cmdId = _cmdIdBuf.subarray(0, N);
  const typeId = _typeIdBuf.subarray(0, N);
  const sourceId = _sourceIdBuf.subarray(0, N);
  const addr = Array.from(
    { length: L },
    (_, k) => (_addrBufs[k] ?? new Int32Array(0)).subarray(0, N) as Int32Array,
  );
  const arrays: TraceArrays = {
    clk: copyArrays ? new BigInt64Array(clk) : clk,
    arrive: copyArrays ? new BigInt64Array(arrive) : arrive,
    cmdId: copyArrays ? new Uint8Array(cmdId) : cmdId,
    typeId: copyArrays ? new Int8Array(typeId) : typeId,
    sourceId: copyArrays ? new Int16Array(sourceId) : sourceId,
    addr: copyArrays ? addr.map(a => new Int32Array(a)) : addr,
    eventId: copyArrays ? new BigInt64Array(_eventIdBuf.subarray(0, N)) : _eventIdBuf.subarray(0, N),
    requestId: copyArrays ? new BigInt64Array(_requestIdBuf.subarray(0, N)) : _requestIdBuf.subarray(0, N),
    finalCmdId: copyArrays ? new Int16Array(_finalCmdIdBuf.subarray(0, N)) : _finalCmdIdBuf.subarray(0, N),
    selectedView: copyArrays ? new Int8Array(_selectedViewBuf.subarray(0, N)) : _selectedViewBuf.subarray(0, N),
    viewCommitted: copyArrays ? new Uint8Array(_viewCommittedBuf.subarray(0, N)) : _viewCommittedBuf.subarray(0, N),
    readyAt: copyArrays ? new BigInt64Array(_readyAtBuf.subarray(0, N)) : _readyAtBuf.subarray(0, N),
    causeEventId: copyArrays ? new BigInt64Array(_causeEventIdBuf.subarray(0, N)) : _causeEventIdBuf.subarray(0, N),
    constraintId: copyArrays ? new Int32Array(_constraintIdBuf.subarray(0, N)) : _constraintIdBuf.subarray(0, N),
    constraintLevel: copyArrays ? new Int16Array(_constraintLevelBuf.subarray(0, N)) : _constraintLevelBuf.subarray(0, N),
    tieOffsets: new BigUint64Array(N + 1),
    tieSourceEventId: new BigInt64Array(0),
    tieConstraintId: new Int32Array(0),
    tieConstraintLevel: new Int16Array(0),
  };

  const traceHeader: TraceHeader = { ...header, numEntries: N, dataOffset: 0 };
  return { buffer: new ArrayBuffer(0), header: traceHeader, spec: _cachedSpec, arrays };
}

// ── WebSocket state ───────────────────────────────────────────────────────────

let _ws: WebSocket | null = null;
let _header: StreamHeader | null = null;
let _spec: StreamSpec | null = null;
let _closed = false;
let _refreshTimer: ReturnType<typeof setTimeout> | null = null;
let _hasLoadedThisSession = false;
const REFRESH_DEBOUNCE_MS = 100;

export function useStreamSession() {
  const status = useState<StreamStatus>('stream-status', () => 'idle');
  const eventCount = useState<number>('stream-event-count', () => 0);
  const connected = useState<boolean>('stream-connected', () => false);
  const isLive = computed(() => status.value === 'streaming');

  function connect() {
    if (!import.meta.client) return;
    if (_ws && _ws.readyState <= WebSocket.OPEN) return;
    _closed = false;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/api/live-trace`;

    if (status.value !== 'done') status.value = 'connecting';
    _ws = new WebSocket(url);

    _ws.onopen = () => {
      connected.value = true;
      if (status.value === 'connecting') status.value = 'idle';
    };

    _ws.onclose = () => {
      connected.value = false;
      _ws = null;
      if (!_closed) {
        setTimeout(() => { if (!_ws && !_closed) connect(); }, 3000);
      }
    };

    _ws.onmessage = (event) => {
      let data: any;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      switch (data.type) {
        case 'init':
          _closed = false;
          _header = data.header;
          _spec = data.spec;
          _resetBuffers(data.header.levelCount ?? 0);
          _hasLoadedThisSession = false;
          eventCount.value = 0;
          status.value = 'streaming';
          _refreshTrace(true);
          break;

        case 'events':
          if (status.value !== 'streaming' || !Array.isArray(data.events)) break;
          _appendEvents(data.events);
          eventCount.value = _count;
          _refreshTrace(false);
          break;

        case 'done':
          if (!_header || !_spec) break;
          status.value = 'finalizing';
          _refreshTrace(true, true);
          _resetBuffers(0);
          status.value = 'done';
          _closed = false;
          closeSocket(false);
          break;
      }
    };
  }

  function closeSocket(sendInterrupt: boolean) {
    if (!_ws) return;
    const ws = _ws;
    _ws = null;
    if (sendInterrupt && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'interrupt' }));
    }
    ws.close();
    connected.value = false;
  }

  function _refreshTrace(force: boolean, copyArrays = false) {
    if (!_header || !_spec) return;
    const run = () => {
      _refreshTimer = null;
      const sessionStore = useSessionStore();
      sessionStore.loadTrace(
        _buildTrace(_header!, _spec!, copyArrays),
        { streamingRefresh: _hasLoadedThisSession },
      );
      _hasLoadedThisSession = true;
    };
    if (force) {
      if (_refreshTimer) {
        clearTimeout(_refreshTimer);
        _refreshTimer = null;
      }
      run();
      return;
    }
    if (_refreshTimer) return;
    _refreshTimer = setTimeout(run, REFRESH_DEBOUNCE_MS);
  }

  function disconnect() {
    _closed = true;
    if (_refreshTimer) {
      clearTimeout(_refreshTimer);
      _refreshTimer = null;
    }
    closeSocket(status.value === 'streaming' || status.value === 'connecting');
    connected.value = false;
    status.value = 'idle';
    eventCount.value = 0;
    _resetBuffers(0);
    _header = null;
    _spec = null;
    _hasLoadedThisSession = false;
  }

  return { status, eventCount, connected, isLive, connect, disconnect };
}
