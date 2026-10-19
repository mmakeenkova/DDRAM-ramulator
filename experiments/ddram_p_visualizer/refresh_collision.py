"""Generate paired Oracle/NACK traces with a guaranteed refresh-lock collision."""

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
        description="Generate deterministic DDRAM-P Oracle/NACK collision traces."
    )
    parser.add_argument("--refresh-interval", type=int, default=16)
    parser.add_argument("--refresh-duration", type=int, default=12)
    parser.add_argument("--refresh-ari", type=int, default=2)
    parser.add_argument("--nack-latency", type=int, default=2)
    parser.add_argument(
        "--output-dir", type=Path, default=EXPERIMENT_DIR / "output"
    )
    return parser.parse_args()


def output_prefix(output_dir: Path, mode: str, interval: int, duration: int) -> Path:
    name = (
        f"ddram_p.collision.refresh-{mode.lower()}"
        f".interval-{interval}.duration-{duration}"
    )
    return output_dir.expanduser().resolve() / name


def generate(mode: str, args: argparse.Namespace) -> tuple[Path, list]:
    prefix = output_prefix(
        args.output_dir, mode, args.refresh_interval, args.refresh_duration
    )
    prefix.parent.mkdir(parents=True, exist_ok=True)

    # One bank keeps the diagram compact. At the first credit, row 0 is
    # internally refreshed. The read is injected one cycle later and therefore
    # requires an ACT to that locked row-region.
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
        dram_managed_refresh=mode,
        dram_refresh_interval=args.refresh_interval,
        dram_refresh_duration=args.refresh_duration,
        dram_refresh_rows_per_region=1,
        dram_refresh_granularity=1,
        dram_refresh_ari=args.refresh_ari,
        dram_refresh_nack_latency=args.nack_latency,
        controller_plugins=[
            ramulator.controller_plugin.BinTraceRecorder(
                path=str(prefix),
                dram_type="DDRAM_P",
                record_equal_constraints=True,
            )
        ],
    )

    for _ in range(args.refresh_interval):
        dut.tick()
    assert any(event.command == "IREF_A" for event in dut.history)

    target = dut.addr_vec(
        Rank=0, BankGroup=0, Bank=0, Row=0, Column=0
    )
    dut.send_request("Read", target)
    dut.run_until_idle(max_ticks=2048)
    stats = dut.stats()  # finalizes the recorder

    nacks = [event for event in dut.history if event.command == "ACT_NACK"]
    if mode == "Oracle":
        assert not nacks
    else:
        assert nacks, "collision demo failed to produce an ACT_NACK"

    print(
        f"{mode:6s}: {prefix}.ch0.ram2bin "
        f"({len(nacks)} ACT_NACK, {stats['num_internal_refreshes']} IREF)"
    )
    return prefix, dut.history


def main() -> None:
    args = parse_args()
    if args.refresh_interval <= 0 or args.refresh_duration <= 0:
        raise ValueError("refresh interval and duration must be positive")
    if args.refresh_ari < 0 or args.nack_latency < 0:
        raise ValueError("ARI and NACK latency must be non-negative")
    for mode in ("Oracle", "Nack"):
        generate(mode, args)


if __name__ == "__main__":
    main()
