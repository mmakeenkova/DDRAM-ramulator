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