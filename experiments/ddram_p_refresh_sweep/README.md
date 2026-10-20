# DDRAM-P MORDOR refresh sweep

This experiment measures completion-cycle overhead on MORDOR CPU traces without
recording visualizer traces. It runs four matched configurations:

| Configuration | Demand views | Internal-refresh views | Refresh |
| --- | ---: | ---: | --- |
| `one_view_no_refresh` | A only | A only | disabled |
| `two_view_no_refresh` | A/B | A/B | disabled |
| `one_view_oracle` | A only | A only | DRAM-managed Oracle |
| `two_view_oracle` | A/B | A/B | DRAM-managed Oracle |

Restricting both demand and refresh is important: `AlwaysA` alone is not a true
one-view baseline because the autonomous refresh engine would otherwise still
use the closed B sensing path.

From the repository root, run the default four-workload smoke study:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_refresh_sweep/run.py
```

### Named configurations

Longer or frequently revisited studies live as JSON files under `configs/`.
List and select them without editing the runner:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_refresh_sweep/run.py --list-configs

PYTHONPATH=python .venv/bin/python experiments/ddram_p_refresh_sweep/run.py \
  --config mordor_10m_oracle

PYTHONPATH=python .venv/bin/python experiments/ddram_p_refresh_sweep/run.py \
  --config mordor_10m_nack
```

Each named configuration gets its own output directory, for example
`output/mordor_10m_oracle/`. Its full source configuration is copied into
`results.json`, alongside the effective runtime parameters and measurements.
The runner refuses to replace completed results unless `--overwrite` is given.
Any command-line option can override the selected file for a deliberate variant;
use a distinct `--output-dir` to retain both runs.

### Complete 55-trace corpus

`run_all.py` discovers every trace in the MORDOR directory and runs each one
as an independently resumable unit. Select configurations explicitly:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_refresh_sweep/run_all.py \
  --configs mordor_10m_oracle mordor_10m_nack
```

Before launching the complete campaign, inspect the selection with:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_refresh_sweep/run_all.py \
  --configs mordor_10m_oracle mordor_10m_nack --dry-run
```

Results are stored per workload below `output/all/<config>/runs/`, with logs
under `output/all/<config>/logs/`. Rerunning the same command skips completed
and configuration-matching workloads, making interrupted studies resumable.
Bounded trace copies are shared across configurations under `output/all/inputs/`
to avoid duplicating the large MORDOR prefixes.
The script also creates aggregate `measurements.csv`, `summary.csv`, and
`results.json` files directly under `output/all/<config>/`, so those directories
can be passed to `plot.py`. Use `--jobs N` for concurrent trace processes where
the host permits it, `--traces ...` or `--limit N` for a subset, and
`--overwrite` only when intentionally replacing completed per-trace results.
The full 10M Oracle-plus-NACK campaign contains 440 simulations and can take
several hours when run serially, so use `--dry-run` and a small `--limit` first.

The defaults retire one million instructions and copy at most 250,000 records
from each source trace. This bounds SimpleO3's input memory use without changing
the original MORDOR files. Override the subset or run jobs in parallel with:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_refresh_sweep/run.py \
  --workloads 429.mcf 538.imagick tpcc64 ycsb_aserver stream_10.trace \
  --instructions 5000000 --trace-lines 1000000 --workers 4
```

By default, Oracle mode uses the DDR5-4800 preset's `nREFI` and `nRFCsb`.
Explicit stress-study timings and the NACK interface are also supported:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_refresh_sweep/run.py \
  --refresh-mode Nack --refresh-interval 256 --refresh-duration 32
```

Outputs under a parameter-named directory such as
`output/oracle.interval-nREFI.duration-nRFCsb/` are ignored by Git:

- `measurements.csv`: CPU completion cycles, memory cycles, memory-stall cycles, row outcomes, refreshes,
  NACKs, latency, throughput, and host runtime for every run.
- `summary.csv`: refresh overhead and two-view speedup per workload.
- `results.json`: complete metadata and both result tables.
- `inputs/`: bounded local trace prefixes used by the simulations.

The runner suppresses Ramulator's very verbose per-access debug stream. Pass
`--verbose-ramulator` when those diagnostics are needed.

The primary end-to-end metric is `cycles_recorded_core_0`, the SimpleO3 CPU
completion cycle. `one_view_refresh_overhead_pct` and
`two_view_refresh_overhead_pct` compare refresh-on with the corresponding
refresh-off control. `two_view_with_refresh_speedup` compares the one-view and
two-view refresh-on runs.

## Plotting Oracle and NACK results

After running both interfaces, generate a paper-style grouped-bar comparison:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_refresh_sweep/plot.py
```

Matplotlib is listed in `requirements-dev.txt`; install the development
dependencies first if it is not already available in the virtual environment.

By default this reads the `nREFI`/`nRFCsb` Oracle and NACK result directories
and writes both PNG and vector PDF versions:

```text
output/ddram_p_refresh_comparison.png
output/ddram_p_refresh_comparison.pdf
```

The upper panel reports the completion-cycle reduction from using two views,
including the no-refresh control. The lower panel reports refresh-on overhead
relative to the matching refresh-off configuration. Negative overhead is shown
below the red zero line rather than clipped. The figure width scales with the
number of workloads so full-corpus labels remain readable.

The plotting command also writes `<output>_rbmpki_boxplot.{png,pdf}`,
`<output>_rbmpki_groups.txt`, and `<output>_numeric_results.md`. RBMPKI is computed from the one-view/no-refresh
baseline as `(row_misses + row_conflicts) * 1000 / retired instructions`.
Workloads sorted by this value are divided into equal-count low, medium, and
high terciles. The box plot shows the four refresh-overhead distributions for
each tercile, marking arithmetic means with diamonds and overheads derived from
geometric-mean refresh/no-refresh cycle ratios with X markers. The text file
records the definition, group ranges, members, RBMPKI values, and mean
overheads. Use `--oracle-dir`, `--nack-dir`, `--output`, and `--formats` to plot
other sweeps.

The Markdown numeric report records the raw execution-cycle count for every
configuration, every per-workload reduction or overhead value used by the
figures, and all-workload arithmetic-mean and cycle-ratio-geomean summaries.

All series use the shared contrasting palette and semantic assignments in
[`../figure_palette.toml`](../figure_palette.toml); new experiment figures
should use the same mapping.

For example, plot the named 10-million-instruction pair without replacing the
1-million-instruction figure:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_refresh_sweep/plot.py \
  --oracle-dir experiments/ddram_p_refresh_sweep/output/mordor_10m_oracle \
  --nack-dir experiments/ddram_p_refresh_sweep/output/mordor_10m_nack \
  --output experiments/ddram_p_refresh_sweep/output/mordor_10m_comparison \
  --title "DDRAM-P · 10 million instructions"
```
