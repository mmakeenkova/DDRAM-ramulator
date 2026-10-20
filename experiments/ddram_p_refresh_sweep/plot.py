"""Plot DDRAM-P refresh results and baseline-RBMPKI group distributions."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
import tomllib
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
_MATPLOTLIB_CACHE = Path(tempfile.gettempdir()) / f"ramulator-matplotlib-{os.getuid()}"
_MATPLOTLIB_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MATPLOTLIB_CACHE))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np


OUTPUT_ROOT = EXPERIMENT_DIR / "output"
DEFAULT_ORACLE_DIR = OUTPUT_ROOT / "oracle.interval-nREFI.duration-nRFCsb"
DEFAULT_NACK_DIR = OUTPUT_ROOT / "nack.interval-nREFI.duration-nRFCsb"
with (EXPERIMENT_DIR.parent / "figure_palette.toml").open("rb") as palette_file:
    _PALETTE_DATA = tomllib.load(palette_file)
COLORS = _PALETTE_DATA["colors"]
SEMANTIC_COLORS = {
    name: COLORS[color_name]
    for name, color_name in _PALETTE_DATA["semantics"].items()
}


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


def read_measurements(result_dir: Path) -> dict[tuple[str, str], dict]:
    """Read raw per-configuration measurements from experiment metadata."""
    metadata_path = result_dir / "results.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(
            f"Numeric reporting requires experiment metadata: {metadata_path}"
        )
    metadata = json.loads(metadata_path.read_text())
    measurements = metadata.get("measurements", [])
    if not measurements:
        raise ValueError(f"No measurements in experiment metadata: {metadata_path}")
    return {
        (str(row["workload"]), str(row["configuration"])): row
        for row in measurements
    }


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


def read_baseline_rbmpki(
    result_dir: Path,
    workloads: list[str],
) -> dict[str, float]:
    """Return one-view/no-refresh row-buffer misses per kilo instruction.

    A row access that does not hit is recorded by the controller either as a
    row miss (closed bank) or a row conflict (different row open), so both
    outcomes contribute to RBMPKI.  The no-refresh, one-view baseline keeps
    refresh behavior and DDRAM-P view selection from affecting classification.
    """
    metadata_path = result_dir / "results.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(
            f"RBMPKI grouping requires experiment metadata: {metadata_path}"
        )
    metadata = json.loads(metadata_path.read_text())
    instructions = int(metadata.get("instructions", 0))
    if instructions <= 0:
        raise ValueError(f"Invalid instruction count in {metadata_path}: {instructions}")

    baseline = {
        row["workload"]: row
        for row in metadata.get("measurements", [])
        if row.get("configuration") == "one_view_no_refresh"
    }
    missing = sorted(set(workloads) - set(baseline))
    if missing:
        raise ValueError(
            f"Missing one_view_no_refresh measurements in {metadata_path}: {missing}"
        )
    return {
        workload: 1000.0
        * (
            float(baseline[workload]["row_misses"])
            + float(baseline[workload]["row_conflicts"])
        )
        / instructions
        for workload in workloads
    }


def rbmpki_groups(
    values: dict[str, float],
) -> list[tuple[str, list[str]]]:
    """Split workloads sorted by baseline RBMPKI into equal-count terciles."""
    ordered = sorted(values, key=lambda workload: (values[workload], workload))
    names = ("Low RBMPKI", "Medium RBMPKI", "High RBMPKI")
    return [
        (name, [ordered[int(index)] for index in indices])
        for name, indices in zip(names, np.array_split(np.arange(len(ordered)), 3))
    ]


def aggregate_refresh_overhead(
    rows: dict[str, dict[str, float | str]],
    workloads: list[str],
    field: str,
) -> float:
    """Geomean refresh/no-refresh cycle ratio, expressed as overhead."""
    ratios = np.asarray(
        [1.0 + float(rows[workload][field]) / 100.0 for workload in workloads],
        dtype=float,
    )
    if np.any(ratios <= 0):
        raise ValueError(f"Refresh overhead produced a non-positive cycle ratio: {ratios}")
    return 100.0 * (float(np.exp(np.mean(np.log(ratios)))) - 1.0)


def aggregate_cycle_reduction(values: list[float]) -> float:
    """Geomean normalized cycle ratio, expressed as a cycle reduction."""
    ratios = np.asarray([1.0 - value / 100.0 for value in values], dtype=float)
    if np.any(ratios <= 0):
        raise ValueError(f"Cycle reduction produced a non-positive cycle ratio: {ratios}")
    return 100.0 * (1.0 - float(np.exp(np.mean(np.log(ratios)))))


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


def style_axis(ax, labels: list[str], ylabel: str, *, show_xlabels: bool = True) -> None:
    ax.set_ylabel(ylabel, fontsize=16)
    ax.set_xticks(np.arange(len(labels)))
    if show_xlabels:
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    else:
        ax.tick_params(axis="x", labelbottom=False)
    ax.tick_params(axis="y", labelsize=12)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, zorder=0)
    ax.axhline(
        0,
        color=SEMANTIC_COLORS["zero_line"],
        linestyle="--",
        linewidth=1.2,
        zorder=2,
    )
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
            SEMANTIC_COLORS["oracle_one_view"],
        ),
        (
            "Oracle · 2 views",
            [float(oracle[name]["two_view_refresh_overhead_pct"]) for name in workloads],
            SEMANTIC_COLORS["oracle_two_views"],
        ),
        (
            "NACK · 1 view",
            [float(nack[name]["one_view_refresh_overhead_pct"]) for name in workloads],
            SEMANTIC_COLORS["nack_one_view"],
        ),
        (
            "NACK · 2 views",
            [float(nack[name]["two_view_refresh_overhead_pct"]) for name in workloads],
            SEMANTIC_COLORS["nack_two_views"],
        ),
    ]

    figure_width = max(14.0, 0.36 * len(workloads))
    fig, axes = plt.subplots(
        2,
        1,
        figsize=(figure_width, 10.0),
        sharex=True,
        constrained_layout=True,
    )
    grouped_bars(
        axes[0],
        x,
        [
            ("No refresh", no_refresh_reduction, SEMANTIC_COLORS["no_refresh"]),
            ("Oracle", oracle_reduction, SEMANTIC_COLORS["oracle"]),
            ("NACK", nack_reduction, SEMANTIC_COLORS["nack"]),
        ],
        width=0.23,
    )
    style_axis(axes[0], labels, "Two-view cycle reduction [%]", show_xlabels=False)
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


def make_rbmpki_boxplot(
    oracle: dict[str, dict[str, float | str]],
    nack: dict[str, dict[str, float | str]],
    groups: list[tuple[str, list[str]]],
):
    series = [
        (
            "Oracle · 1 view",
            oracle,
            "one_view_refresh_overhead_pct",
            SEMANTIC_COLORS["oracle_one_view"],
        ),
        (
            "Oracle · 2 views",
            oracle,
            "two_view_refresh_overhead_pct",
            SEMANTIC_COLORS["oracle_two_views"],
        ),
        (
            "NACK · 1 view",
            nack,
            "one_view_refresh_overhead_pct",
            SEMANTIC_COLORS["nack_one_view"],
        ),
        (
            "NACK · 2 views",
            nack,
            "two_view_refresh_overhead_pct",
            SEMANTIC_COLORS["nack_two_views"],
        ),
    ]
    centers = np.arange(len(groups), dtype=float)
    offsets = np.linspace(-0.27, 0.27, len(series))

    fig, ax = plt.subplots(figsize=(11.5, 5.8), constrained_layout=True)
    for offset, (_, rows, field, color) in zip(offsets, series):
        distributions = [
            [float(rows[workload][field]) for workload in workloads]
            for _, workloads in groups
        ]
        ax.boxplot(
            distributions,
            positions=centers + offset,
            widths=0.16,
            patch_artist=True,
            showmeans=True,
            manage_ticks=False,
            boxprops={"facecolor": color, "edgecolor": "#1a1a1a", "linewidth": 1.0},
            whiskerprops={"color": "#1a1a1a", "linewidth": 1.0},
            capprops={"color": "#1a1a1a", "linewidth": 1.0},
            medianprops={"color": SEMANTIC_COLORS["median"], "linewidth": 1.5},
            meanprops={
                "marker": "D",
                "markerfacecolor": "white",
                "markeredgecolor": "#1a1a1a",
                "markersize": 5,
            },
            flierprops={
                "marker": "o",
                "markerfacecolor": color,
                "markeredgecolor": "#1a1a1a",
                "markersize": 4,
                "alpha": 0.65,
            },
        )
        # Offset the geomean marker slightly within the same box so it does not
        # obscure the arithmetic-mean diamond when the two values are close.
        ax.scatter(
            centers + offset + 0.025,
            [aggregate_refresh_overhead(rows, workloads, field) for _, workloads in groups],
            marker="X",
            s=48,
            color=COLORS["charcoal"],
            linewidths=0.8,
            zorder=5,
        )
    ax.set_xticks(
        centers,
        [f"{name}\n(n={len(workloads)})" for name, workloads in groups],
        fontsize=12,
    )
    ax.set_ylabel("Refresh cycle overhead [%]", fontsize=15)
    ax.set_title("Refresh overhead by one-view/no-refresh RBMPKI tercile", fontsize=16)
    ax.tick_params(axis="y", labelsize=11)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, zorder=0)
    ax.axhline(
        0,
        color=SEMANTIC_COLORS["zero_line"],
        linestyle="--",
        linewidth=1.2,
        zorder=2,
    )
    ax.legend(
        handles=[
            Patch(facecolor=color, edgecolor="#1a1a1a", label=label)
            for label, _, _, color in series
        ]
        + [
            Line2D(
                [0],
                [0],
                marker="D",
                linestyle="none",
                markerfacecolor="white",
                markeredgecolor="#1a1a1a",
                label="Arithmetic mean",
            ),
            Line2D(
                [0],
                [0],
                marker="X",
                linestyle="none",
                markerfacecolor=COLORS["charcoal"],
                markeredgecolor=COLORS["charcoal"],
                label="Geomean cycles",
            )
        ],
        loc="best",
        frameon=True,
        facecolor="white",
        edgecolor="#1a1a1a",
        fontsize=10,
    )
    for spine in ax.spines.values():
        spine.set_color("#1a1a1a")
        spine.set_linewidth(1.0)
    return fig


def write_rbmpki_groups(
    path: Path,
    values: dict[str, float],
    groups: list[tuple[str, list[str]]],
    oracle: dict[str, dict[str, float | str]],
    nack: dict[str, dict[str, float | str]],
) -> None:
    overhead_fields = (
        ("Oracle 1 view", oracle, "one_view_refresh_overhead_pct"),
        ("Oracle 2 views", oracle, "two_view_refresh_overhead_pct"),
        ("NACK 1 view", nack, "one_view_refresh_overhead_pct"),
        ("NACK 2 views", nack, "two_view_refresh_overhead_pct"),
    )
    lines = [
        "DDRAM-P workload groups by baseline RBMPKI",
        "",
        "RBMPKI = 1000 * (row_misses + row_conflicts) / retired instructions.",
        "The baseline is one_view_no_refresh; workloads are sorted by RBMPKI and",
        "split into three equal-count groups with numpy.array_split.",
        "The box plot's diamond is the arithmetic mean and its X is the cycle-ratio",
        "geomean; its center line is the median, the box is the interquartile range,",
        "and whiskers use 1.5 IQR.",
        "",
    ]
    for name, workloads in groups:
        group_values = [values[workload] for workload in workloads]
        lines.append(
            f"{name} (n={len(workloads)}, range={min(group_values):.4f}-{max(group_values):.4f} RBMPKI)"
        )
        for label, rows, field in overhead_fields:
            mean = np.mean([float(rows[workload][field]) for workload in workloads])
            lines.append(f"  mean {label} refresh overhead: {mean:+.4f}%")
            geomean = aggregate_refresh_overhead(rows, workloads, field)
            lines.append(f"  geomean {label} refresh overhead: {geomean:+.4f}%")
        lines.append("  workloads:")
        for workload in workloads:
            lines.append(f"    {workload:<24} {values[workload]:.6f} RBMPKI")
        lines.append("")
    path.write_text("\n".join(lines) + "\n")


def write_numeric_results(
    path: Path,
    workloads: list[str],
    values: dict[str, float],
    groups: list[tuple[str, list[str]]],
    oracle: dict[str, dict[str, float | str]],
    nack: dict[str, dict[str, float | str]],
    oracle_measurements: dict[tuple[str, str], dict],
    nack_measurements: dict[tuple[str, str], dict],
) -> None:
    """Write exact cycle counts and values underlying the refresh figures."""
    group_for = {
        workload: group_name
        for group_name, members in groups
        for workload in members
    }
    lines = [
        "# DDRAM-P refresh numeric results",
        "",
        "Values below are the numeric inputs to the refresh bar and RBMPKI box plots.",
        "The no-refresh cycle columns come from the Oracle experiment's matched controls.",
        "",
        "## Execution cycles",
        "",
        "| Workload | RBMPKI | Group | No refresh · 1 view | No refresh · 2 views | Oracle · 1 view | Oracle · 2 views | NACK · 1 view | NACK · 2 views |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for workload in workloads:
        cycle_sources = (
            (oracle_measurements, "one_view_no_refresh"),
            (oracle_measurements, "two_view_no_refresh"),
            (oracle_measurements, "one_view_oracle"),
            (oracle_measurements, "two_view_oracle"),
            (nack_measurements, "one_view_nack"),
            (nack_measurements, "two_view_nack"),
        )
        cycles = [int(source[(workload, config)]["cycles"]) for source, config in cycle_sources]
        lines.append(
            f"| {workload} | {values[workload]:.6f} | {group_for[workload]} | "
            + " | ".join(str(value) for value in cycles)
            + " |"
        )

    lines.extend([
        "",
        "## Plotted reductions and overheads (%)",
        "",
        "| Workload | No refresh · 2-view reduction | Oracle · 2-view reduction | NACK · 2-view reduction | Oracle · 1-view overhead | Oracle · 2-view overhead | NACK · 1-view overhead | NACK · 2-view overhead |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for workload in workloads:
        plotted = (
            100.0 * (1.0 - 1.0 / float(oracle[workload]["two_view_no_refresh_speedup"])),
            float(oracle[workload]["two_view_with_refresh_cycle_reduction_pct"]),
            float(nack[workload]["two_view_with_refresh_cycle_reduction_pct"]),
            float(oracle[workload]["one_view_refresh_overhead_pct"]),
            float(oracle[workload]["two_view_refresh_overhead_pct"]),
            float(nack[workload]["one_view_refresh_overhead_pct"]),
            float(nack[workload]["two_view_refresh_overhead_pct"]),
        )
        lines.append(
            f"| {workload} | "
            + " | ".join(f"{value:.6f}" for value in plotted)
            + " |"
        )

    aggregate_series = (
        (
            "No refresh · 2-view reduction",
            [100.0 * (1.0 - 1.0 / float(oracle[w]["two_view_no_refresh_speedup"])) for w in workloads],
            "reduction",
        ),
        (
            "Oracle · 2-view reduction",
            [float(oracle[w]["two_view_with_refresh_cycle_reduction_pct"]) for w in workloads],
            "reduction",
        ),
        (
            "NACK · 2-view reduction",
            [float(nack[w]["two_view_with_refresh_cycle_reduction_pct"]) for w in workloads],
            "reduction",
        ),
        (
            "Oracle · 1-view overhead",
            [float(oracle[w]["one_view_refresh_overhead_pct"]) for w in workloads],
            "overhead",
        ),
        (
            "Oracle · 2-view overhead",
            [float(oracle[w]["two_view_refresh_overhead_pct"]) for w in workloads],
            "overhead",
        ),
        (
            "NACK · 1-view overhead",
            [float(nack[w]["one_view_refresh_overhead_pct"]) for w in workloads],
            "overhead",
        ),
        (
            "NACK · 2-view overhead",
            [float(nack[w]["two_view_refresh_overhead_pct"]) for w in workloads],
            "overhead",
        ),
    )
    lines.extend([
        "",
        "## All-workload aggregates",
        "",
        "Arithmetic means average the per-workload percentages. Geomeans are",
        "computed from positive normalized cycle ratios and converted back to percent.",
        "",
        "| Metric | Arithmetic mean (%) | Geomean cycle metric (%) |",
        "|---|---:|---:|",
    ])
    for label, metric_values, kind in aggregate_series:
        arithmetic_mean = float(np.mean(metric_values))
        if kind == "reduction":
            geomean = aggregate_cycle_reduction(metric_values)
        else:
            ratios = np.asarray([1.0 + value / 100.0 for value in metric_values])
            geomean = 100.0 * (float(np.exp(np.mean(np.log(ratios)))) - 1.0)
        lines.append(f"| {label} | {arithmetic_mean:.6f} | {geomean:.6f} |")

    lines.extend([
        "",
        "## RBMPKI-group aggregate markers",
        "",
        "Geomean overhead is derived from refresh/no-refresh cycle ratios, not signed percentages.",
        "",
        "| Group | Configuration | Arithmetic mean overhead (%) | Geomean cycle overhead (%) |",
        "|---|---|---:|---:|",
    ])
    overhead_fields = (
        ("Oracle · 1 view", oracle, "one_view_refresh_overhead_pct"),
        ("Oracle · 2 views", oracle, "two_view_refresh_overhead_pct"),
        ("NACK · 1 view", nack, "one_view_refresh_overhead_pct"),
        ("NACK · 2 views", nack, "two_view_refresh_overhead_pct"),
    )
    for group_name, members in groups:
        for label, rows, field in overhead_fields:
            arithmetic_mean = np.mean([float(rows[workload][field]) for workload in members])
            geomean = aggregate_refresh_overhead(rows, members, field)
            lines.append(
                f"| {group_name} | {label} | {arithmetic_mean:.6f} | {geomean:.6f} |"
            )
    lines.append("")
    path.write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    oracle = read_rows(args.oracle_dir / "summary.csv")
    nack = read_rows(args.nack_dir / "summary.csv")
    available = require_matching_workloads(oracle, nack)
    workloads = workload_order(args.oracle_dir, available)

    oracle_rbmpki = read_baseline_rbmpki(args.oracle_dir, workloads)
    nack_rbmpki = read_baseline_rbmpki(args.nack_dir, workloads)
    inconsistent = [
        workload
        for workload in workloads
        if not np.isclose(oracle_rbmpki[workload], nack_rbmpki[workload])
    ]
    if inconsistent:
        raise ValueError(
            "Oracle and NACK one-view/no-refresh RBMPKI baselines differ for: "
            f"{inconsistent}"
        )
    groups = rbmpki_groups(oracle_rbmpki)
    oracle_measurements = read_measurements(args.oracle_dir)
    nack_measurements = read_measurements(args.nack_dir)

    figure = make_figure(oracle, nack, workloads, args.title)
    boxplot = make_rbmpki_boxplot(oracle, nack, groups)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    boxplot_output = args.output.with_name(f"{args.output.name}_rbmpki_boxplot")
    for file_format in args.formats:
        destination = args.output.with_suffix(f".{file_format}")
        boxplot_destination = boxplot_output.with_suffix(f".{file_format}")
        save_options = {"dpi": args.dpi} if file_format == "png" else {}
        figure.savefig(destination, bbox_inches="tight", **save_options)
        boxplot.savefig(boxplot_destination, bbox_inches="tight", **save_options)
        print(f"Wrote {destination.resolve()}")
        print(f"Wrote {boxplot_destination.resolve()}")
    groups_path = args.output.with_name(f"{args.output.name}_rbmpki_groups.txt")
    write_rbmpki_groups(groups_path, oracle_rbmpki, groups, oracle, nack)
    print(f"Wrote {groups_path.resolve()}")
    numeric_path = args.output.with_name(f"{args.output.name}_numeric_results.md")
    write_numeric_results(
        numeric_path,
        workloads,
        oracle_rbmpki,
        groups,
        oracle,
        nack,
        oracle_measurements,
        nack_measurements,
    )
    print(f"Wrote {numeric_path.resolve()}")
    plt.close(figure)
    plt.close(boxplot)


if __name__ == "__main__":
    main()
