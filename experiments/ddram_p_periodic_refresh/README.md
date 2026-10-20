# DDRAM-P periodic-refresh comparison

This experiment compares three refresh interfaces against a matched no-refresh
baseline for both one-view (`AlwaysA`) and two-view (`TwoView`) DDRAM-P:

- **Periodic REFab:** Ramulator's controller-issued `AllBank` manager injects a
  rank-level `REFab` every `nREFI`. Normal DDRAM-P prerequisites close both views
  before refresh, and `nRFC` blocks the rank afterward.
- **Oracle:** DRAM-managed fine-grained refresh advertises unavailable regions
  before activation.
- **NACK:** activation discovers an unavailable refresh region and is retried
  after that region becomes available.

Every point uses one simulated core, `FRFCFSViewAware`, open-page policy, the
same DDR5-4800 timing preset, and the same trace slice. The counterfactual
`dram_refresh_preserve_open_rows` option is explicitly disabled.

Run the ten-trace, 10-million-instruction preset and generate the plots with:

```bash
PYTHONPATH=python .venv/bin/python \
  experiments/ddram_p_periodic_refresh/run.py \
  --config mordor_10m_quick \
  --workers 4
```

The command runs 80 simulations (10 workloads × 8 configurations), then emits:

- `measurements.csv`: raw simulator measurements;
- `summary.csv`: matched refresh-overhead values and baseline RBMPKI;
- `results.json`: complete metadata and measurements;
- `rbmpki_refresh_comparison.{png,pdf}`: vertically stacked one-/two-view plots;
- `rbmpki_refresh_comparison_groups.txt`: workload tercile membership;
- `rbmpki_refresh_comparison_numeric_results.md`: plotted raw and aggregate values.

The RBMPKI classes are equal-count terciles using
`1000 * (row_misses + row_conflicts) / instructions` from the one-view,
no-refresh baseline. Refresh overhead is always normalized to the no-refresh
configuration with the same view count.

To regenerate only the plots:

```bash
PYTHONPATH=python .venv/bin/python \
  experiments/ddram_p_periodic_refresh/plot.py \
  --result-dir experiments/ddram_p_periodic_refresh/output/mordor_10m_periodic_refresh_quick
```

The periodic and managed mechanisms do not model identical refresh granularity:
`REFab` is rank-wide, whereas Oracle/NACK model fine-grained internal refresh.
The plot is therefore an interface comparison, not a claim that the mechanisms
perform the same physical refresh work.
