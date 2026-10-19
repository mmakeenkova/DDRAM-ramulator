"""Plot the DDRAM-P MORDOR refresh comparison as grouped bar charts."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
_MATPLOTLIB_CACHE = Path(tempfile.gettempdir()) / f"ramulator-matplotlib-{os.getuid()}"
_MATPLOTLIB_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MATPLOTLIB_CACHE))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


OUTPUT_ROOT = EXPERIMENT_DIR / "output"
DEFAULT_ORACLE_DIR = OUTPUT_ROOT / "oracle.interval-nREFI.duration-nRFCsb"
DEFAULT_NACK_DIR = OUTPUT_ROOT / "nack.interval-nREFI.duration-nRFCsb"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-dir", type=Path, default=DEFAULT_ORACLE_DIR)
    parser.add_argument("--nack-dir", type=Path, default=DEFAULT_NACK_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_ROOT / "ddram_p_refresh_comparison",
        help="Output path without an extension.",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=("png", "pdf", "svg"),
        default=("png", "pdf"),
    )
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument(
        "--title",
        default=None,
        help="Optional figure title; omitted by default for paper-friendly output.",
    )
    return parser.parse_args()


def read_rows(path: Path) -> dict[str, dict[str, float | str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Result file does not exist: {path}")
    rows = {}
    with path.open(newline="") as input_file:
        for raw in csv.DictReader(input_file):
            workload = raw.pop("workload")
            rows[workload] = {
                key: float(value) if key != "workload" else value
                for key, value in raw.items()
            }
    if not rows:
        raise ValueError(f"Result file is empty: {path}")
    return rows


def workload_order(result_dir: Path, available: set[str]) -> list[str]:
    metadata_path = result_dir / "results.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text())
        ordered = [name for name in metadata.get("workloads", []) if name in available]
        if set(ordered) == available:
            return ordered
    return sorted(available)


def require_matching_workloads(
    oracle: dict[str, dict[str, float | str]],
    nack: dict[str, dict[str, float | str]],
) -> set[str]:
    oracle_names = set(oracle)
    nack_names = set(nack)
    if oracle_names != nack_names:
        only_oracle = sorted(oracle_names - nack_names)
        only_nack = sorted(nack_names - oracle_names)
        raise ValueError(
            "Oracle and NACK workloads differ: "
            f"only Oracle={only_oracle}, only NACK={only_nack}"
        )
    return oracle_names


def clean_label(name: str) -> str:
    return name.removesuffix(".trace")


def grouped_bars(
    ax,
    x: np.ndarray,
    series: list[tuple[str, list[float], str]],
    width: float,
) -> None:
    center = (len(series) - 1) / 2
    for index, (label, values, color) in enumerate(series):
        ax.bar(
            x + (index - center) * width,
            values,
            width,
            label=label,
            color=color,
            edgecolor="#1a1a1a",
            linewidth=0.9,
            zorder=3,
        )


def style_axis(ax, labels: list[str], ylabel: str) -> None:
    ax.set_ylabel(ylabel, fontsize=16)
    ax.set_xticks(np.arange(len(labels)), labels, rotation=28, ha="right", fontsize=12)
    ax.tick_params(axis="y", labelsize=12)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, zorder=0)
    ax.axhline(0, color="#e53935", linestyle="--", linewidth=1.2, zorder=2)
    for spine in ax.spines.values():
        spine.set_color("#1a1a1a")
        spine.set_linewidth(1.0)


def make_figure(
    oracle: dict[str, dict[str, float | str]],
    nack: dict[str, dict[str, float | str]],
    workloads: list[str],
    title: str | None,
):
    labels = [clean_label(name) for name in workloads]
    x = np.arange(len(workloads), dtype=float)

    no_refresh_reduction = [
        100.0 * (1.0 - 1.0 / float(oracle[name]["two_view_no_refresh_speedup"]))
        for name in workloads
    ]
    oracle_reduction = [
        float(oracle[name]["two_view_with_refresh_cycle_reduction_pct"])
        for name in workloads
    ]
    nack_reduction = [
        float(nack[name]["two_view_with_refresh_cycle_reduction_pct"])
        for name in workloads
    ]

    overhead_series = [
        (
            "Oracle · 1 view",
            [float(oracle[name]["one_view_refresh_overhead_pct"]) for name in workloads],
            "#d9d9d9",
        ),
        (
            "Oracle · 2 views",
            [float(oracle[name]["two_view_refresh_overhead_pct"]) for name in workloads],
            "#aaaaaa",
        ),
        (
            "NACK · 1 view",
            [float(nack[name]["one_view_refresh_overhead_pct"]) for name in workloads],
            "#777777",
        ),
        (
            "NACK · 2 views",
            [float(nack[name]["two_view_refresh_overhead_pct"]) for name in workloads],
            "#3f3f3f",
        ),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(12.2, 4.9), constrained_layout=True)
    grouped_bars(
        axes[0],
        x,
        [
            ("No refresh", no_refresh_reduction, "#d9d9d9"),
            ("Oracle", oracle_reduction, "#929292"),
            ("NACK", nack_reduction, "#4f4f4f"),
        ],
        width=0.23,
    )
    style_axis(axes[0], labels, "Two-view cycle reduction [%]")
    axes[0].legend(
        title="Refresh interface",
        loc="upper right",
        frameon=True,
        facecolor="white",
        edgecolor="#1a1a1a",
        fontsize=11,
        title_fontsize=12,
    )

    grouped_bars(axes[1], x, overhead_series, width=0.18)
    style_axis(axes[1], labels, "Refresh cycle overhead [%]")
    axes[1].legend(
        title="Configuration",
        loc="upper right",
        frameon=True,
        facecolor="white",
        edgecolor="#1a1a1a",
        fontsize=10,
        title_fontsize=12,
    )

    if title:
        fig.suptitle(title, fontsize=17)
    return fig


def main() -> None:
    args = parse_args()
    oracle = read_rows(args.oracle_dir / "summary.csv")
    nack = read_rows(args.nack_dir / "summary.csv")
    available = require_matching_workloads(oracle, nack)
    workloads = workload_order(args.oracle_dir, available)

    figure = make_figure(oracle, nack, workloads, args.title)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for file_format in args.formats:
        destination = args.output.with_suffix(f".{file_format}")
        save_options = {"dpi": args.dpi} if file_format == "png" else {}
        figure.savefig(destination, bbox_inches="tight", **save_options)
        print(f"Wrote {destination.resolve()}")
    plt.close(figure)


if __name__ == "__main__":
    main()
