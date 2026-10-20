"""Run named DDRAM-P experiment configurations across the complete MORDOR corpus."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


EXPERIMENT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = EXPERIMENT_DIR / "configs"
RUNNER = EXPERIMENT_DIR / "run.py"
DEFAULT_TRACE_ROOT = Path(
    os.environ.get("MORDOR_CPUTRACES", "/home/maria/MORDOR/cputraces/cputraces")
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--configs",
        nargs="+",
        required=True,
        help="Named configs below configs/, or paths to JSON config files.",
    )
    parser.add_argument("--trace-root", type=Path, default=DEFAULT_TRACE_ROOT)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=EXPERIMENT_DIR / "output" / "all",
    )
    parser.add_argument(
        "--traces",
        nargs="+",
        default=None,
        help="Optional explicit trace subset; by default every regular file is used.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N traces.")
    parser.add_argument("--jobs", type=int, default=1, help="Concurrent trace processes.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve_config(value: str) -> tuple[Path, dict]:
    candidate = Path(value).expanduser()
    if not candidate.is_file():
        candidate = CONFIG_DIR / (value if value.endswith(".json") else f"{value}.json")
    if not candidate.is_file():
        raise FileNotFoundError(f"Experiment configuration does not exist: {value}")
    path = candidate.resolve()
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or not config.get("name"):
        raise ValueError(f"Configuration requires a non-empty name: {path}")
    return path, config


def discover_traces(trace_root: Path, requested: list[str] | None, limit: int | None) -> list[str]:
    trace_root = trace_root.expanduser().resolve()
    if not trace_root.is_dir():
        raise FileNotFoundError(f"MORDOR trace directory does not exist: {trace_root}")
    if requested is None:
        traces = sorted(path.name for path in trace_root.iterdir() if path.is_file())
    else:
        traces = list(dict.fromkeys(requested))
    missing = [name for name in traces if not (trace_root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"MORDOR traces do not exist below {trace_root}: {missing}")
    if limit is not None:
        if limit <= 0:
            raise ValueError("--limit must be greater than zero")
        traces = traces[:limit]
    if not traces:
        raise ValueError("No traces selected")
    return traces


def result_matches_config(result_path: Path, config_path: Path, config: dict, trace: str) -> bool:
    try:
        result = json.loads(result_path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return (
        result.get("experiment_name") == config["name"]
        and result.get("config_path") == str(config_path)
        and result.get("config") == config
        and result.get("workloads") == [trace]
    )


def run_trace(
    config_path: Path,
    config: dict,
    trace_root: Path,
    input_dir: Path,
    output_dir: Path,
    trace: str,
    overwrite: bool,
) -> tuple[str, str, str]:
    run_dir = output_dir / "runs" / trace
    result_path = run_dir / "results.json"
    if result_path.is_file() and not overwrite:
        if not result_matches_config(result_path, config_path, config, trace):
            return trace, "failed", f"existing result does not match selected configuration: {result_path}"
        return trace, "skipped", "already complete"

    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(RUNNER),
        "--config",
        str(config_path),
        "--trace-root",
        str(trace_root),
        "--workloads",
        trace,
        "--input-dir",
        str(input_dir),
        "--output-dir",
        str(run_dir),
    ]
    if overwrite:
        command.append("--overwrite")
    log_path = log_dir / f"{trace}.log"
    with log_path.open("w") as log:
        completed = subprocess.run(
            command,
            cwd=EXPERIMENT_DIR.parent.parent,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        return trace, "failed", f"exit {completed.returncode}; see {log_path}"
    return trace, "completed", str(result_path)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def aggregate(
    output_dir: Path,
    config_path: Path,
    config: dict,
    trace_root: Path,
    requested: list[str],
    failures: dict[str, str],
) -> int:
    measurements = []
    summaries = []
    trace_records = {}
    completed = []
    for trace in requested:
        result_path = output_dir / "runs" / trace / "results.json"
        if not result_path.is_file():
            continue
        result = json.loads(result_path.read_text())
        measurements.extend(result["measurements"])
        summaries.extend(result["summary"])
        trace_records.update(result["trace_records"])
        completed.append(trace)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "measurements.csv", measurements)
    write_csv(output_dir / "summary.csv", summaries)
    aggregate_result = {
        "experiment_name": config["name"],
        "description": config.get("description"),
        "config_path": str(config_path),
        "config": config,
        "trace_root": str(trace_root),
        "requested_workloads": requested,
        "completed_workloads": completed,
        "failed_workloads": failures,
        "trace_records": trace_records,
        "instructions": config.get("instructions"),
        "refresh_mode": config.get("refresh_mode"),
        "refresh_interval": config.get("refresh_interval"),
        "refresh_duration": config.get("refresh_duration"),
        "measurements": measurements,
        "summary": summaries,
    }
    (output_dir / "results.json").write_text(json.dumps(aggregate_result, indent=2) + "\n")
    return len(completed)


def run_config(args: argparse.Namespace, config_path: Path, config: dict, traces: list[str]) -> bool:
    output_dir = args.output_root / config["name"]
    print(
        f"\n{config['name']}: {len(traces)} traces x 4 model points "
        f"({config.get('instructions', 'default')} instructions each)"
    )
    print(f"Output: {output_dir.resolve()}")
    if args.dry_run:
        for trace in traces:
            print(f"  {trace}")
        return True

    failures = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(
                run_trace,
                config_path,
                config,
                args.trace_root.resolve(),
                args.output_root.resolve() / "inputs",
                output_dir,
                trace,
                args.overwrite,
            ): trace
            for trace in traces
        }
        for index, future in enumerate(as_completed(futures), 1):
            trace, status, detail = future.result()
            print(f"[{index}/{len(traces)}] {status:9} {trace}: {detail}", flush=True)
            if status == "failed":
                failures[trace] = detail

    completed = aggregate(
        output_dir, config_path, config, args.trace_root.resolve(), traces, failures
    )
    print(
        f"Aggregated {completed}/{len(traces)} workloads in "
        f"{output_dir.resolve()}"
    )
    return not failures


def main() -> None:
    args = parse_args()
    if args.jobs <= 0:
        raise ValueError("--jobs must be greater than zero")
    traces = discover_traces(args.trace_root, args.traces, args.limit)
    configs = [resolve_config(value) for value in args.configs]
    print(f"Selected {len(traces)} of {len(discover_traces(args.trace_root, None, None))} traces")
    success = True
    for config_path, config in configs:
        success = run_config(args, config_path, config, traces) and success
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
