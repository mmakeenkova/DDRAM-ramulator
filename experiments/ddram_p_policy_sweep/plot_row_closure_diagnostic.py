"""Plot the quick row-closure control against managed NACK refresh."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tempfile
import tomllib
from pathlib import Path


EXPERIMENT_DIR = Path(__file__).resolve().parent
DEFAULT_DISABLED_DIR = (
    EXPERIMENT_DIR / "output" / "all" / "mordor_10m_policy_quick_disabled"
)
DEFAULT_NACK_DIR = EXPERIMENT_DIR / "output" / "mordor_10m_policy_quick_nack"
DEFAULT_PRESERVE_DIR = (
    EXPERIMENT_DIR / "output" / "all" / "mordor_10m_policy_quick_nack_preserve"
)
DEFAULT_OUTPUT = EXPERIMENT_DIR / "output" / "row_closure_refresh_quick_diagnostic"

_CACHE = Path(tempfile.gettempdir()) / f"ramulator-matplotlib-{os.getuid()}"
_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_CACHE))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


with (EXPERIMENT_DIR.parent / "figure_palette.toml").open("rb") as palette_file:
    _PALETTE_DATA = tomllib.load(palette_file)
COLORS = _PALETTE_DATA["colors"]
SEMANTIC_COLORS = {
    name: COLORS[color_name]
    for name, color_name in _PALETTE_DATA["semantics"].items()
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disabled-dir", type=Path, default=DEFAULT_DISABLED_DIR)
    parser.add_argument("--nack-dir", type=Path, default=DEFAULT_NACK_DIR)
    parser.add_argument("--preserve-dir", type=Path, default=DEFAULT_PRESERVE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--formats", nargs="+", choices=("png", "pdf", "svg"), default=("png", "pdf")
    )
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument(
        "--title",
        default="DDRAM-P · NACK refresh row-closure diagnostic · 10M instructions",
    )
    return parser.parse_args()


def read_measurements(result_dir: Path) -> dict[tuple[str, str], dict[str, str]]:
    path = result_dir / "measurements.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Measurement file does not exist: {path}")
    with path.open(newline="") as input_file:
        rows = list(csv.DictReader(input_file))
    if not rows:
        raise ValueError(f"Measurement file is empty: {path}")
    return {(row["workload"], row["policy"]): row for row in rows}


def workload_order(result_dir: Path, available: set[str]) -> list[str]:
    metadata_path = result_dir / "results.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text())
        source = metadata.get("requested_workloads", metadata.get("workloads", []))
        ordered = [name for name in source if name in available]
        if set(ordered) == available:
            return ordered
    return sorted(available)


def geometric_mean(values: list[float]) -> float:
    if any(value <= 0 for value in values):
        raise ValueError(f"Geometric mean requires positive values: {values}")
    return math.exp(sum(math.log(value) for value in values) / len(values))


def cycles(rows: dict[tuple[str, str], dict[str, str]], workload: str, policy: str) -> float:
    return float(rows[(workload, policy)]["cycles"])


def row_rate(row: dict[str, str], outcome: str) -> float:
    total = sum(float(row[name]) for name in ("row_hits", "row_misses", "row_conflicts"))
    return 100.0 * float(row[outcome]) / total if total else 0.0


def style_axis(ax, ylabel: str) -> None:
    ax.set_ylabel(ylabel, fontsize=14)
    ax.tick_params(axis="y", labelsize=11)
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


def grouped_bars(ax, x: np.ndarray, series, width: float) -> None:
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


def main() -> None:
    args = parse_args()
    disabled = read_measurements(args.disabled_dir)
    nack = read_measurements(args.nack_dir)
    preserve = read_measurements(args.preserve_dir)
    disabled_workloads = {workload for workload, _ in disabled}
    nack_workloads = {workload for workload, _ in nack}
    preserve_workloads = {workload for workload, _ in preserve}
    if disabled_workloads != nack_workloads or disabled_workloads != preserve_workloads:
        raise ValueError(
            "Disabled, NACK, and preserving-NACK workload sets differ: "
            f"only disabled={sorted(disabled_workloads - nack_workloads)}, "
            f"only NACK={sorted(nack_workloads - disabled_workloads)}, "
            f"only preserve={sorted(preserve_workloads - disabled_workloads)}"
        )
    workloads = workload_order(args.disabled_dir, disabled_workloads)
    required = ("both_views", "auto_precharge")
    for workload in workloads:
        for policy in required:
            if any(
                (workload, policy) not in rows
                for rows in (disabled, nack, preserve)
            ):
                raise ValueError(f"Missing {policy} measurement for {workload}")

    overhead = {}
    for refresh_name, refresh_rows in (("Closes rows", nack), ("Preserves rows", preserve)):
        for policy in required:
            ratios = [
                cycles(refresh_rows, workload, policy) / cycles(disabled, workload, policy)
                for workload in workloads
            ]
            overhead[(refresh_name, policy)] = [100.0 * (ratio - 1.0) for ratio in ratios]
            overhead[(refresh_name, policy)].append(
                100.0 * (geometric_mean(ratios) - 1.0)
            )

    outcomes = (
        ("Row hits", "row_hits", SEMANTIC_COLORS["oracle"]),
        ("Row conflicts", "row_conflicts", SEMANTIC_COLORS["queue_aware_policy"]),
        ("Row misses", "row_misses", SEMANTIC_COLORS["nack"]),
    )
    outcome_changes: dict[tuple[str, str], list[float]] = {}
    for refresh_name, refresh_rows in (("Closes", nack), ("Preserves", preserve)):
        for label, field, _ in outcomes:
            values = [
                row_rate(refresh_rows[(workload, "both_views")], field)
                - row_rate(disabled[(workload, "both_views")], field)
                for workload in workloads
            ]
            outcome_changes[(refresh_name, label)] = values + [float(np.mean(values))]

    labels = [workload.removesuffix(".trace") for workload in workloads] + ["Aggregate*"]
    x = np.arange(len(labels), dtype=float)
    aggregate_index = len(workloads)
    figure_width = max(15.0, 1.15 * len(labels))
    fig, axes = plt.subplots(
        2,
        1,
        figsize=(figure_width, 10.0),
        sharex=True,
        constrained_layout=True,
    )

    for ax in axes:
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
            linewidth=1.2,
            zorder=4,
        )
        ax.set_xlim(-0.55, len(labels) - 0.45)

    grouped_bars(
        axes[0],
        x,
        (
            (
                "Open · closes rows",
                overhead[("Closes rows", "both_views")],
                SEMANTIC_COLORS["both_views_policy"],
            ),
            (
                "Open · preserves rows",
                overhead[("Preserves rows", "both_views")],
                COLORS["dark_green"],
            ),
            (
                "Auto-P B · closes rows",
                overhead[("Closes rows", "auto_precharge")],
                SEMANTIC_COLORS["auto_precharge_policy"],
            ),
            (
                "Auto-P B · preserves rows",
                overhead[("Preserves rows", "auto_precharge")],
                COLORS["apricot"],
            ),
        ),
        width=0.19,
    )
    style_axis(axes[0], "Refresh cycle overhead [%]\n(NACK vs. disabled)")
    axes[0].legend(
        title="Row policy",
        loc="best",
        frameon=True,
        facecolor="white",
        edgecolor="#1a1a1a",
        fontsize=11,
        title_fontsize=12,
    )
    grouped_bars(
        axes[1],
        x,
        (
            ("Hits · closes", outcome_changes[("Closes", "Row hits")], COLORS["blue"]),
            ("Hits · preserves", outcome_changes[("Preserves", "Row hits")], COLORS["periwinkle"]),
            ("Conflicts · closes", outcome_changes[("Closes", "Row conflicts")], COLORS["violet"]),
            ("Conflicts · preserves", outcome_changes[("Preserves", "Row conflicts")], COLORS["mauve"]),
            ("Misses · closes", outcome_changes[("Closes", "Row misses")], COLORS["orange"]),
            ("Misses · preserves", outcome_changes[("Preserves", "Row misses")], COLORS["apricot"]),
        ),
        width=0.13,
    )
    style_axis(axes[1], "Row-outcome rate change [percentage points]\n(open-page NACK vs. disabled)")
    axes[1].legend(
        title="Row outcome",
        loc="best",
        frameon=True,
        facecolor="white",
        edgecolor="#1a1a1a",
        fontsize=10,
        title_fontsize=12,
        ncol=2,
    )
    axes[1].set_xticks(x, labels, rotation=28, ha="right", fontsize=11)
    axes[1].text(
        0.99,
        0.03,
        "*Top: cycle-ratio geomean; bottom: arithmetic mean",
        transform=axes[1].transAxes,
        ha="right",
        fontsize=9,
        color=COLORS["charcoal"],
    )

    if args.title:
        fig.suptitle(args.title, fontsize=18)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for output_format in args.formats:
        path = args.output.with_suffix(f".{output_format}")
        save_args = {"bbox_inches": "tight"}
        if output_format == "png":
            save_args["dpi"] = args.dpi
        fig.savefig(path, **save_args)
        print(f"Wrote {path.resolve()}")
    plt.close(fig)


if __name__ == "__main__":
    main()
