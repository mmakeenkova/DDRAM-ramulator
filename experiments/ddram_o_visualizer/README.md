# DDRAM-O visualizer trace

Generate a compact trace that exercises both DDRAM-O views and both directions
of the provisional cross-view activation delay:

```bash
PYTHONPATH=python:. .venv/bin/python \
  experiments/ddram_o_visualizer/generate.py
```

The default output is:

`experiments/ddram_p_visualizer/output/ddram_o.cross-view.ch0.ram2bin`

Two pre-generated comparison traces use `nXACTO=12` and `nXACTO=17`:

- `ddram_o.cross-view.nxacto-12.ch0.ram2bin`
- `ddram_o.cross-view.nxacto-17.ch0.ram2bin`

Load those into the top and bottom comparison panels and align on either
`MRA_B`. Both directions of the cross-view edge remain the strictest timing
constraint, while the five-cycle displacement is directly visible.

Open it in the trace visualizer and enable **Settings → Split view A/B lanes**
and **Color by operation**. The trace includes A-side host reads, B-side
bit-serial MRA operations with two layout identities, and timing arrows for
`ACT_A → MRA_B` and `MRA_B → ACT_A` when those constraints are the strictest.

This script currently uses the controller scheduling harness only as a request
driver. The GenericDDR controller, DDRAM-O device, scheduler, timing model, and
binary trace recorder are the production implementations.
