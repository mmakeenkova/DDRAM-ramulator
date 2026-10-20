"""Run matched DDRAM-P periodic and DRAM-managed refresh experiments."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
import csv
from dataclasses import asdict, dataclass
from itertools import islice
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic


EXPERIMENT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = EXPERIMENT_DIR / "configs"
DEFAULT_TRACE_ROOT = Path(
    os.environ.get("MORDOR_CPUTRACES", "/home/maria/MORDOR/cputraces/cputraces")
)
CONFIG_KEYS = {
    "name", "description", "trace_root", "workloads", "instructions",
    "trace_lines", "workers",
}


@dataclass(frozen=True)
class Configuration:
    name: str
    view_selection: str
    refresh_interface: str
    managed_refresh: str
    refresh_view_count: int


@dataclass
class Result:
    workload: str
    configuration: str
    view_selection: str
    refresh_interface: str
    managed_refresh: str
    refresh_view_count: int
    cycles: int
    memory_cycles: int
    memory_access_cycles: int
    ipc: float
    row_hits: int
    row_misses: int
    row_conflicts: int
    reads_served: int
    writes_served: int
    maintenance_requests: int
    maintenance_requests_served: int
    internal_refreshes: int
    act_nacks: int
    average_read_latency: float
    total_throughput_MBps: float
    wall_seconds: float


def configurations() -> tuple[Configuration, ...]:
    """Return matched points; all use FR-FCFS-view-aware and open-page policy."""
    result = []
    for views, view_selection in ((1, "AlwaysA"), (2, "TwoView")):
        prefix = "one_view" if views == 1 else "two_view"
        result.extend((
            Configuration(f"{prefix}_no_refresh", view_selection, "none", "Disabled", views),
            Configuration(f"{prefix}_periodic", view_selection, "periodic_refab", "Disabled", views),
            Configuration(f"{prefix}_oracle", view_selection, "dram_managed", "Oracle", views),
            Configuration(f"{prefix}_nack", view_selection, "dram_managed", "Nack", views),
        ))
    return tuple(result)


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
        "workloads": ["429.mcf", "538.imagick", "ycsb_aserver", "stream_10.trace"],
        "instructions": 1_000_000,
        "trace_lines": 250_000,
        "workers": 1,
    }
    defaults.update({key: value for key, value in selected.items() if key in defaults})

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--list-configs", action="store_true")
    parser.add_argument("--trace-root", type=Path, default=Path(defaults["trace_root"]))
    parser.add_argument("--workloads", nargs="+", default=defaults["workloads"])
    parser.add_argument("--instructions", type=int, default=defaults["instructions"])
    parser.add_argument("--trace-lines", type=int, default=defaults["trace_lines"])
    parser.add_argument("--workers", type=int, default=defaults["workers"])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--verbose-ramulator", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--no-plot", action="store_true",
        help="Do not invoke plot.py after all simulations finish.",
    )
    args = parser.parse_args()
    args.config_path = selected_path
    args.config_data = selected
    args.experiment_name = selected.get("name", selected_path.stem if selected_path else None)
    args.experiment_description = selected.get("description")
    return args


def prepare_trace(source: Path, destination: Path, line_limit: int) -> int:
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
    configuration: Configuration,
    instructions: int,
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
    refresh_manager = (
        ramulator.refresh_manager.AllBank()
        if configuration.refresh_interface == "periodic_refab"
        else ramulator.refresh_manager.NoRefresh()
    )
    controller = ramulator.controller.GenericDDR(
        dram=dram,
        scheduler=ramulator.scheduler.FRFCFSViewAware(),
        refresh_manager=refresh_manager,
        row_policy=ramulator.row_policy.Open(),
        addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
        view_selection=configuration.view_selection,
        dram_managed_refresh=configuration.managed_refresh,
        dram_refresh_view_count=configuration.refresh_view_count,
        # Keep the row-preserving counterfactual out of this experiment.
        dram_refresh_preserve_open_rows=False,
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
        configuration=configuration.name,
        view_selection=configuration.view_selection,
        refresh_interface=configuration.refresh_interface,
        managed_refresh=configuration.managed_refresh,
        refresh_view_count=configuration.refresh_view_count,
        cycles=cycles,
        memory_cycles=int(controller_stats["cycles"]),
        memory_access_cycles=int(frontend_stats["memory_access_cycles_recorded_core_0"]),
        ipc=instructions / cycles,
        row_hits=int(controller_stats["row_hits"]),
        row_misses=int(controller_stats["row_misses"]),
        row_conflicts=int(controller_stats["row_conflicts"]),
        reads_served=int(controller_stats["num_read_reqs_served"]),
        writes_served=int(controller_stats["num_write_reqs_served"]),
        maintenance_requests=int(controller_stats.get("num_maintenance_reqs", 0)),
        maintenance_requests_served=int(controller_stats.get("num_maintenance_reqs_served", 0)),
        internal_refreshes=int(controller_stats["num_internal_refreshes"]),
        act_nacks=int(controller_stats["num_act_nacks"]),
        average_read_latency=float(controller_stats["avg_read_latency"]),
        total_throughput_MBps=float(controller_stats["total_throughput_MBps"]),
        wall_seconds=monotonic() - start,
    )


def add_comparisons(records: list[dict], instructions: int) -> list[dict]:
    indexed = {(row["workload"], row["configuration"]): row for row in records}
    summaries = []
    mechanisms = ("periodic", "oracle", "nack")
    for workload in sorted({row["workload"] for row in records}):
        one_baseline = indexed[(workload, "one_view_no_refresh")]
        rbmpki = 1000.0 * (
            one_baseline["row_misses"] + one_baseline["row_conflicts"]
        ) / instructions
        for views in ("one_view", "two_view"):
            baseline = indexed[(workload, f"{views}_no_refresh")]
            for mechanism in mechanisms:
                row = indexed[(workload, f"{views}_{mechanism}")]
                summaries.append({
                    "workload": workload,
                    "view_count": 1 if views == "one_view" else 2,
                    "refresh_interface": mechanism,
                    "baseline_cycles": baseline["cycles"],
                    "cycles": row["cycles"],
                    "refresh_cycle_overhead_pct": 100.0 * (row["cycles"] / baseline["cycles"] - 1.0),
                    "baseline_rbmpki": rbmpki,
                    "row_hit_rate_pct": 100.0 * row["row_hits"] / max(
                        1, row["row_hits"] + row["row_misses"] + row["row_conflicts"]
                    ),
                    "maintenance_requests_served": row["maintenance_requests_served"],
                    "internal_refreshes": row["internal_refreshes"],
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
    if args.instructions <= 0 or args.trace_lines <= 0 or args.workers <= 0:
        raise ValueError("instructions, trace-lines, and workers must all be positive")
    if args.output_dir is None:
        name = args.experiment_name or "periodic_refresh"
        args.output_dir = EXPERIMENT_DIR / "output" / name
    completed_result = args.output_dir / "results.json"
    if completed_result.exists() and not args.overwrite:
        raise FileExistsError(
            f"Completed results already exist at {completed_result}; pass --overwrite or choose another --output-dir"
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

    points = configurations()
    jobs = [
        (workload, trace_paths[workload], configuration)
        for workload in args.workloads
        for configuration in points
    ]
    results: list[Result] = []
    print(f"Running {len(jobs)} simulations ({len(args.workloads)} workloads x {len(points)} configurations)")
    with suppress_stderr_fd(not args.verbose_ramulator):
        if args.workers == 1:
            for index, (workload, trace_path, configuration) in enumerate(jobs, 1):
                print(f"[{index}/{len(jobs)}] {workload}: {configuration.name}", flush=True)
                results.append(run_one(workload, trace_path, configuration, args.instructions))
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                futures = {
                    pool.submit(run_one, workload, trace_path, configuration, args.instructions):
                    (workload, configuration.name)
                    for workload, trace_path, configuration in jobs
                }
                for index, future in enumerate(as_completed(futures), 1):
                    workload, name = futures[future]
                    results.append(future.result())
                    print(f"[{index}/{len(jobs)}] completed {workload}: {name}", flush=True)

    records = [asdict(item) for item in sorted(results, key=lambda item: (item.workload, item.configuration))]
    summaries = add_comparisons(records, args.instructions)
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
        "row_policy": "Open",
        "scheduler": "FRFCFSViewAware",
        "periodic_refresh_interval": "nREFI",
        "periodic_refresh_duration": "nRFC",
        "managed_refresh_interval": "nREFI",
        "managed_refresh_duration": "nRFCsb",
        "dram_refresh_preserve_open_rows": False,
        "configurations": [asdict(configuration) for configuration in points],
        "measurements": records,
        "summary": summaries,
    }
    completed_result.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Results: {args.output_dir.resolve()}")

    if not args.no_plot:
        output = args.output_dir / "rbmpki_refresh_comparison"
        subprocess.run(
            [sys.executable, str(EXPERIMENT_DIR / "plot.py"),
             "--result-dir", str(args.output_dir), "--output", str(output)],
            check=True,
        )


if __name__ == "__main__":
    main()
