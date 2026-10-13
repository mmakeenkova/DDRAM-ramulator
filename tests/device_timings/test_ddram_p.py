import ramulator
from tests.device_timings.harness import DeviceUnderTest

def test_ddram_p_views():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )

    dut = DeviceUnderTest(dram)

    row10 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row20 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)

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

    # clode A but not B
    dut.issue("PRE_A", row10, clk=2000)
    assert not dut.probe("RD_A", row10, clk=2001).row_open
    assert dut.probe("RD_B", row20, clk=2001).row_hit


    # open another row in view A
    dut.issue("ACT_A", row20, clk=3000)
    assert dut.probe("RD_A", row20, clk=3001).row_hit
    assert dut.probe("RD_B", row20, clk=3001).row_hit

    # PREab must close both views
    dut.issue("PREab", row20, clk=4000)
    assert not dut.probe("RD_A", row20, clk=4001).row_open
    assert not dut.probe("RD_B", row20, clk=4001).row_open