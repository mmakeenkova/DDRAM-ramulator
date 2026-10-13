from ramulator.dram.ddr5 import DDR5


class DDRAM_P(DDR5):
    name = "DDRAM_P"

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