"""DDRAM: Reproducible bandwidth/latency sweeps with one- and two-row working sets."""

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from tests.latency_throughput.utils.runner import run_sweep
from tests.latency_throughput.utils.spec import resolve_spec

pytestmark = [pytest.mark.ddram_p, pytest.mark.latency_throughput_fast]

OUTPUT = Path(__file__).parent / "plots" / "ddram_comparison"
NOP_COUNTERS = (160, 96, 64, 48, 32, 24, 20, 16, 12, 8, 4, 2, 1)
WARMUP_CYCLES = 5000
READ_SAMPLES = 4096
LATENCY_BUDGET_NS = 60
MODELS = {
    "DDR5": ("DDR5", "FRFCFSRowHit", "Auto"),
    "DDRAM-P / AlwaysA": ("DDRAM_P", "FRFCFSRowHit", "AlwaysA"),
    "DDRAM-P / TwoView": ("DDRAM_P", "FRFCFSViewAware", "TwoView"),
}
COLORS = ("#2563eb", "#d97706", "#168366")


# DDRAM: Keep device capacity, queues, seed, timings and workload identical across models.
def configuration(label, rows):
    dram_class, scheduler, view_selection = MODELS[label]
    return {
        "name": f"{label}, {rows} row(s)/bank",
        "dram_class": dram_class,
        "org_preset": "DDR5_16Gb_x8",
        "timing_preset": "DDR5_4800AN",
        "controller_class": "GenericDDR",
        "scheduler_class": scheduler,
        "controller_kwargs": {"view_selection": view_selection},
        "frontend_clock_ratio": 1,
        "stream_cls": 1,
        "traffic_rows": rows,
        "traffic_bank_counts": {"Rank": 1, "BankGroup": 4, "Bank": 1},
        "nop_counters": NOP_COUNTERS,
    }


# DDRAM: Preserve offered-load ordering; report mean accepted-read latency and achieved bandwidth.
def measurements(raw, spec):
    result = []
    for nop in NOP_COUNTERS:
        stats = raw[(nop, 100)]
        controller = stats["memory_system"]["controller"]
        frontend = stats["frontend"]
        assert frontend["stream_latency_samples_completed"] == READ_SAMPLES
        result.append({
            "nop": nop,
            "offered_gbps": spec.bytes_per_req / (nop * spec.time_unit_ns),
            "bandwidth_gbps": controller["total_throughput_MBps"] / 1000,
            "latency_ns": frontend["avg_stream_latency"] * spec.time_unit_ns,
            "row_hits": controller["read_row_hits"],
            "row_misses": controller["read_row_misses"],
            "row_conflicts": controller["read_row_conflicts"],
            "reads_served": controller["num_read_reqs_served"],
        })
    return result


# DDRAM: Run each point through the production simulation/frontend, caching only within this test run.
@pytest.fixture(scope="module")
def sweep():
    result = {}
    for rows in (1, 2):
        for label in MODELS:
            cfg = configuration(label, rows)
            raw = run_sweep(
                cfg, read_ratios=(100,), num_probe_requests=0, max_workers=1,
                refresh_enabled=False, frontend_clock_ratio=1,
                warmup_cycles=WARMUP_CYCLES,
                latency_measure_mode="stream-only", latency_sample_count=READ_SAMPLES,
            )
            spec = resolve_spec(cfg)
            result[(rows, label)] = measurements(raw, spec)
    export_results(result, spec)
    return result, spec


