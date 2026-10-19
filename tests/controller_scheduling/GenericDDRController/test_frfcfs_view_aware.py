"""DDRAM: Row-hit protection follows the command's affected view, not the whole bank."""

import pytest

import ramulator
from tests.controller_scheduling.GenericDDRController import test_controller_ddram_p as dual
from tests.controller_scheduling.GenericDDRController import test_ddram_p_always_a as single

pytestmark = [pytest.mark.controller_scheduling, pytest.mark.ddram_p]


# DDRAM: Start with two fully aged open rows and independently validate every command.
@pytest.fixture
def dut():
    controller = dual.make_dut(scheduler=ramulator.scheduler.FRFCFSViewAware(), nRTP=2)
    dual.open_two_rows(controller)
    for _ in range(128):
        controller.tick()
    yield controller
    dual.validate_history(controller)


# DDRAM: Both rows remain hits for reads and writes, with one shared column/data path.
@pytest.mark.parametrize("operation,prefix", [("Read", "RD"), ("Write", "WR")])
def test_both_open_rows_supply_hits_in_fcfs_order(dut, operation, prefix):
    dut.reset_stats()
    for index, row in enumerate((20, 10, 20, 10)):
        dut.send_request(operation, dual.addr(dut, row, column=(index + 1) * 8))
    history = dut.run_until_idle()
    dut.assert_commands([f"{prefix}_B", f"{prefix}_A", f"{prefix}_B", f"{prefix}_A"],
                        history=history)
    # Shared bus timing still applies to alternating views in the same bank.
    for first, second in zip(history, history[1:]):
        timing = "nCCDL" if operation == "Read" else "nCCDL_WR"
        assert second.clk - first.clk >= dut.timings[timing]
    assert dut.stats()["row_hits"] == 4


# DDRAM: B hits must not prevent replacement in A during column timing stalls.
@pytest.mark.parametrize("scheduler,independent", [
    (ramulator.scheduler.FRFCFSRowHit, False),
    (ramulator.scheduler.FRFCFSViewAware, True),
])
def test_other_view_hits_do_not_block_a_replacement(scheduler, independent):
    dut = dual.make_dut(scheduler=scheduler())
    dual.open_two_rows(dut)
    for _ in range(128):
        dut.tick()
    for column in (8, 16, 24, 32):
        dut.send_request("Read", dual.addr(dut, 20, column=column))
    dut.send_request("Read", dual.addr(dut, 30))
    history = dut.run_until_idle(2048)
    pre = next(item.clk for item in history if item.command == "PRE_A")
    last_b_hit = max(item.clk for item in history if item.command == "RD_B")
    assert (pre < last_b_hit) == independent
    # The B row remains open throughout A's replacement.
    dut.send_request("Read", dual.addr(dut, 20, column=40))
    dut.assert_commands(["RD_B"], history=dut.run_until_idle())
    dual.validate_history(dut)


# DDRAM: A timing-stalled hit still protects its own view from a younger/equal-age close.
def test_a_hits_prevent_a_precharge(dut):
    dut.send_request("Read", dual.addr(dut, 30))
    for column in (8, 16, 24):
        dut.send_request("Read", dual.addr(dut, 10, column=column))
    history = dut.run_until_idle(2048)
    dut.assert_commands(["RD_A", "RD_A", "RD_A", "PRE_A", "ACT_A", "RD_A"],
                        history=history)


# DDRAM: B receives the same protection when an existing owner reserves A.
def test_b_hits_prevent_b_precharge(dut):
    dut.send_request("Read", dual.addr(dut, 30))
    dual.until_command(dut, "PRE_A")
    dut.send_request("Read", dual.addr(dut, 40))
    for column in (8, 16):
        dut.send_request("Read", dual.addr(dut, 20, column=column))
    history = dut.run_until_idle(2048)
    pre_b = next(item.clk for item in history if item.command == "PRE_B")
    row_level = dut.level_names.index("Row")
    hits = [item.clk for item in history
            if item.command == "RD_B" and item.addr_vec[row_level] == 20]
    assert len(hits) == 2
    assert max(hits) < pre_b


# DDRAM: Controller eligibility must permit the other view's PRE while an ACT waits for CAS.
@pytest.mark.parametrize("active,other", [("A", "B"), ("B", "A")])
def test_other_view_can_precharge_during_active_request(dut, active, other):
    dut.priority_send(f"PRE_{active}", dual.addr(dut, 10))
    dut.run_until_idle()
    for _ in range(128):
        dut.tick()
    dut.send_request("Read", dual.addr(dut, 30))
    act = dual.until_command(dut, f"ACT_{active}")
    dut.send_request("Read", dual.addr(dut, 40))
    history = dut.run_until_idle(2048)
    pre = next(item for item in history if item.command == f"PRE_{other}")
    terminal = next(item for item in history if item.command == f"RD_{active}")
    assert act.clk < pre.clk < terminal.clk


# DDRAM: A view-local close must still wait for that view's active request to finish.
@pytest.mark.parametrize("active", ["A", "B"])
def test_same_view_precharge_waits_for_active_request(dut, active):
    dut.priority_send(f"PRE_{active}", dual.addr(dut, 10))
    dut.run_until_idle()
    for _ in range(128):
        dut.tick()
    dut.send_request("Read", dual.addr(dut, 30))
    dual.until_command(dut, f"ACT_{active}")
    dut.priority_send(f"PRE_{active}", dual.addr(dut, 30))
    dut.assert_commands([f"RD_{active}", f"PRE_{active}"], history=dut.run_until_idle(2048))


# DDRAM: A hit in another bank cannot protect the victim view of this bank.
def test_row_hit_protection_is_scoped_to_physical_bank(dut):
    dut.send_request("Read", dual.addr(dut, 10, bank=1))
    dut.run_until_idle()
    for column in (8, 16, 24):
        dut.send_request("Read", dual.addr(dut, 10, column=column, bank=1))
    dut.send_request("Read", dual.addr(dut, 30, bank=0))
    history = dut.run_until_idle(2048)
    pre = next(item.clk for item in history if item.command == "PRE_A")
    bank_level = dut.level_names.index("Bank")
    last_hit = max(item.clk for item in history
                   if item.command == "RD_A" and item.addr_vec[bank_level] == 1)
    assert pre < last_hit


# DDRAM: Single-view operation matches the existing DDR5 row-hit scheduler exactly.
@pytest.mark.parametrize("workload", [single.test_queued_hits_and_conflicts,
                                      single.test_mixed_traffic_and_mode_switches,
                                      single.test_staggered_arrivals])
def test_always_a_matches_conventional_rowhit_scheduler(workload):
    baseline = single.cs.ControllerUnderTest.make_generic_ddr(
        ramulator.dram.DDR5(org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN", rank=2),
        scheduler=ramulator.scheduler.FRFCFSRowHit(),
    )
    alternate = single.cs.ControllerUnderTest.make_generic_ddr(
        ramulator.dram.DDRAM_P(org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN", rank=2),
        scheduler=ramulator.scheduler.FRFCFSViewAware(), view_selection="AlwaysA",
    )
    workload([baseline, alternate])
