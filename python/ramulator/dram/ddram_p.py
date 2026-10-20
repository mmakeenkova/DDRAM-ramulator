from ramulator.dram.ddr5 import DDR5
from ramulator.dram.spec import TimingConstraint
from copy import deepcopy

def expand_column_commands(commands):
    result = []

    for command in commands:
        if command == "RD":
            result.extend(["RD", "RD_A", "RD_B"])
        elif command == "RDA":
            result.extend(["RDA", "RDA_A", "RDA_B"])
        elif command == "WR":
            result.extend(["WR", "WR_A", "WR_B"])
        elif command == "WRA":
            result.extend(["WRA", "WRA_A", "WRA_B"])
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
        "RDA_A", "RDA_B",
        "WRA_A", "WRA_B",
        # Device-internal, row-granular refresh events.  These are observable
        # in command traces but never travel over the external command bus.
        "IREF_A", "IREF_B", "ACT_NACK",
    ]
    internal_commands = ["IREF_A", "IREF_B", "ACT_NACK"]

    # values inherited from "normal" ACT, RD, WR
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
        "IREF_A": 1,
        "IREF_B": 1,
        "ACT_NACK": 1,
    }

    # PREab and PREsb close both views in all banks/the bank 
    command_impl_overrides = {
        "PREab": "DDRAM_PREab",
        "PREsb": "DDRAM_PREsb",
    }

    timing_constraints = deepcopy(DDR5.timing_constraints)
    activation_commands = ["ACT", "ACT_A", "ACT_B"]
    read_commands = ["RD", "RDA", "RD_A", "RD_B", "RDA_A", "RDA_B"]
    write_commands = ["WR", "WRA", "WR_A", "WR_B", "WRA_A", "WRA_B"]
    maintenance_commands = {"REFab", "REFsb", "RFMab", "RFMsb"}

    def extend_unique(commands, additions):
        """Add commands without introducing duplicates."""
        for cmd in additions:
            if cmd not in commands:
                commands.append(cmd)


    for constraint in timing_constraints:

        # ---------------------------------------------------------
        # 1. Shared activation constraints
        # ---------------------------------------------------------

        # nRRDS: activation spacing across bank groups
        if (
            constraint.level == "Rank"
            and constraint.latency == "nRRDS"
            and constraint.preceding == ["ACT"]
            and constraint.following == ["ACT"]
        ):
            constraint.preceding = activation_commands.copy()
            constraint.following = activation_commands.copy()

        # nRRDL: activation spacing within a bank group
        elif (
            constraint.level == "BankGroup"
            and constraint.latency == "nRRDL"
            and constraint.preceding == ["ACT"]
            and constraint.following == ["ACT"]
        ):
            constraint.preceding = activation_commands.copy()
            constraint.following = activation_commands.copy()

        # nFAW: four-activation window shared by both views
        elif (
            constraint.level == "Rank"
            and constraint.latency == "nFAW"
            and constraint.window == 4
            and constraint.shared_window
        ):
            extend_unique(constraint.preceding, ["ACT_A", "ACT_B"])
            extend_unique(constraint.following, ["ACT_A", "ACT_B"])

        # ---------------------------------------------------------
        # 2. Bank-wide precharge constraints
        # ---------------------------------------------------------

        # RD_A/B -> PREab: read-to-precharge recovery
        if (
            constraint.level == "Rank"
            and constraint.latency == "nRTP"
            and "PREab" in constraint.following
            and "RD" in constraint.preceding
        ):
            extend_unique(constraint.preceding, ["RD_A", "RD_B", "RDA_A", "RDA_B"])

        # WR_A/B -> PREab: write recovery
        if (
            constraint.level == "Rank"
            and constraint.latency == "nCWL + nBL + nWR"
            and "PREab" in constraint.following
            and "WR" in constraint.preceding
        ):
            extend_unique(constraint.preceding, ["WR_A", "WR_B", "WRA_A", "WRA_B"])

        # ACT_A/B -> PREab: minimum active time
        if (
            constraint.level == "Rank"
            and constraint.latency == "nRAS"
            and "PREab" in constraint.following
            and "ACT" in constraint.preceding
        ):
            extend_unique(constraint.preceding, ["ACT_A", "ACT_B"])

        # ---------------------------------------------------------
        # 3. Maintenance constraints
        # ---------------------------------------------------------

        # Maintenance -> activation
        # e.g., REFab -> ACT_A/B (nRFC)
        if (
            maintenance_commands.intersection(constraint.preceding)
            and "ACT" in constraint.following
        ):
            extend_unique(constraint.following, ["ACT_A", "ACT_B"])

        # Activation -> maintenance
        # e.g., ACT_A/B -> REFab (nRC)
        if (
            "ACT" in constraint.preceding
            and maintenance_commands.intersection(constraint.following)
        ):
            extend_unique(constraint.preceding, ["ACT_A", "ACT_B"])

        # View-local auto-precharge has completed only after its access
        # recovery plus nRP, so preserve DDR5's RDA/WRA-to-maintenance delays.
        if maintenance_commands.intersection(constraint.following):
            if "RDA" in constraint.preceding:
                extend_unique(constraint.preceding, ["RDA_A", "RDA_B"])
            if "WRA" in constraint.preceding:
                extend_unique(constraint.preceding, ["WRA_A", "WRA_B"])

        # DDRAM: View-local PRE replaces PREpb for shared precharge spacing and
        # maintenance recovery. Keep PRE-to-ACT bank timing view-local below.
        if constraint.level == "Rank" or maintenance_commands.intersection(
            constraint.preceding + constraint.following
        ):
            if "PREpb" in constraint.preceding:
                extend_unique(constraint.preceding, ["PRE_A", "PRE_B"])
            if "PREpb" in constraint.following:
                extend_unique(constraint.following, ["PRE_A", "PRE_B"])

        # DDRAM: PREab closes both views and delays either view's next activation.
        if "PREab" in constraint.preceding and "ACT" in constraint.following:
            extend_unique(constraint.following, ["ACT_A", "ACT_B"])

    timing_constraints += [
        TimingConstraint(
            level="Bank",
            preceding=["ACT_A"],
            following=["RD_A", "RDA_A", "WR_A", "WRA_A"],
            latency="nRCD",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["ACT_B"],
            following=["RD_B", "RDA_B", "WR_B", "WRA_B"],
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
        # Auto-precharge closes only its issuing view. The state transition is
        # immediate in the model, while these constraints represent the time
        # during which that view remains unavailable for a new activation.
        TimingConstraint(
            level="Bank",
            preceding=["RDA_A"],
            following=["ACT_A"],
            latency="nRTP + nRP",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["RDA_B"],
            following=["ACT_B"],
            latency="nRTP + nRP",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["WRA_A"],
            following=["ACT_A"],
            latency="nCWL + nBL + nWR + nRP",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["WRA_B"],
            following=["ACT_B"],
            latency="nCWL + nBL + nWR + nRP",
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
            preceding=["RD_A", "RD_B", "RDA_A", "RDA_B"],
            following=["PREsb"],
            latency="nRTP",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["WR_A", "WR_B", "WRA_A", "WRA_B"],
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
            ({"RD", "RDA", "WR", "WRA"} & set(constraint.preceding + constraint.following))):
            constraint.preceding = expand_column_commands(constraint.preceding)
            constraint.following = expand_column_commands(constraint.following)
