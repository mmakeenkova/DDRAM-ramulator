import ramulator
from tests.device_timings.harness import DeviceUnderTest
import pytest

# helper
def make_two_view_dut():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)
    row_a = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row_b = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)

    dut.issue("ACT_A", row_a, clk=0)
    dut.issue("ACT_B", row_b, clk=100)
    timings = dict(zip(dram.timing_params, dram.to_config()["timing"]))
    return dut, row_a, row_b, timings

def test_ddram_p_views():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )

    dut = DeviceUnderTest(dram)

    row10 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row20 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)
    row30 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=30, Column=0)

    assert dut.probe("RD_A", row10, clk=0).preq == "ACT_A"
    assert dut.probe("RD_B", row20, clk=0).preq == "ACT_B"

    # open row 10 in view A
    dut.issue("ACT_A", row10, clk=0)
    assert dut.probe("RD_A", row10, clk=1).row_hit
    assert not dut.probe("RD_B", row10, clk=1).row_hit

    # open row 20 in view B without closing row A
    dut.issue("ACT_B", row20, clk=1000)
    assert dut.probe("RD_A", row10, clk=1001).row_hit
    assert dut.probe("RD_B", row20, clk=1001).row_hit

    # close A but not B
    dut.issue("PRE_A", row10, clk=2000)
    assert not dut.probe("RD_A", row10, clk=2001).row_open
    assert dut.probe("RD_B", row20, clk=2001).row_hit


    # open another row in view A
    dut.issue("ACT_A", row30, clk=3000)
    assert dut.probe("RD_A", row30, clk=3001).row_hit
    assert dut.probe("RD_B", row20, clk=3001).row_hit

    # PREab must close both views
    dut.issue("PREab", row20, clk=4000)
    assert not dut.probe("RD_A", row20, clk=4001).row_open
    assert not dut.probe("RD_B", row20, clk=4001).row_open


def test_ddram_p_row_conflict():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )

    dut = DeviceUnderTest(dram)
    row10 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)

    dut.issue("ACT_A", row10, clk=0)
    with pytest.raises(RuntimeError, match="other view"):
        dut.issue("ACT_B", row10, clk=1000)



### REQUEST TIMING TEST ###
def test_ddram_p_activation_to_read():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    row10 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    dut.issue("ACT_A", row10, clk=0)

    # open row, nRCD has not elapsed
    assert dut.probe("RD_A", row10, clk=23).row_hit
    assert not dut.probe("RD_A", row10, clk=23).ready

    # at nRCD, the read becomes legal
    assert dut.probe("RD_A", row10, clk=24).ready
    dut.issue("RD_A", row10, clk=24)

def test_ddram_p_activation_to_precharge():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    row10 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    dut.issue("ACT_A", row10, clk=0)

    assert not dut.probe("PRE_A", row10, clk=51).ready
    assert dut.probe("PRE_A", row10, clk=53).ready

    dut.issue("PRE_A", row10, clk=53)
    assert not dut.probe("RD_A", row10, clk=54).row_open


def test_ddram_p_cross_view_activation_timing():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    row10 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row20 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)

    dut.issue("ACT_A", row10, clk=0)

    # cross-view activation range
    for clk in range(6, 11):
        result = dut.probe("ACT_B", row20, clk=clk)
        print(
            f"clk={clk}: "
            f"preq={result.preq}, "
            f"timing_OK={result.timing_OK}, "
            f"ready={result.ready}"
        )


def test_ddram_p_cross_view_activation_timing():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    row10 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row20 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)

    dut.issue("ACT_A", row10, clk=0)

    assert not dut.probe("ACT_B", row20, clk=7).ready
    assert dut.probe("ACT_B", row20, clk=8).ready

    dut.issue("ACT_B", row20, clk=8)

    # both rows remain open simultaneously
    assert dut.probe("RD_A", row10, clk=100).row_hit
    assert dut.probe("RD_B", row20, clk=100).row_hit  


def test_ddram_p_shared_activation_constraints():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )

    constraints = dram.timing_constraints

    expected_acts = {"ACT", "ACT_A", "ACT_B"}

    for level, latency in [
        ("Rank", "nRRDS"),
        ("BankGroup", "nRRDL"),
    ]:
        matches = [
            c for c in constraints
            if c.level == level
            and c.latency == latency
            and expected_acts.issubset(c.preceding)
            and expected_acts.issubset(c.following)
        ]
        assert len(matches) == 1

    faw = [
        c for c in constraints
        if c.level == "Rank"
        and c.latency == "nFAW"
        and c.window == 4
        and c.shared_window
    ]

    assert len(faw) == 1
    assert expected_acts.issubset(faw[0].preceding)
    assert expected_acts.issubset(faw[0].following)


