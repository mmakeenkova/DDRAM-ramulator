"""Run a small DDRAM-P experiment and record a RAM2BIN command trace."""

from __future__ import annotations

import argparse
from itertools import islice
import os
from pathlib import Path

import ramulator


EXPERIMENT_DIR = Path(__file__).resolve().parent
DEFAULT_TRACE = EXPERIMENT_DIR / "traces" / "two_rows.trace"
DEFAULT_MORDOR_ROOT = Path(
    os.environ.get("MORDOR_CPUTRACES", "/home/maria/MORDOR/cputraces/cputraces")
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run DDRAM-P with binary command-trace recording enabled."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--trace",
        type=Path,
        help="SimpleO3 trace path; defaults to the experiment's two-row trace.",
    )
    source.add_argument(
        "--mordor-trace",
        metavar="NAME",
        help="Trace name below --mordor-root, for example 538.imagick.",
    )
    parser.add_argument(
        "--mordor-root",
        type=Path,
        default=DEFAULT_MORDOR_ROOT,
        help="Directory containing the extracted MORDOR CPU traces.",
    )
    parser.add_argument(
        "--trace-lines",
        type=int,
        default=None,
        help="Use only the first N trace records by making a local input slice.",
    )
    parser.add_argument(
        "--instructions",
        type=int,
        default=20_000,
        help="Number of instructions to retire before stopping (default: 20000).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Trace prefix; '.ch0.ram2bin' is appended by the recorder. "
            "By default the row-policy and refresh settings are encoded in the name."
        ),
    )
    parser.add_argument(
        "--view-selection",
        choices=("TwoView", "QueueAware", "AlwaysA"),
        default="TwoView",
        help="DDRAM-P view-selection policy (default: TwoView).",
    )
    parser.add_argument(
        "--row-policy",
        choices=("Open", "DDRAMViewAutoPrecharge"),
        default="Open",
        help="Row-closure policy (default: Open).",
    )
    parser.add_argument(
        "--auto-precharge-view",
        choices=("A", "B"),
        default="B",
        help="Transient view used by DDRAMViewAutoPrecharge (default: B).",
    )
    parser.add_argument(
        "--no-preserve-queued-hits",
        action="store_true",
        help="Auto-precharge even when another request to the same row is queued.",
    )
    parser.add_argument(
        "--min-hits-to-preserve",
        type=int,
        default=1,
        help="Queued same-row requests needed to suppress auto-precharge (default: 1).",
    )
    parser.add_argument(
        "--managed-refresh",
        choices=("Disabled", "Oracle", "Nack"),
        default="Disabled",
        help="Autonomous DDRAM-P refresh interface (default: Disabled).",
    )
    parser.add_argument(
        "--refresh-interval",
        type=int,
        default=-1,
        help="Cycles between autonomous refresh credits; -1 uses nREFI.",
    )
    parser.add_argument(
        "--refresh-duration",
        type=int,
        default=-1,
        help="Cycles occupied by a row refresh; -1 uses nRFCsb.",
    )
    return parser.parse_args()


def resolve_output_prefix(args: argparse.Namespace) -> Path:
    """Preserve explicit names and derive descriptive names for default output."""
    if args.output is not None:
        return args.output.expanduser().resolve()
    name = "ddram_p"
    if args.row_policy == "DDRAMViewAutoPrecharge":
        name += f".auto-precharge-{args.auto_precharge_view.lower()}"
        if args.no_preserve_queued_hits:
            name += ".always"
        elif args.min_hits_to_preserve != 1:
            name += f".preserve-{args.min_hits_to_preserve}"
    if args.managed_refresh != "Disabled":
        interval = "nREFI" if args.refresh_interval < 0 else str(args.refresh_interval)
        duration = "nRFCsb" if args.refresh_duration < 0 else str(args.refresh_duration)
        name += (
            f".refresh-{args.managed_refresh.lower()}"
            f".interval-{interval}.duration-{duration}"
        )
    return (EXPERIMENT_DIR / "output" / name).resolve()


def resolve_input(args: argparse.Namespace) -> Path:
    if args.mordor_trace:
        path = args.mordor_root / args.mordor_trace
    else:
        path = args.trace or DEFAULT_TRACE
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Input trace does not exist: {path}")
    return path


def prepare_input(path: Path, line_limit: int | None) -> Path:
    if line_limit is None:
        return path
    if line_limit <= 0:
        raise ValueError("--trace-lines must be greater than zero")

    input_dir = EXPERIMENT_DIR / "output" / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    sliced = input_dir / f"{path.name}.first-{line_limit}"
    with path.open() as source, sliced.open("w") as destination:
        destination.writelines(islice(source, line_limit))
    if sliced.stat().st_size == 0:
        raise ValueError(f"Input trace is empty: {path}")
    return sliced


def build_simulation(
    input_trace: Path,
    output_prefix: Path,
    instructions: int,
    view_selection: str,
    row_policy_name: str,
    auto_precharge_view: str,
    preserve_queued_hits: bool,
    min_hits_to_preserve: int,
    managed_refresh: str,
    refresh_interval: int,
    refresh_duration: int,
):
    if instructions <= 0:
        raise ValueError("--instructions must be greater than zero")

    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    frontend = ramulator.frontend.SimpleO3(
        clock_ratio=8,
        traces=[str(input_trace)],
        num_expected_insts=instructions,
        translation=ramulator.translation.NoTranslation(max_addr=2**31),
    )

    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_4800AN",
        rank=1,
    )

    if row_policy_name == "DDRAMViewAutoPrecharge":
        row_policy = ramulator.row_policy.DDRAMViewAutoPrecharge(
            auto_precharge_view=auto_precharge_view,
            preserve_queued_hits=preserve_queued_hits,
            min_hits_to_preserve=min_hits_to_preserve,
        )
    else:
        row_policy = ramulator.row_policy.Open()

    controller = ramulator.controller.GenericDDR(
        dram=dram,
        scheduler=ramulator.scheduler.FRFCFSViewAware(),
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
        row_policy=row_policy,
        addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
        view_selection=view_selection,
        dram_managed_refresh=managed_refresh,
        dram_refresh_interval=refresh_interval,
        dram_refresh_duration=refresh_duration,
        controller_plugins=[
            ramulator.controller_plugin.BinTraceRecorder(
                path=str(output_prefix),
                dram_type="DDRAM_P",
                record_equal_constraints=True,
            )
        ],
    )

    memory_system = ramulator.memory_system.GenericDRAM(
        clock_ratio=3,
        controllers=[controller],
        channel_mapper=ramulator.channel_mapper.CacheLineInterleave(),
    )
    return ramulator.Simulation(frontend, memory_system)


def main() -> None:
    args = parse_args()
    source = resolve_input(args)
    input_trace = prepare_input(source, args.trace_lines)
    output_prefix = resolve_output_prefix(args)

    print(f"Input trace:  {input_trace}")
    print(f"Output trace: {output_prefix}.ch0.ram2bin")

    simulation = build_simulation(
        input_trace,
        output_prefix,
        args.instructions,
        args.view_selection,
        args.row_policy,
        args.auto_precharge_view,
        not args.no_preserve_queued_hits,
        args.min_hits_to_preserve,
        args.managed_refresh,
        args.refresh_interval,
        args.refresh_duration,
    )
    simulation.run()
    simulation.finalize()

    print("Trace complete.")
    print("Open it with: PYTHONPATH=python python -m ramulator visualize --dev")


if __name__ == "__main__":
    main()
