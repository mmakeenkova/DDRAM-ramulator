# DDRAM-P trace-visualizer experiment

This experiment runs the generic DDR controller with `DDRAM_P`, the
`FRFCFSViewAware` scheduler, `TwoView` selection, and an explicitly configured
`BinTraceRecorder`. Trace recording is local to this experiment; other
controllers and tests do not record unless they also add the plugin.
The recorder enables `record_equal_constraints=True`, so the visualizer can
show every constraint tied for the strictest ready time rather than just one.

Run the small bundled example from the repository root:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_visualizer/run.py
```

The default SimpleO3 trace alternates cache lines from two rows in the same
bank, making the initial `ACT_A`/`ACT_B` and subsequent view-local accesses easy
to find. Supply `--trace` to use any other SimpleO3-format file.

The resulting trace is:

```text
experiments/ddram_p_visualizer/output/ddram_p.ch0.ram2bin
```

Start the visualizer and drop that file onto its upload page:

```bash
PYTHONPATH=python .venv/bin/python -m ramulator visualize --dev
```

Timing relationships are shown as subtle colored arrows by default. Hover an
arrow or either command to emphasize it and show a readable description such
as `ACT A → ACT B delay · nRRDL = 8 cycles`. The ready-time marker separates
the solid timing portion from any dashed scheduling/resource slack.
The **Bottlenecks** popover ranks the strictest constraints across the trace.

The **Row hits** popover reports the overall hit rate plus read/write and
view-A/view-B breakdowns. Row-hit accesses have a dashed lime outline by
default. In **Settings**, enable **Color borders by view** to add a cyan A or
pink B outline without replacing the existing command/request colors; internal
`IREF_A` and `IREF_B` events are included. These display preferences persist in
the browser. When a same-lane dependency arrow is routed below its commands,
its hover label is also placed below the arrow to avoid covering the bars.

The visualizer requires Node.js 20+ and npm. On first use, the launcher installs
the packages under `visualizer/node_modules`. A production build can instead be
created with `cd visualizer && npm install && npm run build`.

## MORDOR CPU traces

The extracted MORDOR traces at `/home/maria/MORDOR/cputraces/cputraces` already
use the SimpleO3 input format expected by this experiment. Select one by name:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_visualizer/run.py \
  --mordor-trace 538.imagick \
  --instructions 100000
```

Override the directory either with `--mordor-root` or the
`MORDOR_CPUTRACES` environment variable:

```bash
MORDOR_CPUTRACES=/path/to/cputraces/cputraces \
PYTHONPATH=python .venv/bin/python experiments/ddram_p_visualizer/run.py \
  --mordor-trace 429.mcf
```

SimpleO3 loads its entire input file into memory. For large MORDOR workloads,
make and use a local prefix without modifying the source dataset:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_visualizer/run.py \
  --mordor-trace 505.mcf \
  --trace-lines 50000 \
  --instructions 100000
```

Generated slices and `.ram2bin` files live under `output/` and are ignored by
Git. Use `--output` to choose a different trace prefix. Use
`--view-selection AlwaysA` for a single-view comparison.

## Asymmetric view auto-precharge

Use view B as a transient view while leaving A open-page. The policy keeps B
open when at least one other same-bank, same-row request is buffered, then uses
`RDA_B` or `WRA_B` for the last queued access:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_visualizer/run.py \
  --row-policy DDRAMViewAutoPrecharge \
  --auto-precharge-view B
```

The default output is
`output/ddram_p.auto-precharge-b.ch0.ram2bin`. Use
`--no-preserve-queued-hits` for an always-transient view, or
`--min-hits-to-preserve N` to require more queued reuse before keeping the row
open. `--auto-precharge-view A` provides the symmetric policy for experiments.

In Command View, an `RDA_A/B` or `WRA_A/B` is followed by an auto-precharge
overlay: a dashed gray recovery interval and an orange `nRP` interval. The end
of the orange interval is the earliest point at which that view can be
activated again. Hover the originating command for the timing values. This is
an internal phase of the combined command, not a separately issued `PRE_A/B`.
The overlay is enabled by default and can be hidden under **Settings → Show
auto-precharge phases**.

