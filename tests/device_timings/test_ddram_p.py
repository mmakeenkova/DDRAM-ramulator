import ramulator
from tests.device_timings.harness import DeviceUnderTest
import pytest

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