# DDRAM: Save raw metrics and a shared-axis 2x3 comparison; dashed curves repeat the DDR5 baseline.
def export_results(result, spec):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    records = [{"rows_per_bank": rows, "model": label, **point}
               for (rows, label), points in result.items() for point in points]
    with (OUTPUT / "measurements.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    metadata = {
        "timing_preset": "DDR5_4800AN", "org_preset": "DDR5_16Gb_x8",
        "models": MODELS, "read_percentage": 100, "row_policy": "Open",
        "refresh": False, "active_banks": 4, "rows_per_bank": [1, 2],
        "requests_per_row_visit": 1, "warmup_memory_cycles": WARMUP_CYCLES,
        "read_samples_per_point": READ_SAMPLES, "seed": 12345,
        "time_unit_ns": spec.time_unit_ns, "bytes_per_request": spec.bytes_per_req,
        "raw_channel_limit_gbps": spec.max_theoretical_throughput,
        "latency_budget_ns": LATENCY_BUDGET_NS,
        "latency": "mean accepted-read-to-completion latency; source backpressure excluded",
        "points": records,
    }
    (OUTPUT / "measurements.json").write_text(json.dumps(metadata, indent=2) + "\n")
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharex=True, sharey="row")
    for row_index, rows in enumerate((1, 2)):
        baseline = result[(rows, "DDR5")]
        for column, (label, color) in enumerate(zip(MODELS, COLORS)):
            ax = axes[row_index, column]
            points = result[(rows, label)]
            if column:
                ax.plot([p["bandwidth_gbps"] for p in baseline],
                        [p["latency_ns"] for p in baseline], "--", color="#94a3b8",
                        linewidth=1.5, label="DDR5 baseline")
            ax.plot([p["bandwidth_gbps"] for p in points],
                    [p["latency_ns"] for p in points], "o-", color=color,
                    markersize=4, linewidth=2, label=label)
            peak = max(p["bandwidth_gbps"] for p in points)
            light = points[0]["latency_ns"]
            ax.text(0.04, 0.96, f"Peak: {peak:.2f} GB/s\nLight load: {light:.1f} ns",
                    transform=ax.transAxes, va="top", fontsize=10,
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9})
            ax.set_xlim(0, spec.max_theoretical_throughput * 1.05)
            ax.set_ylim(bottom=0)
            if rows == 2:
                ax.axhline(LATENCY_BUDGET_NS, color="#64748b", linestyle=":", alpha=0.5)
            ax.grid(alpha=0.2)
            ax.spines[["top", "right"]].set_visible(False)
            if row_index == 0:
                scheduler = MODELS[label][1]
                ax.set_title(f"{label}\n{scheduler}", fontsize=12, fontweight="bold")
            if row_index == 1:
                ax.set_xlabel("Achieved read bandwidth (GB/s)")
            if column == 0:
                workload = "One-row control" if rows == 1 else "Two alternating rows"
                ax.set_ylabel(f"{workload}\nMean read latency (ns)")
            if column:
                ax.legend(loc="lower right", fontsize=8)
    fig.suptitle("DDRAM-P bandwidth–latency validation", fontsize=18, fontweight="bold")
    fig.text(0.5, 0.925,
             "DDR5-4800AN · 4 active banks · 100% reads · Open-page · No refresh",
             ha="center", color="#475569")
    fig.text(0.5, 0.015,
             "Identical deterministic traffic and queues; 4,096 sampled reads/point after warmup. "
             "Dotted line: 60 ns budget. TwoView includes device and scheduler changes.",
             ha="center", fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, 0.04, 1, 0.90))
    fig.savefig(OUTPUT / "comparison.png", dpi=180)
    fig.savefig(OUTPUT / "comparison.svg")
    plt.close(fig)
    print(f"\nDDRAM comparison figure: {OUTPUT / 'comparison.png'}")
    for rows in (1, 2):
        for label in MODELS:
            points = result[(rows, label)]
            print(f"  {rows} row(s), {label}: peak "
                  f"{max(p['bandwidth_gbps'] for p in points):.3f} GB/s; "
                  f"light-load latency {points[0]['latency_ns']:.3f} ns")


# DDRAM: The fixed-A path must reproduce DDR5 at every offered load and working-set size.
def test_always_a_matches_ddr5(sweep):
    result, _ = sweep
    for rows in (1, 2):
        assert result[(rows, "DDR5")] == result[(rows, "DDRAM-P / AlwaysA")]


# DDRAM: With one resident row, a second sensing path should provide no steady-state advantage.
def test_single_row_control_matches(sweep):
    result, _ = sweep
    assert result[(1, "DDR5")] == result[(1, "DDRAM-P / TwoView")]


# DDRAM: Two resident rows remove recurring conflicts and reduce latency for this deliberately local workload.
def test_two_row_working_set_benefits(sweep):
    result, _ = sweep
    baseline = result[(2, "DDR5")]
    dual = result[(2, "DDRAM-P / TwoView")]
    assert baseline[0]["row_conflicts"] > 0
    assert all(point["row_conflicts"] == 0 for point in dual)
    assert all(point["row_hits"] / point["reads_served"] > 0.99 for point in dual)
    assert dual[0]["latency_ns"] < baseline[0]["latency_ns"]
    # DDRAM: Both can saturate the shared bus; compare useful bandwidth at a stated latency budget.
    baseline_budget = max(p["bandwidth_gbps"] for p in baseline
                          if p["latency_ns"] <= LATENCY_BUDGET_NS)
    dual_budget = max(p["bandwidth_gbps"] for p in dual
                      if p["latency_ns"] <= LATENCY_BUDGET_NS)
    assert dual_budget > baseline_budget
    assert max(p["bandwidth_gbps"] for p in dual) == pytest.approx(
        max(p["bandwidth_gbps"] for p in baseline), rel=0.01
    )


# DDRAM: Additional views share the data bus and cannot exceed its modeled payload rate.
def test_channel_bandwidth_bound(sweep):
    result, spec = sweep
    for points in result.values():
        assert all(0 < point["bandwidth_gbps"] <= spec.max_theoretical_throughput * 1.01
                   and point["latency_ns"] > 0 for point in points)
