"""Plot periodic versus DRAM-managed refresh overhead by baseline RBMPKI class."""

from __future__ import annotations

import argparse
import csv
import math
import os
from pathlib import Path
import tempfile
import tomllib


EXPERIMENT_DIR = Path(__file__).resolve().parent
_MPL_CACHE = Path(tempfile.gettempdir()) / f"ramulator-matplotlib-{os.getuid()}"
_MPL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL_CACHE))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np


with (EXPERIMENT_DIR.parent / "figure_palette.toml").open("rb") as palette_file:
    _PALETTE = tomllib.load(palette_file)
COLORS = _PALETTE["colors"]
SEMANTICS = {
    name: COLORS[color_name]
    for name, color_name in _PALETTE["semantics"].items()
}
MECHANISMS = (
    ("periodic", "Periodic REFab", SEMANTICS["periodic_refresh"]),
    ("oracle", "Oracle", SEMANTICS["oracle"]),
    ("nack", "NACK", SEMANTICS["nack"]),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--formats", nargs="+", choices=("png", "pdf", "svg"), default=("png", "pdf"))
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--title", default="DDRAM-P refresh overhead by no-refresh RBMPKI class")
    return parser.parse_args()


def read_summary(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Result file does not exist: {path}")
    rows = []
    with path.open(newline="") as input_file:
        for raw in csv.DictReader(input_file):
            rows.append({
                "workload": raw["workload"],
                "view_count": int(raw["view_count"]),
                "refresh_interface": raw["refresh_interface"],
                "baseline_cycles": int(raw["baseline_cycles"]),
                "cycles": int(raw["cycles"]),
                "overhead": float(raw["refresh_cycle_overhead_pct"]),
                "rbmpki": float(raw["baseline_rbmpki"]),
                "row_hit_rate": float(raw["row_hit_rate_pct"]),
                "maintenance": int(raw["maintenance_requests_served"]),
                "internal_refreshes": int(raw["internal_refreshes"]),
                "act_nacks": int(raw["act_nacks"]),
            })
    if not rows:
        raise ValueError(f"Result file is empty: {path}")
    return rows


def group_workloads(rows: list[dict]) -> list[tuple[str, list[str]]]:
    rbmpki = {}
    for row in rows:
        rbmpki[row["workload"]] = row["rbmpki"]
    ordered = sorted(rbmpki, key=lambda workload: (rbmpki[workload], workload))
    if len(ordered) < 3:
        raise ValueError(
            "RBMPKI tercile plots require at least three workloads; "
            f"found {len(ordered)}"
        )
    names = ("Low RBMPKI", "Medium RBMPKI", "High RBMPKI")
    return [
        (name, [ordered[int(index)] for index in indices])
        for name, indices in zip(names, np.array_split(np.arange(len(ordered)), 3))
    ]


def ratio_geomean(overheads: list[float]) -> float:
    ratios = [1.0 + value / 100.0 for value in overheads]
    if any(value <= 0 for value in ratios):
        raise ValueError(f"Cannot calculate a cycle-ratio geomean from {overheads}")
    return 100.0 * (math.exp(sum(math.log(value) for value in ratios) / len(ratios)) - 1.0)


def values_for(
    rows: list[dict], workloads: list[str], view_count: int, mechanism: str,
) -> list[float]:
    indexed = {
        (row["workload"], row["view_count"], row["refresh_interface"]): row["overhead"]
        for row in rows
    }
    return [indexed[(workload, view_count, mechanism)] for workload in workloads]


def draw_panel(ax, rows: list[dict], groups, view_count: int) -> None:
    group_centers = np.arange(len(groups), dtype=float)
    offsets = (-0.25, 0.0, 0.25)
    width = 0.20
    for offset, (mechanism, _, color) in zip(offsets, MECHANISMS):
        data = [values_for(rows, workloads, view_count, mechanism) for _, workloads in groups]
        positions = group_centers + offset
        box = ax.boxplot(
            data,
            positions=positions,
            widths=width,
            patch_artist=True,
            showmeans=True,
            meanprops={
                "marker": "D", "markerfacecolor": "white",
                "markeredgecolor": "#252525", "markersize": 5,
            },
            medianprops={"color": SEMANTICS["median"], "linewidth": 1.7},
            boxprops={"edgecolor": "#252525", "linewidth": 1.0},
            whiskerprops={"color": "#252525", "linewidth": 1.0},
            capprops={"color": "#252525", "linewidth": 1.0},
            flierprops={
                "marker": "o", "markerfacecolor": color,
                "markeredgecolor": "#555555", "markersize": 3.5, "alpha": 0.8,
            },
        )
        for patch in box["boxes"]:
            patch.set_facecolor(color)
        for position, values in zip(positions, data):
            ax.scatter(
                position + 0.055,
                ratio_geomean(values),
                marker="x",
                s=34,
                linewidth=1.4,
                color=COLORS["charcoal"],
                zorder=5,
            )

    labels = [f"{name}\n(n={len(workloads)})" for name, workloads in groups]
    ax.set_xticks(group_centers, labels)
    ax.set_xlim(-0.48, len(groups) - 0.52)
    ax.set_ylabel("Refresh cycle overhead [%]")
    ax.set_title(f"{view_count} view{'s' if view_count == 2 else ''}", loc="left", fontsize=14)
    ax.axhline(0, color=SEMANTICS["zero_line"], linestyle="--", linewidth=1.2, zorder=1)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, zorder=0)
    ax.margins(x=0)


def write_groups(path: Path, rows: list[dict], groups) -> None:
    rbmpki = {row["workload"]: row["rbmpki"] for row in rows}
    lines = [
        "RBMPKI groups",
        "=============",
        "",
        "RBMPKI = 1000 * (row misses + row conflicts) / instructions,",
        "measured in the one-view/no-refresh baseline. Groups are equal-count terciles.",
        "",
    ]
    for name, workloads in groups:
        lines.append(f"{name} (n={len(workloads)})")
        for workload in workloads:
            lines.append(f"  {workload:<24} {rbmpki[workload]:.6f}")
        lines.append("")
    path.write_text("\n".join(lines))


def write_report(path: Path, rows: list[dict], groups) -> None:
    indexed = {
        (row["workload"], row["view_count"], row["refresh_interface"]): row
        for row in rows
    }
    lines = [
        "# DDRAM-P periodic-refresh comparison", "",
        "Refresh overhead is `100 × (refresh cycles / matching no-refresh cycles − 1)`.",
        "Arithmetic means summarize percentage points; GMean is computed over cycle ratios.",
        "",
    ]
    for group_name, workloads in groups:
        lines.extend((f"## {group_name} (n={len(workloads)})", ""))
        for view_count in (1, 2):
            lines.extend((f"### {view_count} view{'s' if view_count == 2 else ''}", ""))
            lines.append("| Workload | Refresh | No-refresh cycles | Refresh cycles | Overhead | Row-hit rate | REFab served | Internal refreshes | ACT NACKs |")
            lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
            for workload in workloads:
                for mechanism, label, _ in MECHANISMS:
                    row = indexed[(workload, view_count, mechanism)]
                    lines.append(
                        f"| {workload} | {label} | {row['baseline_cycles']:,} | {row['cycles']:,} | "
                        f"{row['overhead']:+.4f}% | {row['row_hit_rate']:.4f}% | {row['maintenance']:,} | "
                        f"{row['internal_refreshes']:,} | {row['act_nacks']:,} |"
                    )
            lines.extend(("", "| Refresh | Mean overhead | Cycle-ratio GMean overhead |", "|---|---:|---:|"))
            for mechanism, label, _ in MECHANISMS:
                values = values_for(rows, workloads, view_count, mechanism)
                lines.append(f"| {label} | {np.mean(values):+.4f}% | {ratio_geomean(values):+.4f}% |")
            lines.append("")

    all_workloads = [workload for _, workloads in groups for workload in workloads]
    lines.extend(("## All workloads", "", "| Views | Refresh | Mean overhead | Cycle-ratio GMean overhead |", "|---:|---|---:|---:|"))
    for view_count in (1, 2):
        for mechanism, label, _ in MECHANISMS:
            values = values_for(rows, all_workloads, view_count, mechanism)
            lines.append(f"| {view_count} | {label} | {np.mean(values):+.4f}% | {ratio_geomean(values):+.4f}% |")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    args = parse_args()
    rows = read_summary(args.result_dir / "summary.csv")
    groups = group_workloads(rows)
    output = args.output or args.result_dir / "rbmpki_refresh_comparison"
    output.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 1, figsize=(12.5, 9.0), sharex=True, constrained_layout=True)
    draw_panel(axes[0], rows, groups, 1)
    draw_panel(axes[1], rows, groups, 2)
    axes[0].tick_params(axis="x", labelbottom=False)
    handles = [Patch(facecolor=color, edgecolor="#252525", label=label) for _, label, color in MECHANISMS]
    handles.extend((
        Line2D([], [], marker="D", linestyle="None", markerfacecolor="white", markeredgecolor="#252525", label="Arithmetic mean"),
        Line2D([], [], marker="x", linestyle="None", color=COLORS["charcoal"], label="Cycle-ratio GMean"),
    ))
    axes[0].legend(handles=handles, loc="best", ncol=2, frameon=True)
    if args.title:
        fig.suptitle(args.title, fontsize=18)
    for extension in args.formats:
        fig.savefig(output.with_suffix(f".{extension}"), dpi=args.dpi, bbox_inches="tight")
    plt.close(fig)

    write_groups(output.with_name(f"{output.name}_groups.txt"), rows, groups)
    write_report(output.with_name(f"{output.name}_numeric_results.md"), rows, groups)
    print(f"Figure: {output.with_suffix('.png').resolve()}")
    print(f"Groups: {output.with_name(f'{output.name}_groups.txt').resolve()}")
    print(f"Numbers: {output.with_name(f'{output.name}_numeric_results.md').resolve()}")


if __name__ == "__main__":
    main()
