import struct

import pytest

from ramulator.trace import Trace


def _pack_array(fmt, values):
    return b"".join(struct.pack("<" + fmt, value) for value in values)


def _trace_bytes(version):
    levels = ("Channel", "Bank", "Row")
    commands = ("ACT_A", "RD_A")
    timings = ("nRCD",)
    spec = b"".join(value.encode() + b"\0" for value in levels)
    spec += _pack_array("I", (1, 2, 1024))
    spec += b"".join(value.encode() + b"\0" for value in commands)
    spec += _pack_array("B", (0b10001, 0b100100))
    if version >= (1, 1):
        spec += _pack_array("B", (1, 1))
    spec += b"nRCD\0" + _pack_array("i", (16,))
    if version >= (1, 2):
        spec += _pack_array("I", (2 if version >= (1, 3) else 1,))
        spec += b"nRCD\0" + struct.pack("<hhhihBh", 2, 0, 1, 16, 1, 0, -1)
        if version >= (1, 3):
            spec += b"command bus\0" + struct.pack("<hhhihBh", 0, 0, 1, 16, 1, 0, -1)

    data_offset = (64 + len(spec) + 7) & ~7
    header = bytearray(64)
    header[:8] = b"RAM2BIN\0"
    flags = int(version >= (1, 2)) | (4 if version >= (1, 4) else 0)
    struct.pack_into("<BBH", header, 8, *version, flags)
    struct.pack_into("<HHHHHH", header, 12, 3, 2, 1, 64, 8, 8)
    struct.pack_into("<IiQQ", header, 24, 0, 16, 2, data_offset)
    header[48:55] = b"DDRAM_P"

    data = _pack_array("q", (10, 26))
    data += _pack_array("q", (10, 10))
    data += _pack_array("B", (0, 1))
    data += _pack_array("b", (0, 0))
    data += _pack_array("h", (7, 7))
    data += _pack_array("i", (0, 0))
    data += _pack_array("i", (1, 1))
    data += _pack_array("i", (42, 42))
    if version >= (1, 2):
        data += _pack_array("q", (100, 101))
        data += _pack_array("q", (5, 5))
        data += _pack_array("h", (1, 1))
        data += _pack_array("b", (0, 0))
        data += _pack_array("B", (1, 1))
        data += _pack_array("q", (-1, 26))
        data += _pack_array("q", (-1, 100))
        data += _pack_array("i", (-1, 0))
        data += _pack_array("h", (-1, 2))
        if version >= (1, 3):
            data += _pack_array("Q", (0, 0, 2))
            data += _pack_array("q", (100, 100))
            data += _pack_array("i", (0, 1))
            data += _pack_array("h", (2, 0))
        if version >= (1, 4):
            data += _pack_array("b", (0, 1))
            data += _pack_array("b", (-1, 1))
            data += _pack_array("q", (-1, 7))
            data += _pack_array("q", (-1, 3))
    return bytes(header) + spec + bytes(data_offset - 64 - len(spec)) + data


@pytest.mark.parametrize("version", [(1, 0), (1, 1), (1, 2), (1, 3), (1, 4)])
def test_reader_preserves_old_trace_compatibility(version):
    trace = Trace(_trace_bytes(version))

    trace.assert_sequence(["ACT_A", "RD_A"])
    assert [event.command for event in trace.commands(bank=1)] == ["ACT_A", "RD_A"]
    assert trace.events[0].address == (0, 1, 42)

    if version < (1, 2):
        assert trace.events[1].request_id == -1
        assert trace.events[1].view is None
        assert trace.timing_cause(1) == (None, None)
    else:
        assert [event.command for event in trace.commands(view="A")] == ["ACT_A", "RD_A"]
        assert [event.command for event in trace.request_chain(5)] == ["ACT_A", "RD_A"]
        source, constraint = trace.timing_cause(1)
        assert source == trace.events[0]
        assert constraint is not None and constraint.label == "nRCD"
        trace.assert_timing_edge(trace.events[0], trace.events[1], "nRCD")
        causes = trace.timing_causes(1)
        assert [cause.constraint.label for cause in causes] == (
            ["nRCD", "command bus"] if version >= (1, 3) else ["nRCD"]
        )
        if version >= (1, 4):
            assert trace.events[1].layout == "BitSerial"
            assert (trace.events[1].required_view, trace.events[1].layout_id,
                    trace.events[1].layout_version) == (1, 7, 3)
