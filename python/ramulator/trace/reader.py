"""Small, dependency-free RAM2BIN reader for tests and development tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Iterable, Iterator, Sequence


@dataclass(frozen=True)
class TraceHeader:
    version: tuple[int, int]
    flags: int
    level_count: int
    command_count: int
    timing_count: int
    channel_id: int
    num_entries: int
    data_offset: int
    dram_type: str


@dataclass(frozen=True)
class TimingConstraint:
    label: str
    level: int
    preceding: int
    following: int
    value: int
    window: int
    sibling: bool
    history_group: int


@dataclass(frozen=True)
class TraceEvent:
    index: int
    clk: int
    arrive: int
    command: str
    command_id: int
    type_id: int
    source_id: int
    address: tuple[int, ...]
    event_id: int
    request_id: int = -1
    final_command: str | None = None
    selected_view: int = -1
    view_committed: bool = False
    ready_at: int = -1
    cause_event_id: int = -1
    constraint_id: int = -1
    constraint_level: int = -1
    pud_layout: int = 0
    required_view: int = -1
    layout_id: int = -1
    layout_version: int = -1

    @property
    def layout(self) -> str | None:
        return "BitSerial" if self.pud_layout == 1 else None

    @property
    def view(self) -> str | None:
        return "A" if self.selected_view == 0 else "B" if self.selected_view == 1 else None


@dataclass(frozen=True)
class TraceTimingCause:
    ready_at: int
    source: TraceEvent | None
    constraint: TimingConstraint | None
    level: int


class _Cursor:
    def __init__(self, data: bytes, offset: int = 0):
        self.data = data
        self.offset = offset

    def unpack(self, fmt: str):
        values = struct.unpack_from("<" + fmt, self.data, self.offset)
        self.offset += struct.calcsize("<" + fmt)
        return values[0] if len(values) == 1 else values

    def cstring(self) -> str:
        end = self.data.index(b"\0", self.offset)
        value = self.data[self.offset:end].decode("utf-8")
        self.offset = end + 1
        return value


class Trace:
    """An in-memory RAM2BIN trace with convenience assertions.

    Version 1.0 and 1.1 files remain supported. Their diagnostic fields use
    neutral defaults, so consumers can use one API for DDR and DDRAM-P traces.
    """

    def __init__(self, data: bytes):
        if data[:7] != b"RAM2BIN":
            raise ValueError("not a RAM2BIN trace")
        self._data = data
        self.header = self._read_header(data)
        self._read_spec()
        self._events = self._read_events()
        self._event_by_id = {event.event_id: event for event in self._events}

    @classmethod
    def open(cls, path: str | Path) -> "Trace":
        return cls(Path(path).read_bytes())

    @staticmethod
    def _read_header(data: bytes) -> TraceHeader:
        major, minor = struct.unpack_from("<BB", data, 8)
        flags = struct.unpack_from("<H", data, 10)[0]
        level_count, command_count, timing_count = struct.unpack_from("<HHH", data, 12)
        channel_id = struct.unpack_from("<I", data, 24)[0]
        num_entries, data_offset = struct.unpack_from("<QQ", data, 32)
        dram_type = data[48:64].split(b"\0", 1)[0].decode("utf-8")
        return TraceHeader(
            (major, minor),
            flags,
            level_count,
            command_count,
            timing_count,
            channel_id,
            num_entries,
            data_offset,
            dram_type,
        )

    def _read_spec(self) -> None:
        cur = _Cursor(self._data, 64)
        self.level_names = tuple(cur.cstring() for _ in range(self.header.level_count))
        self.level_sizes = tuple(cur.unpack("I") for _ in range(self.header.level_count))
        self.command_names = tuple(cur.cstring() for _ in range(self.header.command_count))
        self.command_meta = tuple(cur.unpack("B") for _ in range(self.header.command_count))
        if self.header.version >= (1, 1):
            self.command_cycles = tuple(cur.unpack("B") for _ in range(self.header.command_count))
        else:
            self.command_cycles = (1,) * self.header.command_count
        self.timing_names = tuple(cur.cstring() for _ in range(self.header.timing_count))
        self.timing_values = tuple(cur.unpack("i") for _ in range(self.header.timing_count))
        constraints: list[TimingConstraint] = []
        if self.header.version >= (1, 2):
            for _ in range(cur.unpack("I")):
                label = cur.cstring()
                level, preceding, following = cur.unpack("hhh")
                value = cur.unpack("i")
                window = cur.unpack("h")
                sibling = bool(cur.unpack("B"))
                history_group = cur.unpack("h")
                constraints.append(
                    TimingConstraint(
                        label,
                        level,
                        preceding,
                        following,
                        value,
                        window,
                        sibling,
                        history_group,
                    )
                )
        self.timing_constraints = tuple(constraints)

    def _array(self, offset: int, fmt: str) -> tuple[int, ...]:
        size = struct.calcsize("<" + fmt)
        return tuple(
            struct.unpack_from("<" + fmt, self._data, offset + i * size)[0]
            for i in range(self.header.num_entries)
        )

    def _read_events(self) -> tuple[TraceEvent, ...]:
        count = self.header.num_entries
        levels = self.header.level_count
        offset = self.header.data_offset
        clk = self._array(offset, "q")
        offset += 8 * count
        arrive = self._array(offset, "q")
        offset += 8 * count
        command_ids = self._array(offset, "B")
        offset += count
        type_ids = self._array(offset, "b")
        offset += count
        source_ids = self._array(offset, "h")
        offset += 2 * count
        addresses = []
        for _ in range(levels):
            addresses.append(self._array(offset, "i"))
            offset += 4 * count

        event_ids = tuple(range(count))
        request_ids = (-1,) * count
        final_ids = (-1,) * count
        selected_views = (-1,) * count
        committed = (0,) * count
        ready_at = (-1,) * count
        cause_ids = (-1,) * count
        constraint_ids = (-1,) * count
        constraint_levels = (-1,) * count
        tie_offsets = (0,) * (count + 1)
        tie_source_ids: tuple[int, ...] = ()
        tie_constraint_ids: tuple[int, ...] = ()
        tie_levels: tuple[int, ...] = ()
        pud_layouts = (0,) * count
        required_views = (-1,) * count
        layout_ids = (-1,) * count
        layout_versions = (-1,) * count
        if self.header.version >= (1, 2):
            event_ids = self._array(offset, "q")
            offset += 8 * count
            request_ids = self._array(offset, "q")
            offset += 8 * count
            final_ids = self._array(offset, "h")
            offset += 2 * count
            selected_views = self._array(offset, "b")
            offset += count
            committed = self._array(offset, "B")
            offset += count
            ready_at = self._array(offset, "q")
            offset += 8 * count
            cause_ids = self._array(offset, "q")
            offset += 8 * count
            constraint_ids = self._array(offset, "i")
            offset += 4 * count
            constraint_levels = self._array(offset, "h")
            offset += 2 * count
            if self.header.version >= (1, 3):
                tie_offsets = tuple(
                    struct.unpack_from("<Q", self._data, offset + i * 8)[0]
                    for i in range(count + 1)
                )
                offset += (count + 1) * 8
                tie_count = tie_offsets[-1]
                tie_source_ids = self._array_count(offset, "q", tie_count)
                offset += 8 * tie_count
                tie_constraint_ids = self._array_count(offset, "i", tie_count)
                offset += 4 * tie_count
                tie_levels = self._array_count(offset, "h", tie_count)
                offset += 2 * tie_count
            if self.header.version >= (1, 4) and self.header.flags & 4:
                pud_layouts = self._array(offset, "b")
                offset += count
                required_views = self._array(offset, "b")
                offset += count
                layout_ids = self._array(offset, "q")
                offset += 8 * count
                layout_versions = self._array(offset, "q")

        self._tie_offsets = tie_offsets
        self._tie_source_ids = tie_source_ids
        self._tie_constraint_ids = tie_constraint_ids
        self._tie_levels = tie_levels

        events = []
        for i in range(count):
            final_id = final_ids[i]
            events.append(
                TraceEvent(
                    i,
                    clk[i],
                    arrive[i],
                    self.command_names[command_ids[i]],
                    command_ids[i],
                    type_ids[i],
                    source_ids[i],
                    tuple(level[i] for level in addresses),
                    event_ids[i],
                    request_ids[i],
                    self.command_names[final_id]
                    if 0 <= final_id < len(self.command_names)
                    else None,
                    selected_views[i],
                    bool(committed[i]),
                    ready_at[i],
                    cause_ids[i],
                    constraint_ids[i],
                    constraint_levels[i],
                    pud_layouts[i],
                    required_views[i],
                    layout_ids[i],
                    layout_versions[i],
                )
            )
        return tuple(events)

    def _array_count(self, offset: int, fmt: str, count: int) -> tuple[int, ...]:
        size = struct.calcsize("<" + fmt)
        return tuple(
            struct.unpack_from("<" + fmt, self._data, offset + i * size)[0]
            for i in range(count)
        )

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return self._events

    def commands(
        self, *, bank: int | None = None, view: str | int | None = None
    ) -> Iterator[TraceEvent]:
        bank_level = next((i for i, name in enumerate(self.level_names) if name == "Bank"), None)
        view_id = {"A": 0, "B": 1}.get(view, view)
        for event in self._events:
            if bank is not None and (bank_level is None or event.address[bank_level] != bank):
                continue
            if view is not None and event.selected_view != view_id:
                continue
            yield event

    def request_chain(self, request_id: int) -> tuple[TraceEvent, ...]:
        return tuple(event for event in self._events if event.request_id == request_id)

    def timing_cause(
        self, event: TraceEvent | int
    ) -> tuple[TraceEvent | None, TimingConstraint | None]:
        target = self._events[event] if isinstance(event, int) else event
        source = self._event_by_id.get(target.cause_event_id)
        constraint = (
            self.timing_constraints[target.constraint_id]
            if 0 <= target.constraint_id < len(self.timing_constraints) else None
        )
        return source, constraint

    def timing_causes(self, event: TraceEvent | int) -> tuple[TraceTimingCause, ...]:
        target = self._events[event] if isinstance(event, int) else event
        begin = self._tie_offsets[target.index]
        end = self._tie_offsets[target.index + 1]
        if begin == end:
            source, constraint = self.timing_cause(target)
            if target.constraint_id < 0:
                return ()
            return (TraceTimingCause(target.ready_at, source, constraint, target.constraint_level),)
        return tuple(
            TraceTimingCause(
                target.ready_at,
                self._event_by_id.get(self._tie_source_ids[i]),
                self.timing_constraints[self._tie_constraint_ids[i]]
                if 0 <= self._tie_constraint_ids[i] < len(self.timing_constraints)
                else None,
                self._tie_levels[i],
            )
            for i in range(begin, end)
        )

    def assert_sequence(
        self, expected: Sequence[str], events: Iterable[TraceEvent] | None = None
    ) -> None:
        actual = [event.command for event in (self._events if events is None else events)]
        expected_list = list(expected)
        if actual != expected_list:
            raise AssertionError(f"command sequence differs:\nexpected {expected_list}\nactual   {actual}")

    def assert_timing_edge(
        self, source: TraceEvent, target: TraceEvent, label: str | None = None
    ) -> None:
        cause, constraint = self.timing_cause(target)
        if cause != source:
            raise AssertionError(f"event {target.event_id} was caused by {cause}, not {source}")
        if label is not None and (constraint is None or constraint.label != label):
            actual = constraint.label if constraint else None
            raise AssertionError(f"expected timing label {label!r}, got {actual!r}")
