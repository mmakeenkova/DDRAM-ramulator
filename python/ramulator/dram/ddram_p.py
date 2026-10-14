from ramulator.dram.ddr5 import DDR5
from ramulator.dram.spec import TimingConstraint
from copy import deepcopy

def expand_column_commands(commands):
    result = []

    for command in commands:
        if command == "RD":
            result.extend(["RD", "RD_A", "RD_B"])
        elif command == "WR":
            result.extend(["WR", "WR_A", "WR_B"])
        else:
            result.append(command)

    return result


class DDRAM_P(DDR5):
    name = "DDRAM_P"

    # cross view delay -> TODO: sweep this in experiments
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
    read_commands = ["RD", "RD_A", "RD_B"]
    write_commands = ["WR", "WR_A", "WR_B"]

    
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

        # Read-to-bank-wide-precharge
        if (
            constraint.level == "Rank"
            and constraint.following == ["PREab"]
            and constraint.latency == "nRTP"
        ):
            constraint.preceding.extend(["RD_A", "RD_B"])

        # Write-to-bank-wide-precharge
        elif (
            constraint.level == "Rank"
            and constraint.following == ["PREab"]
            and constraint.latency == "nCWL + nBL + nWR"
        ):
            constraint.preceding.extend(["WR_A", "WR_B"])

        # ACT-to-PREab minimum active time
        if (
            constraint.level == "Rank"
            and constraint.preceding == ["ACT"]
            and constraint.following == ["PREab"]
            and constraint.latency == "nRAS"
        ):
            constraint.preceding.extend(["ACT_A", "ACT_B"])

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
        # view-local read-to-precharge timing
        TimingConstraint(
            level="Bank",
            preceding=["RD_A"],
            following=["PRE_A"],
            latency="nRTP",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["RD_B"],
            following=["PRE_B"],
            latency="nRTP",
        ),
        # view-local write-to-precharge timing
        TimingConstraint(
            level="Bank",
            preceding=["WR_A"],
            following=["PRE_A"],
            latency="nCWL + nBL + nWR",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["WR_B"],
            following=["PRE_B"],
            latency="nCWL + nBL + nWR",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["ACT_B"],
            following=["ACT_B"],
            latency="nRC",
        ),
        # PREsb closes both views
        TimingConstraint(
            level="Bank",
            preceding=["ACT_A", "ACT_B"],
            following=["PREsb"],
            latency="nRAS",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["RD_A", "RD_B"],
            following=["PREsb"],
            latency="nRTP",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["WR_A", "WR_B"],
            following=["PREsb"],
            latency="nCWL + nBL + nWR",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["PREsb"],
            following=["ACT_A", "ACT_B"],
            latency="nRP",
        ),
    ]

    # inherit these constraints from DDR5 and apply to RD_A, RD_B, WR_A, WR_B
    # assumption: shared column-command path and data interface for both views
    # DDRAM-P does *not* have two independednt external data busses
    column_latency_names = {
        "nBL",
        "nCCDS",
        "nCCDS_WR",
        "nRTW",
        "nCWL + nBL + nWTRS",
        "nCCDL",
        "nCCDL_WR",
        "nCWL + nBL + nWTRL",
        "nCCDM",
        "nCCDM_WR",
        "nCWL + nBL + nWTRM",
        "nBL + nCS",
        "nCWL + nBL + nCS - nCL",
    }

    for constraint in timing_constraints:
        if (constraint.latency in column_latency_names and 
            ({"RD", "WR"} & set(constraint.preceding + constraint.following))):
            constraint.preceding = expand_column_commands(constraint.preceding)
            constraint.following = expand_column_commands(constraint.following)
