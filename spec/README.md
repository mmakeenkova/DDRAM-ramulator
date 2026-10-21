# DDRAM specifications

This directory contains implementation specifications and their compiled PDFs.
The generated PDFs are intentionally retained alongside the LaTeX sources.

Build all specifications with:

```bash
make -C spec
```

Current documents:

- `ddram_o_milestone1.tex` / `ddram_o_milestone1.pdf`: simplified DDRAM-O
  device and timing model for Milestone 1. Revision 0.7 / timing ledger M1-P1
  inherits Pumulator's SIMDRAM AP/AAP assumptions from the supplied
  `pumulator_infra_all` snapshot at commit `8fd8bd6f`. Source paths and the
  limits of that inheritance are recorded in the document.

M1-P1 replaces the legacy copy margin `ceil(nRP / 4)` with a configurable
4 ns split-decoder delay, rounded up using the selected DDR5 clock period.
At DDR5_3200AN, MRA remains 76 cycles and COPY/NOT become 83 cycles
(previously 82). A two-activate copy profile is documented for sensitivity
analysis. Cross-view delay and activation-power assumptions remain provisional
DDRAM-specific choices.

Simulator defaults and PuD override resolution now implement M1-P1 locally
to DDRAM-O. Use `tDEC_ns=4.0` and
`copy_timing_profile="pumulator-split"` (defaults), or select
`"pumulator-two-activate"`. Resolved configurations include a
`ddram_timing_model` provenance record. COPY/NOT remain reserved timing costs.

Revision 0.3 adds the controller-integration contract: conventional host
accesses use view A, bit-serial PuD uses view B with compatible bit-plane
placement, and scheduling cannot override layout requirements. It specifies
request metadata, command mapping, commitment/retry behavior, dependencies,
completion, and initial controller tests. These are requirements for the next
implementation; no controller code is changed by this specification update.

Revision 0.4 adds a PuD command/operation catalogue linking layout and operand
requirements, required view, symbolic service timing, and implementation
status. It covers MRA/COPY/NOT in both views, the B-oriented MAJ3 and arithmetic
sequences, and future layout conversion. Timing defaults remain in the timing
ledger; the catalogue includes rules for keeping mappings, examples, and tests
consistent when requirements change.

Revision 0.5 highlights B-view primitives as the initial PuD implementation
target and greys out A-view PuD primitives as deferred optional extensions.
The initial PuD controller/compiler scope is B-only; ordinary host accesses
continue through A. Existing low-level A-view device support is retained.

The first controller stage is implemented: `GenericDDR` with `DDRAM_O` maps
host reads/writes to A using `view_selection="Auto"` (default) or `"AlwaysA"`
and the `Open` row policy. `TwoView` and `QueueAware` are rejected for DDRAM-O.
DDR5 comparison tests are in
`tests/controller_scheduling/GenericDDRController/test_controller_ddram_o.py`
and included in `pytest-ddram.ini`.

Revision 0.6 records timing-only B-view MRA integration. C++ callers submit
`Request::Type::PudMRA` through `send()` with a concrete B-local address,
`required_view=1`, `pud_layout=BitSerial`, and nonnegative layout identity and
version. Admission supplies a shared `pud_completion` token; consumers can
use it as `pud_dependency`. Completion occurs after `nMRA`, independently of
read returns. Direct priority-queue MRA submission is rejected.

The Python validation harness exposes the same contract:

```python
producer = dut.send_pud(
    b_address, required_view=1, layout="BitSerial",
    layout_id=7, layout_version=1,
)
dut.send_pud(
    other_b_address, required_view=1, layout="BitSerial",
    layout_id=7, layout_version=1, dependency=producer,
)
```

Layout tags and versions are checked, but physical operand placement and data
values are not yet modeled. Compound arithmetic, general dependency graphs,
and conversion remain future work; ordinary host traffic remains pinned to A.

Revision 0.7 expands the implemented controller queueing contract. It records
the active, priority, PuD, and host arbitration order; FR-FCFS eligibility and
bypass behavior; PRE-to-MRA prerequisite residency; the separate MRA service
completion deque; and the distinction between admission, timing readiness,
command issue, and completion. It also explains why deliberate phase gaps in
the DDRAM-O visualizer trace are admission slack rather than extra device
timing.

The `.aux`, `.log`, `.out`, and table-of-contents files are build artifacts and
are not retained.
