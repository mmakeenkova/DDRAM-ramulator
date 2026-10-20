import pytest

import ramulator
from tests.device_timings.harness import DeviceUnderTest


pytestmark = [pytest.mark.device_timings, pytest.mark.ddram_o]


def make_dut(**overrides):
    dram = ramulator.dram.DDRAM_O(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
        **overrides,
    )
    return dram, DeviceUnderTest(dram)


def test_ddram_o_resolves_provisional_timings_and_accepts_overrides():
    dram, _ = make_dut()
    _, timing = dram.resolve()

    assert timing["nXACTO"] == 8
    assert timing["nMRA"] == timing["nRAS"] + timing["nRP"]
    assert timing["nCOPY"] == timing["nRAS"] + timing["nRP"] + (timing["nRP"] + 3) // 4
    assert timing["nNOT"] == timing["nCOPY"]

    overridden, _ = make_dut(nXACTO=13, nMRA=71, nCOPY=83, nNOT=79)
    _, timing = overridden.resolve()
    assert (timing["nXACTO"], timing["nMRA"], timing["nCOPY"], timing["nNOT"]) == (
        13,
        71,
        83,
        79,
    )


@pytest.mark.parametrize("name,value", [("nXACTO", 0), ("nMRA", -2), ("nCOPY", 1.5)])
def test_ddram_o_rejects_invalid_provisional_timings(name, value):
    with pytest.raises(ValueError, match=rf"{name} must be a positive integer"):
        dram = ramulator.dram.DDRAM_O(
            org_preset="DDR5_16Gb_x8",
            timing_preset="DDR5_3200AN",
            rank=1,
            **{name: value},
        )
        dram.to_config()


def test_ddram_o_views_can_open_equal_numeric_rows_independently():
    _, dut = make_dut(nXACTO=17)
    row = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)

    dut.issue("ACT_A", row, clk=0)
    dut.assert_earliest_ready_at("ACT_B", row, clk=17)
    dut.issue("ACT_B", row, clk=17)

    assert dut.probe("RD_A", row, clk=100).row_hit
    assert dut.probe("RD_B", row, clk=100).row_hit

    dut.issue("PRE_A", row, clk=100)
    assert not dut.probe("RD_A", row, clk=101).row_open
    assert dut.probe("RD_B", row, clk=101).row_hit


def test_ddram_o_cross_view_delay_is_configurable_for_act_and_mra():
    _, dut = make_dut(nXACTO=17)
    row_a = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row_b = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)

    dut.issue("ACT_A", row_a, clk=0)
    dut.assert_earliest_ready_at("MRA_B", row_b, clk=17)

    _, dut = make_dut(nXACTO=19)
    dut.issue("MRA_A", row_a, clk=0)
    dut.assert_earliest_ready_at("ACT_B", row_b, clk=19)


def test_ddram_o_mra_is_atomic_and_occupies_only_its_view():
    _, dut = make_dut(nXACTO=17, nMRA=40)
    row_a = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row_b = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)

    dut.issue("MRA_A", row_a, clk=0)

    # MRA does not create a persistent conventional row-open state.
    probe = dut.probe("RD_A", row_a, clk=1)
    assert not probe.row_open
    assert probe.preq == "ACT_A"

    dut.assert_earliest_ready_at("ACT_B", row_b, clk=17)
    dut.assert_earliest_ready_at("ACT_A", row_a, clk=40)


def test_ddram_o_mra_requests_local_precharge_when_view_is_open():
    _, dut = make_dut(nMRA=40)
    row = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)

    dut.issue("ACT_A", row, clk=0)
    assert dut.probe("MRA_A", row, clk=100).preq == "PRE_A"
    # The other view remains independently usable.
    assert dut.probe("MRA_B", row, clk=100).preq == "MRA_B"


def test_ddram_o_mra_counts_toward_shared_activation_window():
    _, dut = make_dut()
    rows = [
        dut.addr_vec(Rank=0, BankGroup=group, Bank=0, Row=10 + group, Column=0)
        for group in range(5)
    ]

    for clk, command, address in zip(
        (0, 8, 16, 24),
        ("MRA_A", "ACT_B", "MRA_A", "ACT_B"),
        rows[:4],
    ):
        dut.issue(command, address, clk=clk)

    assert not dut.probe("MRA_A", rows[4], clk=31).ready
    assert dut.probe("MRA_A", rows[4], clk=32).ready
