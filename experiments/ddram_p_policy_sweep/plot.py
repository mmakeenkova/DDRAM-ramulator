"""Plot a DDRAM-P view-policy sweep as grouped bar charts."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
import tomllib
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
_CACHE = Path(tempfile.gettempdir()) / f"ramulator-matplotlib-{os.getuid()}"
_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_CACHE))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np


with (EXPERIMENT_DIR.parent / "figure_palette.toml").open("rb") as palette_file:
    _PALETTE_DATA = tomllib.load(palette_file)
COLORS = _PALETTE_DATA["colors"]
SEMANTIC_COLORS = {
    name: COLORS[color_name]
    for name, color_name in _PALETTE_DATA["semantics"].items()
}

POLICIES = (
    ("one_view", "One view", SEMANTIC_COLORS["one_view_policy"]),
    ("both_views", "Both views", SEMANTIC_COLORS["both_views_policy"]),
    ("auto_precharge", "Auto-precharge B", SEMANTIC_COLORS["auto_precharge_policy"]),
    ("queue_aware", "Queue-aware", SEMANTIC_COLORS["queue_aware_policy"]),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formats", nargs="+", choices=("png", "pdf", "svg"), default=("png", "pdf"))
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--title", default=None)
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, float | str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Result file does not exist: {path}")
    rows: list[dict[str, float | str]] = []
    with path.open(newline="") as input_file:
        for raw in csv.DictReader(input_file):
            rows.append({
                key: value if key in ("workload", "policy") else float(value)
                for key, value in raw.items()
            })
    if not rows:
        raise ValueError(f"Result file is empty: {path}")
    return rows


def workload_order(result_dir: Path, available: set[str]) -> list[str]:
    metadata_path = result_dir / "results.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text())
        source = metadata.get("requested_workloads", metadata.get("workloads", []))
        ordered = [name for name in source if name in available]
        if set(ordered) == available:
            return ordered
    return sorted(available)


def validate(rows: list[dict[str, float | str]]) -> tuple[dict[tuple[str, str], dict], set[str]]:
    indexed = {(str(row["workload"]), str(row["policy"])): row for row in rows}
    workloads = {str(row["workload"]) for row in rows}
    expected = {name for name, _, _ in POLICIES}
    incomplete = {
        workload: sorted(expected - {policy for candidate, policy in indexed if candidate == workload})
        for workload in workloads
    }
    incomplete = {name: missing for name, missing in incomplete.items() if missing}
    if incomplete:
        raise ValueError(f"Workloads are missing policy results: {incomplete}")
    return indexed, workloads


def read_baseline_rbmpki(
    result_dir: Path,
    workloads: list[str],
) -> dict[str, float]:
    """Return RBMPKI from the one-view run used as the policy baseline."""
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
        if row.get("policy") == "one_view"
    }
    missing = sorted(set(workloads) - set(baseline))
    if missing:
        raise ValueError(f"Missing one-view measurements in {metadata_path}: {missing}")
    return {
        workload: 1000.0
        * (
            float(baseline[workload]["row_misses"])
            + float(baseline[workload]["row_conflicts"])
        )
        / instructions
        for workload in workloads
    }


def rbmpki_groups(values: dict[str, float]) -> list[tuple[str, list[str]]]:
    """Split workloads sorted by one-view RBMPKI into equal-count terciles."""
    ordered = sorted(values, key=lambda workload: (values[workload], workload))
    names = ("Low RBMPKI", "Medium RBMPKI", "High RBMPKI")
    return [
        (name, [ordered[int(index)] for index in indices])
        for name, indices in zip(names, np.array_split(np.arange(len(ordered)), 3))
    ]


def grouped_bars(ax, x: np.ndarray, series: list[tuple[str, list[float], str]]) -> None:
    width = 0.19
    center = (len(series) - 1) / 2
    for index, (label, values, color) in enumerate(series):
        ax.bar(
            x + (index - center) * width, values, width,
            label=label, color=color, edgecolor="#1a1a1a", linewidth=0.9, zorder=3,
        )


def geometric_mean(values: list[float]) -> float:
    """Return a geometric mean, including a well-defined zero case."""
    if not values:
        raise ValueError("Cannot compute a geometric mean of an empty sequence")
    if any(value < 0 for value in values):
        raise ValueError(f"Geometric mean inputs must be non-negative: {values}")
    if any(value == 0 for value in values):
        return 0.0
    return float(np.exp(np.mean(np.log(values))))


def aggregate_cycle_reduction(
    indexed: dict[tuple[str, str], dict],
    workloads: list[str],
    policy: str,
) -> float:
    """Geomean normalized cycles, expressed as reduction versus one view."""
    normalized_cycles = [
        float(indexed[(workload, policy)]["cycles"])
        / float(indexed[(workload, "one_view")]["cycles"])
        for workload in workloads
    ]
    return 100.0 * (1.0 - geometric_mean(normalized_cycles))


def style_axis(
    ax,
    labels: list[str],
    ylabel: str,
    aggregate_index: int,
) -> None:
    ax.axvspan(
        aggregate_index - 0.5,
        aggregate_index + 0.5,
        color=SEMANTIC_COLORS["aggregate_background"],
        zorder=-1,
    )
    ax.axvline(
        aggregate_index - 0.5,
        color=COLORS["charcoal"],
        linestyle="--",
        linewidth=1.3,
        zorder=2,
    )
    ax.set_ylabel(ylabel, fontsize=16)
    ax.set_xticks(np.arange(len(labels)), labels, rotation=28, ha="right", fontsize=12)
    ax.set_xlim(-0.5, len(labels) - 0.5)
    ax.tick_params(axis="y", labelsize=12)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, zorder=0)
    for spine in ax.spines.values():
        spine.set_color("#1a1a1a")
        spine.set_linewidth(1.0)


def make_rbmpki_boxplot(
    indexed: dict[tuple[str, str], dict],
    groups: list[tuple[str, list[str]]],
):
    centers = np.arange(len(groups), dtype=float)
    offsets = np.linspace(-0.27, 0.27, len(POLICIES))
    fig, ax = plt.subplots(figsize=(11.5, 5.8), constrained_layout=True)

    for offset, (policy, _, color) in zip(offsets, POLICIES):
        distributions = [
            [
                float(indexed[(workload, policy)]["cycle_reduction_vs_one_view_pct"])
                for workload in workloads
            ]
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
            [aggregate_cycle_reduction(indexed, workloads, policy) for _, workloads in groups],
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
    ax.set_xlim(-0.5, len(groups) - 0.5)
    ax.set_ylabel("Cycle reduction vs. one view [%]", fontsize=15)
    ax.set_title("Scheduling-policy benefit by one-view RBMPKI tercile", fontsize=16)
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
            for _, label, color in POLICIES
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
    indexed: dict[tuple[str, str], dict],
) -> None:
    lines = [
        "DDRAM-P scheduling-policy workload groups by baseline RBMPKI",
        "",
        "RBMPKI = 1000 * (row_misses + row_conflicts) / retired instructions.",
        "The baseline is the one_view policy under this experiment's refresh mode;",
        "workloads are sorted by RBMPKI and split into three equal-count groups.",
        "The box plot's diamond is the arithmetic mean and its X is the cycle-ratio",
        "geomean; its center line is the median, the box is the interquartile range,",
        "and whiskers use 1.5 IQR.",
        "",
    ]
    for group_name, workloads in groups:
        group_values = [values[workload] for workload in workloads]
        lines.append(
            f"{group_name} (n={len(workloads)}, "
            f"range={min(group_values):.4f}-{max(group_values):.4f} RBMPKI)"
        )
        for policy, label, _ in POLICIES:
            mean = np.mean(
                [
                    float(indexed[(workload, policy)]["cycle_reduction_vs_one_view_pct"])
                    for workload in workloads
                ]
            )
            lines.append(f"  mean {label} cycle reduction: {mean:+.4f}%")
            geomean = aggregate_cycle_reduction(indexed, workloads, policy)
            lines.append(f"  geomean {label} cycle reduction: {geomean:+.4f}%")
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
    indexed: dict[tuple[str, str], dict],
) -> None:
    """Write the exact per-workload and aggregate values used by both plots."""
    group_for = {
        workload: group_name
        for group_name, members in groups
        for workload in members
    }
    lines = [
        "# DDRAM-P scheduling-policy numeric results",
        "",
        "Values below are the numeric inputs to the grouped-bar and RBMPKI box plots.",
        "RBMPKI uses the one-view run under this experiment's refresh mode.",
        "",
        "## Execution cycles",
        "",
        "| Workload | RBMPKI | Group | One view | Both views | Auto-precharge B | Queue-aware |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    for workload in workloads:
        cycles = [int(float(indexed[(workload, policy)]["cycles"])) for policy, _, _ in POLICIES]
        lines.append(
            f"| {workload} | {values[workload]:.6f} | {group_for[workload]} | "
            + " | ".join(str(value) for value in cycles)
            + " |"
        )

    lines.extend([
        "",
        "## Cycle reduction versus one view (%)",
        "",
        "| Workload | One view | Both views | Auto-precharge B | Queue-aware |",
        "|---|---:|---:|---:|---:|",
    ])
    for workload in workloads:
        reductions = [
            float(indexed[(workload, policy)]["cycle_reduction_vs_one_view_pct"])
            for policy, _, _ in POLICIES
        ]
        lines.append(
            f"| {workload} | "
            + " | ".join(f"{value:.6f}" for value in reductions)
            + " |"
        )

    lines.extend([
        "",
        "## Row-hit rate (%)",
        "",
        "| Workload | One view | Both views | Auto-precharge B | Queue-aware |",
        "|---|---:|---:|---:|---:|",
    ])
    for workload in workloads:
        rates = [
            float(indexed[(workload, policy)]["row_hit_rate_pct"])
            for policy, _, _ in POLICIES
        ]
        lines.append(
            f"| {workload} | "
            + " | ".join(f"{value:.6f}" for value in rates)
            + " |"
        )

    lines.extend([
        "",
        "## All-workload aggregates",
        "",
        "The arithmetic mean averages the per-workload reductions. The geomean",
        "reduction is derived from the geometric mean of normalized cycle counts.",
        "",
        "| Policy | Arithmetic mean cycle reduction (%) | Geomean cycle reduction (%) | Geomean row-hit rate (%) |",
        "|---|---:|---:|---:|",
    ])
    for policy, label, _ in POLICIES:
        arithmetic_mean = np.mean(
            [
                float(indexed[(workload, policy)]["cycle_reduction_vs_one_view_pct"])
                for workload in workloads
            ]
        )
        reduction = aggregate_cycle_reduction(indexed, workloads, policy)
        hit_rate = geometric_mean(
            [float(indexed[(workload, policy)]["row_hit_rate_pct"]) for workload in workloads]
        )
        lines.append(
            f"| {label} | {arithmetic_mean:.6f} | {reduction:.6f} | {hit_rate:.6f} |"
        )

    lines.extend([
        "",
        "## RBMPKI-group aggregate markers",
        "",
        "The geomean reduction is derived from normalized cycle counts, not signed percentages.",
        "",
        "| Group | Policy | Arithmetic mean reduction (%) | Geomean cycle reduction (%) |",
        "|---|---|---:|---:|",
    ])
    for group_name, members in groups:
        for policy, label, _ in POLICIES:
            arithmetic_mean = np.mean(
                [
                    float(indexed[(workload, policy)]["cycle_reduction_vs_one_view_pct"])
                    for workload in members
                ]
            )
            geomean = aggregate_cycle_reduction(indexed, members, policy)
            lines.append(
                f"| {group_name} | {label} | {arithmetic_mean:.6f} | {geomean:.6f} |"
            )
    lines.append("")
    path.write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    rows = read_rows(args.result_dir / "summary.csv")
    indexed, available = validate(rows)
    workloads = workload_order(args.result_dir, available)
    rbmpki = read_baseline_rbmpki(args.result_dir, workloads)
    groups = rbmpki_groups(rbmpki)
    labels = [name.removesuffix(".trace") for name in workloads] + ["GMean"]
    aggregate_index = len(workloads)
    x = np.arange(len(labels), dtype=float)

    cycle_series = [
        (
            label,
            [
                float(indexed[(workload, name)]["cycle_reduction_vs_one_view_pct"])
                for workload in workloads
            ]
            + [aggregate_cycle_reduction(indexed, workloads, name)],
            color,
        )
        for name, label, color in POLICIES
    ]
    hit_series = [
        (
            label,
            [float(indexed[(workload, name)]["row_hit_rate_pct"]) for workload in workloads]
            + [
                geometric_mean(
                    [
                        float(indexed[(workload, name)]["row_hit_rate_pct"])
                        for workload in workloads
                    ]
                )
            ],
            color,
        )
        for name, label, color in POLICIES
    ]

    fig, axes = plt.subplots(1, 2, figsize=(12.2, 4.9), constrained_layout=True)
    grouped_bars(axes[0], x, cycle_series)
    style_axis(
        axes[0],
        labels,
        "Cycle reduction vs. one view [%]",
        aggregate_index,
    )
    axes[0].axhline(
        0,
        color=SEMANTIC_COLORS["zero_line"],
        linestyle="--",
        linewidth=1.2,
        zorder=2,
    )
    grouped_bars(axes[1], x, hit_series)
    style_axis(axes[1], labels, "Row-hit rate [%]", aggregate_index)
    axes[1].legend(
        title="View policy", loc="best", frameon=True, facecolor="white",
        edgecolor="#1a1a1a", fontsize=10, title_fontsize=12,
    )
    if args.title:
        fig.suptitle(args.title, fontsize=17)

    boxplot = make_rbmpki_boxplot(indexed, groups)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    boxplot_output = args.output.with_name(f"{args.output.name}_rbmpki_boxplot")
    for file_format in args.formats:
        destination = args.output.with_suffix(f".{file_format}")
        boxplot_destination = boxplot_output.with_suffix(f".{file_format}")
        options = {"dpi": args.dpi} if file_format == "png" else {}
        fig.savefig(destination, bbox_inches="tight", **options)
        boxplot.savefig(boxplot_destination, bbox_inches="tight", **options)
        print(f"Wrote {destination.resolve()}")
        print(f"Wrote {boxplot_destination.resolve()}")
    groups_path = args.output.with_name(f"{args.output.name}_rbmpki_groups.txt")
    write_rbmpki_groups(groups_path, rbmpki, groups, indexed)
    print(f"Wrote {groups_path.resolve()}")
    numeric_path = args.output.with_name(f"{args.output.name}_numeric_results.md")
    write_numeric_results(numeric_path, workloads, rbmpki, groups, indexed)
    print(f"Wrote {numeric_path.resolve()}")
    plt.close(fig)
    plt.close(boxplot)


if __name__ == "__main__":
    main()