def test_ddram_p_nrrds():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    row_bg0 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row_bg1 = dut.addr_vec(Rank=0, BankGroup=1, Bank=0, Row=20, Column=0)

    dut.issue("ACT_A", row_bg0, clk=0)

    nrrds = 8
    assert not dut.probe("ACT_B", row_bg1, clk=nrrds - 1).ready
    assert dut.probe("ACT_B", row_bg1, clk=nrrds).ready



def test_ddram_p_nrrdl():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    row_bank0 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row_bank1 = dut.addr_vec(Rank=0, BankGroup=0, Bank=1, Row=20, Column=0)

    dut.issue("ACT_A", row_bank0, clk=0)

    nrrdl = 8
    assert not dut.probe("ACT_B", row_bank1, clk=nrrdl - 1).ready
    assert dut.probe("ACT_B", row_bank1, clk=nrrdl).ready

def test_ddram_p_nfaw():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    rows = [
        dut.addr_vec(
            Rank=0,
            BankGroup=bg,
            Bank=0,
            Row=10 + bg,
            Column=0,
        )
        for bg in range(5)
    ]

    # four activations, alternating views
    for clk, command, addr in zip(
        [0, 8, 16, 24],
        ["ACT_A", "ACT_B", "ACT_A", "ACT_B"],
        rows[:4],
    ):
        dut.issue(command, addr, clk=clk)

    # tFAW for fifth activation
    assert not dut.probe("ACT_A", rows[4], clk=31).ready
    assert dut.probe("ACT_A", rows[4], clk=32).ready


def test_ddram_p_shared_column_constraints():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )

    constraints = dram.timing_constraints

    def find_constraint(level, latency, preceding, following):
        return any(
            c.level == level
            and c.latency == latency
            and set(preceding).issubset(c.preceding)
            and set(following).issubset(c.following)
            for c in constraints
        )

    assert find_constraint(
        "Channel", "nBL",
        ["RD_A", "RD_B"],
        ["RD_A", "RD_B"],
    )

    assert find_constraint(
        "Rank", "nRTW",
        ["RD_A", "RD_B"],
        ["WR_A", "WR_B"],
    )

    assert find_constraint(
        "Bank", "nCCDL",
        ["RD_A", "RD_B"],
        ["RD_A", "RD_B"],
    )

    assert find_constraint(
        "Bank", "nCWL + nBL + nWTRL",
        ["WR_A", "WR_B"],
        ["RD_A", "RD_B"],
    )


def test_ddram_p_read_to_read_timing():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    row10 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row20 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)

    # same bank
    dut.issue("ACT_A", row10, clk=0)
    dut.issue("ACT_B", row20, clk=100)

    assert dut.probe("RD_A", row10, clk=200).row_hit
    assert dut.probe("RD_B", row20, clk=200).row_hit

    dut.issue("RD_A", row10, clk=200)

    # find the earliest legal read through view B
    # it's 8 cycles btw -> view independence + shared column timings
    # this should be >= max (nBL, nCCDS, nCCDL)
    # nBL (channel, data bus occupancy), ncCDS (rank, column-to-column spacing)
    # nCCDL (bank, column-to-column spacing) -> shared column path for both views
    for clk in range(201, 221):
        result = dut.probe("RD_B", row20, clk=clk)

        print(
            f"clk={clk}: "
            f"preq={result.preq}, "
            f"timing_OK={result.timing_OK}, "
            f"ready={result.ready}"
        )
    config = dram.to_config()
    timings = dict(zip(dram.timing_params, config["timing"]))
    for name in ["nBL", "nCCDS", "nCCDL"]:
        print(f"{name} = {timings[name]}")


def test_ddram_p_read_to_read_timing2():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    row10 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row20 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)

    dut.issue("ACT_A", row10, clk=0)
    dut.issue("ACT_B", row20, clk=100)

    assert dut.probe("RD_A", row10, clk=200).row_hit
    assert dut.probe("RD_B", row20, clk=200).row_hit

    dut.issue("RD_A", row10, clk=200)

    assert not dut.probe("RD_B", row20, clk=207).ready
    assert dut.probe("RD_B", row20, clk=208).ready

    dut.issue("RD_B", row20, clk=208)
    assert dut.probe("RD_A", row10, clk=300).row_hit
    assert dut.probe("RD_B", row20, clk=300).row_hit


