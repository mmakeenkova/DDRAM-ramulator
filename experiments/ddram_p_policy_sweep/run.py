"""Compare DDRAM-P view-selection and row-closure policies on MORDOR traces."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from itertools import islice
from pathlib import Path
from time import monotonic


EXPERIMENT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = EXPERIMENT_DIR / "configs"
DEFAULT_TRACE_ROOT = Path(
    os.environ.get("MORDOR_CPUTRACES", "/home/maria/MORDOR/cputraces/cputraces")
)
DEFAULT_WORKLOADS = ("429.mcf", "538.imagick", "ycsb_aserver", "stream_10.trace")
CONFIG_KEYS = {
    "name", "description", "trace_root", "workloads", "instructions",
    "trace_lines", "refresh_mode", "refresh_interval", "refresh_duration",
    "refresh_preserve_open_rows", "workers",
}


@dataclass(frozen=True)
class Policy:
    name: str
    view_selection: str
    row_policy: str
    refresh_view_count: int


@dataclass
class Result:
    workload: str
    policy: str
    view_selection: str
    row_policy: str
    refresh_mode: str
    refresh_preserve_open_rows: bool
    cycles: int
    memory_cycles: int
    memory_access_cycles: int
    ipc: float
    row_hits: int
    row_misses: int
    row_conflicts: int
    reads_served: int
    writes_served: int
    internal_refreshes: int
    act_nacks: int
    average_read_latency: float
    total_throughput_MBps: float
    wall_seconds: float


def policies() -> tuple[Policy, ...]:
    """Return matched points that differ only in view/row policy."""
    return (
        Policy("one_view", "AlwaysA", "Open", 1),
        Policy("both_views", "TwoView", "Open", 2),
        Policy("auto_precharge", "TwoView", "DDRAMViewAutoPrecharge", 2),
        Policy("queue_aware", "QueueAware", "Open", 2),
    )


def resolve_config_path(value: str) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    named = CONFIG_DIR / (value if value.endswith(".json") else f"{value}.json")
    if named.is_file():
        return named.resolve()
    raise FileNotFoundError(f"Experiment configuration does not exist: {value}")


def load_config(value: str | None) -> tuple[dict, Path | None]:
    if value is None:
        return {}, None
    path = resolve_config_path(value)
    config = json.loads(path.read_text())
    if not isinstance(config, dict):
        raise ValueError(f"Experiment configuration must be a JSON object: {path}")
    unknown = set(config) - CONFIG_KEYS
    if unknown:
        raise ValueError(f"Unknown configuration fields in {path}: {sorted(unknown)}")
    return config, path


def parse_args() -> argparse.Namespace:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config")
    pre_parser.add_argument("--list-configs", action="store_true")
    pre_args, _ = pre_parser.parse_known_args()
    if pre_args.list_configs:
        for path in sorted(CONFIG_DIR.glob("*.json")):
            config = json.loads(path.read_text())
            print(f"{path.stem:<28} {config.get('description', '')}")
        raise SystemExit(0)

    selected, selected_path = load_config(pre_args.config)
    defaults = {
        "trace_root": DEFAULT_TRACE_ROOT,
        "workloads": list(DEFAULT_WORKLOADS),
        "instructions": 1_000_000,
        "trace_lines": 250_000,
        "refresh_mode": "Oracle",
        "refresh_interval": -1,
        "refresh_duration": -1,
        "refresh_preserve_open_rows": False,
        "workers": 1,
    }
    defaults.update({key: value for key, value in selected.items() if key in defaults})
    defaults["trace_root"] = Path(defaults["trace_root"])

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--list-configs", action="store_true")
    parser.add_argument("--trace-root", type=Path, default=defaults["trace_root"])
    parser.add_argument("--workloads", nargs="+", default=defaults["workloads"])
    parser.add_argument("--instructions", type=int, default=defaults["instructions"])
    parser.add_argument("--trace-lines", type=int, default=defaults["trace_lines"])
    parser.add_argument(
        "--refresh-mode", choices=("Disabled", "Oracle", "Nack"),
        default=defaults["refresh_mode"],
    )
    parser.add_argument("--refresh-interval", type=int, default=defaults["refresh_interval"])
    parser.add_argument("--refresh-duration", type=int, default=defaults["refresh_duration"])
    parser.add_argument(
        "--refresh-preserve-open-rows",
        action=argparse.BooleanOptionalAction,
        default=defaults["refresh_preserve_open_rows"],
    )
    parser.add_argument("--workers", type=int, default=defaults["workers"])
    parser.add_argument("--verbose-ramulator", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    args.config_path = selected_path
    args.config_data = selected
    args.experiment_name = selected.get("name", selected_path.stem if selected_path else None)
    args.experiment_description = selected.get("description")
    return args


def prepare_trace(source: Path, destination: Path, line_limit: int) -> int:
    if line_limit <= 0:
        raise ValueError("--trace-lines must be greater than zero")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = 0
    with source.open() as input_file, destination.open("w") as output_file:
        for line in islice(input_file, line_limit):
            output_file.write(line)
            lines += 1
    if lines == 0:
        raise ValueError(f"Input trace is empty: {source}")
    return lines


def run_one(
    workload: str,
    trace_path: str,
    policy: Policy,
    instructions: int,
    refresh_mode: str,
    refresh_interval: int,
    refresh_duration: int,
    refresh_preserve_open_rows: bool,
) -> Result:
    import ramulator

    start = monotonic()
    frontend = ramulator.frontend.SimpleO3(
        clock_ratio=8,
        traces=[trace_path],
        num_expected_insts=instructions,
        translation=ramulator.translation.NoTranslation(max_addr=2**31),
    )
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_4800AN",
        rank=1,
    )
    if policy.row_policy == "DDRAMViewAutoPrecharge":
        row_policy = ramulator.row_policy.DDRAMViewAutoPrecharge(
            auto_precharge_view="B",
            preserve_queued_hits=True,
            min_hits_to_preserve=1,
        )
    else:
        row_policy = ramulator.row_policy.Open()
    controller = ramulator.controller.GenericDDR(
        dram=dram,
        scheduler=ramulator.scheduler.FRFCFSViewAware(),
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
        row_policy=row_policy,
        addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
        view_selection=policy.view_selection,
        dram_managed_refresh=refresh_mode,
        dram_refresh_view_count=policy.refresh_view_count,
        dram_refresh_interval=refresh_interval,
        dram_refresh_duration=refresh_duration,
        dram_refresh_preserve_open_rows=refresh_preserve_open_rows,
    )
    memory_system = ramulator.memory_system.GenericDRAM(
        clock_ratio=3,
        controllers=[controller],
        channel_mapper=ramulator.channel_mapper.CacheLineInterleave(),
    )
    simulation = ramulator.Simulation(frontend, memory_system)
    simulation.run()
    simulation.finalize()
    stats = simulation.stats
    frontend_stats = stats["frontend"]
    controller_stats = stats["memory_system"]["controller"]
    cycles = int(frontend_stats["cycles_recorded_core_0"])
    return Result(
        workload=workload,
        policy=policy.name,
        view_selection=policy.view_selection,
        row_policy=policy.row_policy,
        refresh_mode=refresh_mode,
        refresh_preserve_open_rows=refresh_preserve_open_rows,
        cycles=cycles,
        memory_cycles=int(controller_stats["cycles"]),
        memory_access_cycles=int(frontend_stats["memory_access_cycles_recorded_core_0"]),
        ipc=instructions / cycles,
        row_hits=int(controller_stats["row_hits"]),
        row_misses=int(controller_stats["row_misses"]),
        row_conflicts=int(controller_stats["row_conflicts"]),
        reads_served=int(controller_stats["num_read_reqs_served"]),
        writes_served=int(controller_stats["num_write_reqs_served"]),
        internal_refreshes=int(controller_stats["num_internal_refreshes"]),
        act_nacks=int(controller_stats["num_act_nacks"]),
        average_read_latency=float(controller_stats["avg_read_latency"]),
        total_throughput_MBps=float(controller_stats["total_throughput_MBps"]),
        wall_seconds=monotonic() - start,
    )


def add_comparisons(records: list[dict]) -> list[dict]:
    by_workload = {(row["workload"], row["policy"]): row for row in records}
    summaries = []
    for workload in sorted({row["workload"] for row in records}):
        baseline = by_workload[(workload, "one_view")]
        for policy in policies():
            row = by_workload[(workload, policy.name)]
            row_accesses = row["row_hits"] + row["row_misses"] + row["row_conflicts"]
            summaries.append({
                "workload": workload,
                "policy": policy.name,
                "cycles": row["cycles"],
                "speedup_vs_one_view": baseline["cycles"] / row["cycles"],
                "cycle_reduction_vs_one_view_pct": 100.0 * (1.0 - row["cycles"] / baseline["cycles"]),
                "row_hit_rate_pct": 100.0 * row["row_hits"] / row_accesses if row_accesses else 0.0,
                "average_read_latency": row["average_read_latency"],
                "act_nacks": row["act_nacks"],
            })
    return summaries


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@contextmanager
def suppress_stderr_fd(enabled: bool):
    if not enabled:
        yield
        return
    saved_stderr = os.dup(2)
    try:
        with open(os.devnull, "w") as sink:
            os.dup2(sink.fileno(), 2)
            yield
    finally:
        os.dup2(saved_stderr, 2)
        os.close(saved_stderr)


def main() -> None:
    args = parse_args()
    if args.instructions <= 0:
        raise ValueError("--instructions must be greater than zero")
    if args.workers <= 0:
        raise ValueError("--workers must be greater than zero")
    if args.output_dir is None:
        name = args.experiment_name or f"policy_{args.refresh_mode.lower()}"
        args.output_dir = EXPERIMENT_DIR / "output" / name
    completed_result = args.output_dir / "results.json"
    if completed_result.exists() and not args.overwrite:
        raise FileExistsError(
            f"Completed results already exist at {completed_result}; "
            "select another --output-dir or pass --overwrite"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.input_dir is None:
        args.input_dir = args.output_dir / "inputs"

    trace_paths: dict[str, str] = {}
    trace_records: dict[str, int] = {}
    for workload in args.workloads:
        source = (args.trace_root / workload).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"MORDOR trace does not exist: {source}")
        sliced = args.input_dir / f"{source.name}.first-{args.trace_lines}"
        trace_records[workload] = prepare_trace(source, sliced, args.trace_lines)
        trace_paths[workload] = str(sliced)

    jobs = [
        (workload, trace_paths[workload], policy)
        for workload in args.workloads
        for policy in policies()
    ]
    results: list[Result] = []
    print(f"Running {len(jobs)} simulations ({len(args.workloads)} workloads x 4 policies)")
    with suppress_stderr_fd(not args.verbose_ramulator):
        if args.workers == 1:
            for index, (workload, trace_path, policy) in enumerate(jobs, 1):
                print(f"[{index}/{len(jobs)}] {workload}: {policy.name}", flush=True)
                results.append(run_one(
                    workload, trace_path, policy, args.instructions, args.refresh_mode,
                    args.refresh_interval, args.refresh_duration,
                    args.refresh_preserve_open_rows,
                ))
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                futures = {
                    pool.submit(
                        run_one, workload, trace_path, policy, args.instructions,
                        args.refresh_mode, args.refresh_interval, args.refresh_duration,
                        args.refresh_preserve_open_rows,
                    ): (workload, policy.name)
                    for workload, trace_path, policy in jobs
                }
                for index, future in enumerate(as_completed(futures), 1):
                    workload, name = futures[future]
                    results.append(future.result())
                    print(f"[{index}/{len(jobs)}] completed {workload}: {name}", flush=True)

    records = [
        asdict(result)
        for result in sorted(results, key=lambda item: (item.workload, item.policy))
    ]
    summaries = add_comparisons(records)
    write_csv(args.output_dir / "measurements.csv", records)
    write_csv(args.output_dir / "summary.csv", summaries)
    metadata = {
        "experiment_name": args.experiment_name,
        "description": args.experiment_description,
        "config_path": str(args.config_path) if args.config_path else None,
        "config": args.config_data,
        "trace_root": str(args.trace_root.resolve()),
        "input_dir": str(args.input_dir.resolve()),
        "workloads": args.workloads,
        "trace_records": trace_records,
        "instructions": args.instructions,
        "num_simulated_cores": 1,
        "refresh_mode": args.refresh_mode,
        "refresh_interval": "nREFI" if args.refresh_interval < 0 else args.refresh_interval,
        "refresh_duration": "nRFCsb" if args.refresh_duration < 0 else args.refresh_duration,
        "refresh_preserve_open_rows": args.refresh_preserve_open_rows,
        "policies": [asdict(policy) for policy in policies()],
        "measurements": records,
        "summary": summaries,
    }
    (args.output_dir / "results.json").write_text(json.dumps(metadata, indent=2) + "\n")

    print("\nPolicy comparison")
    for row in summaries:
        print(
            f"  {row['workload']:<20} {row['policy']:<16} "
            f"cycle reduction={row['cycle_reduction_vs_one_view_pct']:+.2f}% "
            f"row hits={row['row_hit_rate_pct']:.2f}%"
        )
    print(f"\nResults: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
