"""Milestone-one DDRAM-O device model.

This layer introduces orthogonal A/B conventional commands and an atomic
multi-row activation command.  It deliberately models timing/state only:
operand encoding, PuD functional semantics, and persistent three-/five-row
states belong to later milestones.
"""

from copy import deepcopy
from decimal import Decimal, ROUND_CEILING
from math import isfinite

from ramulator.dram.ddr5 import DDR5
from ramulator.dram.ddram_p import DDRAM_P
from ramulator.dram.spec import TimingConstraint


def _extend_unique(commands, additions):
    for command in additions:
        if command not in commands:
            commands.append(command)


class DDRAM_O(DDR5):
    name = "DDRAM_O"

    commands = DDR5.commands + [
        "ACT_A", "ACT_B", "PRE_A", "PRE_B",
        "RD_A", "RD_B", "WR_A", "WR_B",
        "RDA_A", "RDA_B", "WRA_A", "WRA_B",
        "MRA_A", "MRA_B",
    ]

    command_cycles = {
        **DDR5.command_cycles,
        "ACT_A": 2,
        "ACT_B": 2,
        "RD_A": 2,
        "RD_B": 2,
        "WR_A": 2,
        "WR_B": 2,
        "RDA_A": 2,
        "RDA_B": 2,
        "WRA_A": 2,
        "WRA_B": 2,
        # MRA carries row-selection information, so use DDR5's two-cycle
        # address-command occupancy as a conservative placeholder.
        "MRA_A": 2,
        "MRA_B": 2,
    }

    command_impl_overrides = {
        "PREab": "DDRAM_PREab",
        "PREsb": "DDRAM_PREsb",
        **{
            command: f"DDRAM_O_{command}"
            for command in (
                "ACT_A", "ACT_B", "RD_A", "RD_B", "WR_A", "WR_B",
                "RDA_A", "RDA_B", "WRA_A", "WRA_B", "MRA_A", "MRA_B",
            )
        },
    }

    timing_params = DDR5.timing_params + ["nXACTO", "nMRA", "nCOPY", "nNOT"]
    timing_presets = deepcopy(DDR5.timing_presets)
    for _preset in timing_presets.values():
        _preset.update(nXACTO=-1, nMRA=-1, nCOPY=-1, nNOT=-1)

    # DDRAM: Keep the default AP/AAP costs available to preset resolution and codegen.
    @classmethod
    def resolve_secondary_timings(cls, timing_dict, org_dict):
        super().resolve_secondary_timings(timing_dict, org_dict)
        cls._resolve_pud_defaults(timing_dict, "pumulator-split", 4.0)

    # DDRAM: Configure physical decoder delay and copy profile without changing DDR5's DSL.
    def __init__(self, *, copy_timing_profile="pumulator-split", tDEC_ns=4.0, **kwargs):
        super().__init__(**kwargs)
        self.copy_timing_profile = copy_timing_profile
        self.tDEC_ns = tDEC_ns

    # DDRAM: Inherit Pumulator's ceiling-rounded AP/AAP formulas, independently of MRA overrides.
    @staticmethod
    def _resolve_pud_defaults(timing_dict, profile, decoder_ns):
        if timing_dict["nXACTO"] == -1:
            timing_dict["nXACTO"] = 8
        if timing_dict["nMRA"] == -1:
            timing_dict["nMRA"] = timing_dict["nRAS"] + timing_dict["nRP"]
        if timing_dict["nCOPY"] == -1:
            decoder_ticks = Decimal(str(decoder_ns)) * 1000 / Decimal(str(timing_dict["tCK_ps"]))
            decoder_cycles = int(decoder_ticks.to_integral_value(rounding=ROUND_CEILING))
            timing_dict["nCOPY"] = timing_dict["nRAS"] + timing_dict["nRP"] + (
                decoder_cycles if profile == "pumulator-split" else timing_dict["nRAS"])
        if timing_dict["nNOT"] == -1:
            timing_dict["nNOT"] = timing_dict["nCOPY"]

    # DDRAM: Derive PuD defaults after all explicit base and primitive overrides, locally to DDRAM-O.
    def resolve(self):
        if self.copy_timing_profile not in ("pumulator-split", "pumulator-two-activate"):
            raise ValueError("DDRAM_O: unknown copy_timing_profile")
        if (isinstance(self.tDEC_ns, bool) or not isinstance(self.tDEC_ns, (int, float))
                or not isfinite(self.tDEC_ns) or self.tDEC_ns <= 0):
            raise ValueError("DDRAM_O: tDEC_ns must be finite and positive")
        org_dict, timing_dict = super().resolve()
        for name in ("nRAS", "nRP", "tCK_ps"):
            value = timing_dict[name]
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"DDRAM_O: {name} must be a positive integer, got {value}")
        for name in ("nXACTO", "nMRA", "nCOPY", "nNOT"):
            if name in self._overrides:
                value = timing_dict[name]
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    raise ValueError(f"DDRAM_O: {name} must be a positive integer, got {value}")
            else:
                timing_dict[name] = -1
        self._resolve_pud_defaults(timing_dict, self.copy_timing_profile, self.tDEC_ns)
        for name in ("nXACTO", "nMRA", "nCOPY", "nNOT"):
            value = timing_dict[name]
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"DDRAM_O: {name} must be a positive integer, got {value}")
        return org_dict, timing_dict

    # DDRAM: Preserve timing provenance alongside the resolved cycle values in experiment configs.
    def to_config(self):
        config = super().to_config()
        config["ddram_timing_model"] = dict(
            revision="M1-P1", copy_profile=self.copy_timing_profile,
            tDEC_ns=self.tDEC_ns, rounding="ceil",
            org_preset=self.org_preset, timing_preset=self.timing_preset,
            overrides=dict(self._overrides), intersection_modeling=False,
        )
        return config

    # DDRAM-P already supplies the tested dual-view DDR5 timing envelope.  We
    # copy it rather than subclassing DDRAM-P so its command semantics and
    # managed-refresh events cannot leak into DDRAM-O.
    timing_constraints = deepcopy(DDRAM_P.timing_constraints)

    _maintenance_commands = {"REFab", "REFsb", "RFMab", "RFMsb"}

    for _constraint in timing_constraints:
        # MRA draws from the same rank-level activation budget as ACT.
        if (
            _constraint.level in ("Rank", "BankGroup")
            and _constraint.latency in ("nRRDS", "nRRDL")
            and "ACT" in _constraint.preceding
            and "ACT" in _constraint.following
        ):
            _extend_unique(_constraint.preceding, ["MRA_A", "MRA_B"])
            _extend_unique(_constraint.following, ["MRA_A", "MRA_B"])
        if (
            _constraint.level == "Rank"
            and _constraint.latency == "nFAW"
            and _constraint.window == 4
            and _constraint.shared_window
        ):
            _extend_unique(_constraint.preceding, ["MRA_A", "MRA_B"])
            _extend_unique(_constraint.following, ["MRA_A", "MRA_B"])

        # All-bank/same-bank maintenance must also delay a following MRA.
        if _maintenance_commands.intersection(_constraint.preceding):
            if {"ACT", "ACT_A", "ACT_B"}.intersection(_constraint.following):
                _extend_unique(_constraint.following, ["MRA_A", "MRA_B"])

        # Any operation that releases a bank/view for ACT also releases it for
        # the corresponding atomic MRA.
        if "PRE_A" in _constraint.preceding and "ACT_A" in _constraint.following:
            _extend_unique(_constraint.following, ["MRA_A"])
        if "PRE_B" in _constraint.preceding and "ACT_B" in _constraint.following:
            _extend_unique(_constraint.following, ["MRA_B"])
        if {"PREab", "PREsb"}.intersection(_constraint.preceding):
            if {"ACT", "ACT_A", "ACT_B"}.intersection(_constraint.following):
                _extend_unique(_constraint.following, ["MRA_A", "MRA_B"])

        # Replace DDRAM-P's fixed cross-view placeholder with a configurable
        # DDRAM-O timing parameter and include all ACT/MRA combinations.
        if (
            _constraint.level == "Bank"
            and _constraint.preceding == ["ACT_A"]
            and _constraint.following == ["ACT_B"]
        ):
            _constraint.preceding = ["ACT_A", "MRA_A"]
            _constraint.following = ["ACT_B", "MRA_B"]
            _constraint.latency = "nXACTO"
        elif (
            _constraint.level == "Bank"
            and _constraint.preceding == ["ACT_B"]
            and _constraint.following == ["ACT_A"]
        ):
            _constraint.preceding = ["ACT_B", "MRA_B"]
            _constraint.following = ["ACT_A", "MRA_A"]
            _constraint.latency = "nXACTO"

    # The atomic MRA leaves its target view closed but occupies that view for
    # nMRA cycles.  The other view can start an activation-like operation once
    # nXACTO (and shared nRRD/nFAW constraints) permit it.
    timing_constraints += [
        TimingConstraint(
            level="Bank",
            preceding=["MRA_A"],
            following=["ACT_A", "MRA_A", "PRE_A", "RD_A", "RDA_A", "WR_A", "WRA_A"],
            latency="nMRA",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["MRA_B"],
            following=["ACT_B", "MRA_B", "PRE_B", "RD_B", "RDA_B", "WR_B", "WRA_B"],
            latency="nMRA",
        ),
        TimingConstraint(
            level="Rank",
            preceding=["MRA_A", "MRA_B"],
            following=["REFab", "REFsb", "RFMab", "RFMsb"],
            latency="nMRA",
        ),
    ]