def test_ddram_p_read_to_write_turnaround():
    dut, row_a, row_b, t = make_two_view_dut()
    start = 200

    dut.issue("RD_A", row_a, clk=start)
    # shared external data bus
    expected = start + t["nRTW"]
    assert not dut.probe("WR_B", row_b, clk=expected - 1).ready
    assert dut.probe("WR_B", row_b, clk=expected).ready

    dut.issue("WR_B", row_b, clk=expected)
    # don't close view
    assert dut.probe("RD_A", row_a, clk=300).row_hit
    assert dut.probe("RD_B", row_b, clk=300).row_hit


def test_ddram_p_write_to_read_turnaround():
    dut, row_a, row_b, t = make_two_view_dut()
    start = 200

    dut.issue("WR_A", row_a, clk=start)

    rank_delay = t["nCWL"] + t["nBL"] + t["nWTRS"]
    bank_delay = t["nCWL"] + t["nBL"] + t["nWTRL"]

    expected_delay = max(rank_delay, bank_delay)
    expected = start + expected_delay
    assert not dut.probe("RD_B", row_b, clk=expected - 1).ready
    assert dut.probe("RD_B", row_b, clk=expected).ready

    dut.issue("RD_B", row_b, clk=expected)
    assert dut.probe("RD_A", row_a, clk=300).row_hit
    assert dut.probe("RD_B", row_b, clk=300).row_hit


def test_ddram_p_write_to_precharge():
    dut, row_a, row_b, t = make_two_view_dut()
    start = 200
    dut.issue("WR_A", row_a, clk=start)

    # DDR5 write recovery 
    recovery = t["nCWL"] + t["nBL"] + t["nWR"]
    expected = start + recovery

    first_ready = expected + 1  # matches observed DDR5
    assert not dut.probe("PRE_A", row_a, clk=first_ready - 1).ready
    assert dut.probe("PRE_A", row_a, clk=first_ready).ready
    dut.issue("PRE_A", row_a, clk=first_ready)  

    assert not dut.probe("RD_A", row_a, clk=300).row_open
    assert dut.probe("RD_B", row_b, clk=300).row_hit
    dut.issue("RD_B", row_b, clk=300)


def test_ddram_p_read_to_precharge():
    dut, row_a, row_b, t = make_two_view_dut()
    start = 200
    dut.issue("RD_A", row_a, clk=start)
    expected = start + t["nRTP"]

    first_ready = expected + 1  # matches observed DDR5
    assert not dut.probe("PRE_A", row_a, clk=first_ready - 1).ready
    assert dut.probe("PRE_A", row_a, clk=first_ready).ready
    dut.issue("PRE_A", row_a, clk=first_ready)
    assert dut.probe("RD_B", row_b, clk=300).row_hit

def test_ddram_p_write_to_write():
    dut, row_a, row_b, t = make_two_view_dut()
    start = 200
    dut.issue("WR_A", row_a, clk=start)

    delay = max(t["nBL"], t["nCCDS_WR"], t["nCCDL_WR"])
    assert not dut.probe( "WR_B", row_b, clk=start + delay - 1).ready
    assert dut.probe("WR_B", row_b, clk=start + delay).ready
    dut.issue("WR_B", row_b, clk=start + delay)


def test_ddram_p_independent_precharge_timing():
    dut, row_a, row_b, t = make_two_view_dut()
    # B has been open long enough to satisfy nRAS
    dut.issue("WR_A", row_a, clk=200)
    # B should be independently prechargeable
    assert dut.probe("PRE_B", row_b, clk=210).ready
    dut.issue("PRE_B", row_b, clk=210)
    # A must remain open
    assert dut.probe("RD_A", row_a, clk=300).row_hit
    assert not dut.probe("RD_B", row_b, clk=300).row_open


