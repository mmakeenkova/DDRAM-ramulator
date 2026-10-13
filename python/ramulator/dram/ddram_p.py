from ramulator.dram.ddr5 import DDR5
from ramulator.dram.spec import TimingConstraint
from copy import deepcopy

class DDRAM_P(DDR5):
    name = "DDRAM_P"

    # cross view delay -> TODO: what is this??
    nXACT = 8

    # expand existing command set -> MC will convert RD to RD_A or RD_B based on 
    # scheduling algorithm
    commands = DDR5.commands + [
        "ACT_A", "ACT_B",
        "PRE_A", "PRE_B",
        "RD_A", "RD_B",
        "WR_A", "WR_B",
    ]

    # values inherited from "normal" ACT, RD, WR
    command_cycles = {
        **DDR5.command_cycles,
        "ACT_A": 2,
        "ACT_B": 2,
        "RD_A": 2,
        "RD_B": 2,
        "WR_A": 2,
        "WR_B": 2,
    }

    # PREab and PREsb close both views in all banks/the bank 
    command_impl_overrides = {
        "PREab": "DDRAM_PREab",
        "PREsb": "DDRAM_PREsb",
    }

    timing_constraints = deepcopy(DDR5.timing_constraints)
    activation_commands = ["ACT", "ACT_A", "ACT_B"]

    for constraint in timing_constraints:

        # apply nRRDS to ACT_A and ACT_B also
        if (
            constraint.level == "Rank"
            and constraint.latency == "nRRDS"
            and constraint.preceding == ["ACT"]
            and constraint.following == ["ACT"]
        ):
            constraint.preceding = activation_commands.copy()
            constraint.following = activation_commands.copy()

        # apply nRRDL to ACT_A and ACT_B also
        elif (
            constraint.level == "BankGroup"
            and constraint.latency == "nRRDL"
            and constraint.preceding == ["ACT"]
            and constraint.following == ["ACT"]
        ):
            constraint.preceding = activation_commands.copy()
            constraint.following = activation_commands.copy()

        # four-activation window (nFAW)
        elif (
            constraint.level == "Rank"
            and constraint.latency == "nFAW"
            and constraint.window == 4
            and constraint.shared_window
        ):
            constraint.preceding.extend(["ACT_A", "ACT_B"])
            constraint.following.extend(["ACT_A", "ACT_B"])

    timing_constraints += [
        TimingConstraint(
            level="Bank",
            preceding=["ACT_A"],
            following=["RD_A", "WR_A"],
            latency="nRCD",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["ACT_B"],
            following=["RD_B", "WR_B"],
            latency="nRCD",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["ACT_A"],
            following=["PRE_A"],
            latency="nRAS",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["ACT_B"],
            following=["PRE_B"],
            latency="nRAS",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["PRE_A"],
            following=["ACT_A"],
            latency="nRP",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["PRE_B"],
            following=["ACT_B"],
            latency="nRP",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["ACT_A"],
            following=["ACT_A"],
            latency="nRC",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["ACT_B"],
            following=["ACT_B"],
            latency="nRC",
        ),

        ## inter-view timing constraints
        TimingConstraint(
            level="Bank",
            preceding=["ACT_A"],
            following=["ACT_B"],
            latency=str(nXACT),  #bruh.
        ),
        TimingConstraint(
            level="Bank",
            preceding=["ACT_B"],
            following=["ACT_A"],
            latency=str(nXACT),
        ),
    ]