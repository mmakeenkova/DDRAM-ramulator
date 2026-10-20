"""Generate a compact TwoView/QueueAware view-replacement comparison."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import ramulator

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import tests.controller_scheduling.harness as cs


EXPERIMENT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic TwoView and QueueAware DDRAM-P traces."
    )
    parser.add_argument(
        "--output-dir", type=Path, default=EXPERIMENT_DIR / "output"
    )
    return parser.parse_args()


def generate(policy: str, output_dir: Path) -> Path:
    label = "two-view" if policy == "TwoView" else "queue-aware"
    prefix = output_dir.expanduser().resolve() / f"ddram_p.view-{label}"
    prefix.parent.mkdir(parents=True, exist_ok=True)

    # One bank keeps the visualizer compact.  Row 10 is opened in A and row 20
    # in B.  The two writes remain in the write queue while the read miss for
    # row 30 is selected.  TwoView's deterministic A-first replacement evicts
    # row 10; QueueAware sees the queued writes and evicts row 20 from B.
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
        bankgroup=1,
        bank=1,
        row=64,
    )
    dut = cs.ControllerUnderTest.make_generic_ddr(
        dram,
        scheduler=ramulator.scheduler.FRFCFSViewAware(),
        view_selection=policy,
        controller_plugins=[
            ramulator.controller_plugin.BinTraceRecorder(
                path=str(prefix),
                dram_type="DDRAM_P",
                record_equal_constraints=True,
            )
        ],
    )

    def address(row: int, column: int = 0) -> list[int]:
        return dut.addr_vec(
            Rank=0, BankGroup=0, Bank=0, Row=row, Column=column
        )

    dut.send_request("Read", address(10))
    dut.run_until_idle()
    dut.send_request("Read", address(20))
    dut.run_until_idle()
    start = len(dut.history)

    dut.send_request("Write", address(10, 8))
    dut.send_request("Write", address(10, 16))
    dut.send_request("Read", address(30))
    history = dut.run_until_idle(max_ticks=2048)
    dut.stats()  # Finalize the binary recorder.

    row_level = dut.level_names.index("Row")
    miss_commands = [
        event.command for event in history if event.addr_vec[row_level] == 30
    ]
    expected_view = "A" if policy == "TwoView" else "B"
    assert miss_commands == [
        f"PRE_{expected_view}", f"ACT_{expected_view}", f"RD_{expected_view}"
    ]

    later_row10 = [
        event.command
        for event in dut.history[start:]
        if event.addr_vec[row_level] == 10
    ]
    if policy == "TwoView":
        # A is reserved by the row-30 request while its prerequisites execute,
        # so the displaced row 10 is reopened in B when the writes progress.
        assert later_row10 == ["PRE_B", "ACT_B", "WR_B", "WR_B"]
    else:
        assert later_row10 == ["WR_A", "WR_A"]

    print(f"{policy:10s}: {prefix}.ch0.ram2bin")
    print("             " + " → ".join(event.command for event in history))
    return prefix


def main() -> None:
    args = parse_args()
    for policy in ("TwoView", "QueueAware"):
        generate(policy, args.output_dir)


if __name__ == "__main__":
    main()
