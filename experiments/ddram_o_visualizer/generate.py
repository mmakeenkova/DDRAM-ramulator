"""Generate a compact DDRAM-O trace with visible cross-view dependencies.

This development driver uses the controller scheduling harness because the
production CPU-trace frontends do not yet encode PuD request metadata.  The
commands, timing checks, scheduler, and BinTraceRecorder are the production
implementations.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import ramulator
from ramulator.trace import Trace
from tests.controller_scheduling.harness import ControllerUnderTest


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    ROOT / "experiments" / "ddram_p_visualizer" / "output"
    / "ddram_o.cross-view"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a DDRAM-O RAM2BIN trace for the A/B lane visualizer."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output prefix; '.ch0.ram2bin' is appended (default: %(default)s).",
    )
    parser.add_argument(
        "--cross-view-delay",
        type=int,
        default=17,
        help="nXACTO used to make cross-view arrows easy to distinguish (default: 17).",
    )
    parser.add_argument(
        "--mra-duration",
        type=int,
        default=40,
        help="nMRA service interval in cycles (default: 40).",
    )
    return parser.parse_args()


def address(dut: ControllerUnderTest, *, row: int, column: int = 0) -> list[int]:
    return dut.addr_vec(
        Channel=0, Rank=0, BankGroup=0, Bank=0, Row=row, Column=column
    )


def send_mra(
    dut: ControllerUnderTest,
    *,
    row: int,
    layout_id: int,
    layout_version: int,
) -> int:
    return dut.send_pud(
        address(dut, row=row),
        required_view=1,
        layout="BitSerial",
        layout_id=layout_id,
        layout_version=layout_version,
    )


def generate(output: Path, n_xacto: int, n_mra: int) -> Path:
    if n_xacto <= 0 or n_mra <= 0:
        raise ValueError("--cross-view-delay and --mra-duration must be positive")

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    trace_path = Path(f"{output}.ch0.ram2bin")
    if trace_path.exists():
        trace_path.unlink()

    dram = ramulator.dram.DDRAM_O(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
        nXACTO=n_xacto,
        nMRA=n_mra,
    )
    dut = ControllerUnderTest.make_generic_ddr(
        dram,
        scheduler=ramulator.scheduler.FRFCFSViewAware(),
        view_selection="Auto",
        controller_plugins=[
            ramulator.controller_plugin.BinTraceRecorder(
                path=str(output),
                dram_type="DDRAM_O",
                record_equal_constraints=True,
            )
        ],
    )

    # Phase 1: issue ACT_A first, then introduce MRA_B so it is held by nXACTO.
    # A second read remains an A-side row hit while the B operation is active.
    dut.send_request("Read", address(dut, row=10, column=0))
    for _ in range(256):
        issued = dut.tick()
        if any(item.command == "ACT_A" for item in issued):
            break
    else:
        raise RuntimeError("ACT_A was not issued while constructing phase 1")
    send_mra(dut, row=20, layout_id=7, layout_version=1)
    dut.send_request("Read", address(dut, row=10, column=8))
    dut.run_until_idle(4096)
    dut.take_completions()

    # Close A and let nRP elapse before phase 2, so an otherwise-ready ACT_A is
    # constrained specifically by the preceding MRA_B's cross-view nXACTO.
    dut.priority_send("PRE_A", address(dut, row=10))
    dut.run_until_idle(4096)
    for _ in range(dut.timings["nRP"]):
        dut.tick()

    # Phase 2: MRA_B wins over the activation prerequisite, exposing the
    # reverse B-to-A nXACTO edge without a stricter PRE_A-to-ACT_A dependency.
    send_mra(dut, row=30, layout_id=8, layout_version=2)
    dut.send_request("Read", address(dut, row=40, column=0))
    dut.send_request("Read", address(dut, row=40, column=8))
    dut.run_until_idle(4096)
    dut.stats()  # Finalizes plugins and flushes RAM2BIN.

    trace = Trace.open(trace_path)
    print(f"Wrote {trace_path}")
    print(f"RAM2BIN {trace.header.version[0]}.{trace.header.version[1]}: "
          f"{len(trace.events)} commands")
    for event in trace.events:
        layout = f", {event.layout} L{event.layout_id}v{event.layout_version}" if event.layout else ""
        print(f"  {event.clk:4d}  {event.command:6s}  req={event.request_id:2d}"
              f"  view={event.view or '-'}{layout}")
    return trace_path


def main() -> None:
    args = parse_args()
    generate(args.output, args.cross_view_delay, args.mra_duration)


if __name__ == "__main__":
    main()