def test_ddram_p_view_replacement():
    dut, row_a, row_b, t = make_two_view_dut()
    row30 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=30, Column=0)

    # A was activated at cycle 0, B at cycle 100 
    dut.issue("PRE_A", row_a, clk=200)

    # new ACT must satisfy both nRP and nRC
    # find expected nRP boundary first -> 223
    expected = 200 + t["nRP"]
    for clk in range(expected - 2, expected + 4):
        result = dut.probe("ACT_A", row30, clk=clk)
        print(clk, result.preq, result.timing_OK, result.ready)

    # B must remain open throughout the replacement
    assert dut.probe("RD_B", row_b, clk=300).row_hit


def test_ddram_p_view_replacement():
    # replacing row in view A does not disturb B
    dut, row_a, row_b, t = make_two_view_dut()
    row30 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=30, Column=0)

    dut.issue("PRE_A", row_a, clk=200)

    for clk in range(219, 226):
        result = dut.probe("ACT_A", row30, clk=clk)
        print(
            f"clk={clk}: preq={result.preq}, "
            f"timing_OK={result.timing_OK}, ready={result.ready}"
        )

    matches = [
        c for c in ramulator.dram.DDRAM_P.timing_constraints
        if c.level == "Bank"
        and c.preceding == ["PRE_A"]
        and c.following == ["ACT_A"]
    ]

    assert len(matches) == 1
    print(matches[0])

    expected = 200 + t["nRP"]
    assert not dut.probe("ACT_A", row30, clk=expected - 1).ready
    assert dut.probe("ACT_A", row30, clk=expected).ready
    dut.issue("ACT_A", row30, clk=expected)

    assert dut.probe("RD_A", row30, clk=300).row_hit
    assert dut.probe("RD_B", row_b, clk=300).row_hit


def test_ddram_p_write_to_preab():
    dut, row_a, row_b, t = make_two_view_dut()
    dut.issue("WR_B", row_b, clk=200)
    recovery = t["nCWL"] + t["nBL"] + t["nWR"]
    expected = 200 + recovery +1

    assert not dut.probe("PREab", row_b, clk=expected - 1).ready
    assert dut.probe("PREab", row_b, clk=expected).ready
    dut.issue("PREab", row_b, clk=expected)
    assert not dut.probe("RD_A", row_a, clk=300).row_open
    assert not dut.probe("RD_B", row_b, clk=300).row_open


def test_ddram_p_write_to_presb():
    dut, row_a, row_b, t = make_two_view_dut()
    dut.issue("WR_B", row_b, clk=200)

    recovery = t["nCWL"] + t["nBL"] + t["nWR"]
    expected = 200 + recovery

    # PREsb must wait for the outstanding write
    assert not dut.probe("PREsb", row_b, clk=expected - 1).ready
    # find boundary
    for clk in range(expected, expected + 5):
        result = dut.probe("PREsb", row_b, clk=clk)
        print(clk, result.preq, result.timing_OK, result.ready)


def test_ddram_p_presb_bank_targeting():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    # two different bank groups, same bank index
    bg0_bank0_a = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    bg1_bank0_b = dut.addr_vec(Rank=0, BankGroup=1, Bank=0, Row=20, Column=0)

    # different bank index: should not be affected
    bg0_bank1_a = dut.addr_vec(Rank=0, BankGroup=0, Bank=1, Row=30, Column=0)

    dut.issue("ACT_A", bg0_bank0_a, clk=0)
    dut.issue("ACT_B", bg1_bank0_b, clk=100)
    dut.issue("ACT_A", bg0_bank1_a, clk=200)

    # all activations and minimum active times have elapsed
    dut.issue("PREsb", bg0_bank0_a, clk=1000)
    # bank index 0 is closed in both bank groups
    assert not dut.probe("RD_A", bg0_bank0_a, clk=1100).row_open
    assert not dut.probe("RD_B", bg1_bank0_b, clk=1100).row_open
    # bank index 1 remains open
    assert dut.probe("RD_A", bg0_bank1_a, clk=1100).row_hit


def test_ddr5_presb_targeting_diagnostic():
    dram = ramulator.dram.DDR5(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    bg0_bank0 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    bg1_bank0 = dut.addr_vec(Rank=0, BankGroup=1, Bank=0, Row=20, Column=0)

    dut.issue("ACT", bg0_bank0, clk=0)
    dut.issue("ACT", bg1_bank0, clk=100)
    dut.issue("PREsb", bg0_bank0, clk=1000)

    assert not dut.probe("RD", bg0_bank0, clk=1100).row_open
    assert not dut.probe("RD", bg1_bank0, clk=1100).row_open