# DDRAM-P view-policy sweep

This experiment compares four controller policies on identical single-core
MORDOR trace prefixes:

| Label | View selection | Row policy | Refresh views |
| --- | --- | --- | ---: |
| `one_view` | `AlwaysA` | `Open` | 1 |
| `both_views` | `TwoView` | `Open` | 2 |
| `auto_precharge` | `TwoView` | `DDRAMViewAutoPrecharge` on B | 2 |
| `queue_aware` | `QueueAware` | `Open` | 2 |

Auto-precharge preserves B when another buffered request can hit its row and
otherwise issues `RDA_B`/`WRA_B`. Queue-aware uses queue reuse to choose a
victim view but retains open-page behavior. They are separate experimental
points, not combined.

Each simulation supplies one trace to `SimpleO3`, so it models one core. The
`--workers` and `--jobs` switches only parallelize independent simulations on
the host.

## Four-workload 10M run

From the repository root:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_policy_sweep/run.py \
  --config mordor_10m_oracle
```

Use `mordor_10m_nack` for the NACK refresh interface. Results go to
`output/<config-name>/` unless `--output-dir` is specified.

### Ten-trace quick overview

The NACK quick preset runs the five workloads used by the earlier short study
(`429.mcf`, `538.imagick`, `tpcc64`, `ycsb_aserver`, and `stream_10.trace`)
plus `401.bzip2`, `403.gcc`, `470.lbm`, `520.omnetpp`, and `557.xz`:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_policy_sweep/run.py \
  --config mordor_10m_quick_nack
```

This performs 40 simulations: ten single-core workloads times four policies.
Its results are written to `output/mordor_10m_policy_quick_nack/`.

Plot the quick overview with:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_policy_sweep/plot.py \
  --result-dir experiments/ddram_p_policy_sweep/output/mordor_10m_policy_quick_nack \
  --output experiments/ddram_p_policy_sweep/output/mordor_10m_policy_quick_nack_comparison \
  --title "DDRAM-P policies · NACK refresh · 10-trace quick overview"
```

## Complete corpus with resume

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_policy_sweep/run_all.py \
  --configs mordor_10m_oracle mordor_10m_nack \
  --jobs 1
```

Each workload is stored below `output/all/<config-name>/runs/`. Repeating the
command skips configuration-matching completed workloads and rebuilds the
aggregate `measurements.csv`, `summary.csv`, and `results.json`. Use
`--dry-run`, `--limit N`, or `--traces ...` to inspect or restrict the corpus.
Avoid `--overwrite` when resuming.

## Plotting

For the four-workload Oracle run:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_policy_sweep/plot.py \
  --result-dir experiments/ddram_p_policy_sweep/output/mordor_10m_policy_oracle \
  --output experiments/ddram_p_policy_sweep/output/mordor_10m_policy_oracle_comparison \
  --title "DDRAM-P policies · 10 million instructions"
```

For the all-trace run, point `--result-dir` at
`output/all/mordor_10m_policy_oracle` (or the NACK directory). The left panel
shows completion-cycle reduction relative to `one_view`; the right panel shows
row-hit rate. The final `GMean` group is separated by a dashed line and gray
background. Its cycle-reduction value is derived by geometrically averaging
each workload's normalized cycles and converting the result back to a percent
reduction. The row-hit aggregate is the geometric mean of workload row-hit
rates. PNG and vector PDF are produced by default.

The same command also writes `<output>_rbmpki_boxplot.{png,pdf}` and
`<output>_rbmpki_groups.txt`, plus `<output>_numeric_results.md`. Workloads are classified into equal-count low,
medium, and high terciles using RBMPKI from the one-view run under the selected
refresh mode. The box plot shows each policy's per-workload cycle reduction
relative to one view; diamonds mark arithmetic means. The text file records the
definition, ranges, membership, RBMPKI values, and aggregate reductions. Diamonds
mark arithmetic means and X markers show reductions derived from geometric-mean
normalized cycle counts. The Markdown
report records every plotted per-workload value, raw execution cycles, and both
the all-workload arithmetic-mean and cycle-ratio-geomean reductions.

The policy colors come from the shared semantic palette in
[`../figure_palette.toml`](../figure_palette.toml), which should also be used
for future experiment figures.

## Row-closure/refresh diagnostic

After running the matched ten-trace refresh-disabled preset, compare it with
the completed NACK quick run using:

```bash
PYTHONPATH=python .venv/bin/python \
  experiments/ddram_p_policy_sweep/plot_row_closure_diagnostic.py
```

This writes `output/row_closure_refresh_quick_diagnostic.{png,pdf}`. The upper
panel compares NACK-refresh overhead under open-page and auto-precharge-B row
policies for normal row-closing refresh and the explicitly counterfactual
row-preserving control. The lower panel shows how both refresh variants change
open-page row-hit, row-conflict, and row-miss rates. The shaded aggregate uses
a cycle-ratio geomean in the upper panel and an arithmetic mean in the lower
panel.

`dram_refresh_preserve_open_rows` defaults to `false` and must not be enabled
for normal DDRAM-P results. Only the named
`mordor_10m_quick_nack_preserve.json` diagnostic preset enables it. The control
keeps a row logically open across internal refresh while still making its view
or locked region unavailable during the refresh interval.