## Autonomous refresh

The experiment can enable either DRAM-managed refresh interface. It continues
to use `NoRefresh`: `IREF_A`/`IREF_B` are generated inside the device model,
not submitted through the controller maintenance queue.

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_visualizer/run.py \
  --managed-refresh Oracle --refresh-interval 256 --refresh-duration 32

PYTHONPATH=python .venv/bin/python experiments/ddram_p_visualizer/run.py \
  --managed-refresh Nack --refresh-interval 256 --refresh-duration 32
```

These commands automatically produce:

```text
output/ddram_p.refresh-oracle.interval-256.duration-32.ch0.ram2bin
output/ddram_p.refresh-nack.interval-256.duration-32.ch0.ram2bin
```

When interval or duration is left at its default, the filename uses `nREFI` or
`nRFCsb`, for example
`ddram_p.refresh-oracle.interval-nREFI.duration-nRFCsb.ch0.ram2bin`.
An explicit `--output` continues to override the complete prefix.

Oracle mode suppresses ACTs that would conflict with a private refresh lock.
Nack mode attempts them, emits an `ACT_NACK` trace event, and retries after the
configured NACK latency plus ARI. Internal refreshes use a closed view and can
overlap demand work in the other view when it targets a different lock region.
The visualizer labels `IREF_A`, `IREF_B`, and `ACT_NACK` as **INTERNAL** events.
They remain visible in the command hierarchy, but are excluded from external
command-bus timing edges and command-bus utilization.

### Deterministic Oracle/NACK collision

The bundled CPU trace does not guarantee that an ACT arrives while its region
is locked. Generate a compact, one-bank comparison that deliberately injects a
read to row 0 one cycle after row 0 begins internal refresh:

```bash
PYTHONPATH=python .venv/bin/python \
  experiments/ddram_p_visualizer/refresh_collision.py
```

This writes a matched pair under `output/`:

```text
ddram_p.collision.refresh-oracle.interval-16.duration-12.ch0.ram2bin
ddram_p.collision.refresh-nack.interval-16.duration-12.ch0.ram2bin
```

Load them in the Compare view. Oracle delays the ACT until the region unlocks.
NACK attempts the ACT during the lock and records `ACT_NACK` events at the
configured retry spacing before the eventual ACT and RD.

For a side-by-side comparison, run the same input with distinct output names:

```bash
PYTHONPATH=python .venv/bin/python experiments/ddram_p_visualizer/run.py \
  --view-selection AlwaysA --output experiments/ddram_p_visualizer/output/always_a
PYTHONPATH=python .venv/bin/python experiments/ddram_p_visualizer/run.py \
  --view-selection TwoView --output experiments/ddram_p_visualizer/output/two_view
```

Open the visualizer's **Compare** view and load `always_a.ch0.ram2bin` above
`two_view.ch0.ram2bin`. Pan and zoom are synchronized by default. To compensate
for different startup or scheduling offsets, choose **Align commands** and click
the corresponding command in each panel; that pair becomes the shared relative
time origin.

## Queue-aware replacement comparison

Generate a short, deterministic comparison between A-first `TwoView` replacement
and the queue-aware policy:

```bash
PYTHONPATH=python .venv/bin/python \
  experiments/ddram_p_visualizer/queue_aware_comparison.py
```

This writes:

```text
output/ddram_p.view-two-view.ch0.ram2bin
output/ddram_p.view-queue-aware.ch0.ram2bin
```

Both traces first open row 10 in A and row 20 in B, then issue a read miss for
row 30 while two writes to row 10 are waiting. `TwoView` replaces A and later
needs another `PRE`/`ACT` pair to reopen row 10. `QueueAware` replaces B and
preserves the two `WR_A` row hits. Load the pair in **Trace comparison** and
align the initial `RD_B` immediately before the traces diverge.
