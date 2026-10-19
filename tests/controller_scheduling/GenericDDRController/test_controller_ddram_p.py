import pytest

import ramulator
import tests.controller_scheduling.harness as cs
from tests.device_timings.harness import DeviceUnderTest

pytestmark = [pytest.mark.controller_scheduling, pytest.mark.ddram_p]

SCHEDULERS = [
    ramulator.scheduler.FRFCFS,
    ramulator.scheduler.FRFCFSRowHit,
    ramulator.scheduler.FRFCFSViewAware,
]


# DDRAM: Exercise the shared preparation contract under all three schedulers.
@pytest.fixture(params=SCHEDULERS)
def dut(request):
    controller = make_dut(scheduler=request.param())
    yield controller
    validate_history(controller)


# DDRAM: Keep refresh and row closure explicit so command traces are deterministic.
def make_dut(*, scheduler=None, dram_cls=ramulator.dram.DDRAM_P, row_policy=None, **timings):
    dram = dram_cls(org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN", rank=1, **timings)
    return cs.ControllerUnderTest.make_generic_ddr(dram, scheduler=scheduler, row_policy=row_policy)


# DDRAM: Independently replay every issued command through prerequisite/timing checks.
def validate_history(dut):
    device = DeviceUnderTest(dut.dram)
    for item in dut.history:
        device.issue(item.command, item.addr_vec, clk=item.clk)


# DDRAM: Vary columns to avoid write forwarding and coalescing in command tests.
def addr(dut, row, column=0, bank=0):
    return dut.addr_vec(Rank=0, BankGroup=0, Bank=bank, Row=row, Column=column)


# DDRAM: Stop at an actual command boundary, not a guessed timing delay.
def until_command(dut, name, max_ticks=2048):
    for _ in range(max_ticks):
        for item in dut.tick():
            if item.command == name:
                return item
    raise AssertionError(f"Did not observe {name}")


# DDRAM: Open both views through ordinary requests and leave them open.
def open_two_rows(dut):
    dut.send_request("Read", addr(dut, 10))
    dut.run_until_idle()
    dut.send_request("Read", addr(dut, 20))
    dut.run_until_idle()


# DDRAM: Scheduler scans must not reserve views for requests that have not issued.
def test_queued_rows_open_both_views_and_complete(dut):
    dut.send_request("Read", addr(dut, 10))
    dut.send_request("Read", addr(dut, 20))
    history = dut.run_until_idle()
    assert sorted(item.command for item in history) == sorted(
        ["ACT_A", "ACT_B", "RD_A", "RD_B"]
    )
    acts = [item for item in history if item.command.startswith("ACT_")]
    assert acts[1].clk - acts[0].clk >= dut.dram.nXACT
    # The second activation can overlap the first view's activation-to-read wait.
    assert acts[1].clk < next(item.clk for item in history if item.command == "RD_A")
    assert dut.stats()["num_read_reqs_served"] == 2


# DDRAM: Row hits override closed-view and A-first replacement preferences.
@pytest.mark.parametrize("operation,prefix", [("Read", "RD"), ("Write", "WR")])
def test_hits_use_the_existing_view(dut, operation, prefix):
    open_two_rows(dut)
    dut.send_request(operation, addr(dut, 20, column=8))
    dut.assert_commands([f"{prefix}_B"], history=dut.run_until_idle())
    dut.send_request(operation, addr(dut, 10, column=16))
    dut.assert_commands([f"{prefix}_A"], history=dut.run_until_idle())
    # Close A explicitly: a hit in B must still win over the newly closed A.
    dut.priority_send("PRE_A", addr(dut, 10))
    dut.run_until_idle()
    dut.send_request(operation, addr(dut, 20, column=24))
    dut.assert_commands([f"{prefix}_B"], history=dut.run_until_idle())


# DDRAM: Replacement closes only the selected victim and releases its reservation.
@pytest.mark.parametrize("operation,prefix", [("Read", "RD"), ("Write", "WR")])
def test_replacement_preserves_other_view(dut, operation, prefix):
    open_two_rows(dut)
    dut.send_request(operation, addr(dut, 30))
    history = dut.run_until_idle()
    dut.assert_commands(["PRE_A", "ACT_A", f"{prefix}_A"], history=history)
    # DDRAM: Command-start timestamps account for the two-cycle following ACT.
    assert history[1].clk - history[0].clk >= dut.timings["nRP"] - 1
    assert history[2].clk - history[1].clk >= dut.timings["nRCD"]
    dut.send_request("Read", addr(dut, 20, column=8))
    dut.assert_commands(["RD_B"], history=dut.run_until_idle())
    dut.send_request("Read", addr(dut, 40))
    dut.assert_commands(["PRE_A", "ACT_A", "RD_A"], history=dut.run_until_idle())


# DDRAM: Same-row followers cannot open a reserved target in the other view.
def test_same_row_followers_wait_for_committed_owner(dut):
    open_two_rows(dut)
    dut.send_request("Read", addr(dut, 30))
    until_command(dut, "PRE_A")
    start = len(dut.history)
    dut.send_request("Read", addr(dut, 30, column=8))
    dut.send_request("Read", addr(dut, 40))
    history = dut.run_until_idle(max_ticks=2048)
    row_level = dut.level_names.index("Row")
    target = [item.command for item in history if item.addr_vec[row_level] == 30]
    assert target == ["ACT_A", "RD_A", "RD_A"]
    assert all(
        item.command != "ACT_B"
        for item in dut.history[start:]
        if item.addr_vec[row_level] == 30
    )
    assert dut.stats()["num_read_reqs_served"] == 5


# DDRAM: Commit B with PRE, then free and close A before B can activate.
@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_precharge_commits_view_even_when_other_view_becomes_free(scheduler):
    dut = make_dut(scheduler=scheduler(), nRCD=2)
    open_two_rows(dut)
    for _ in range(dut.timings["nRAS"]):
        dut.tick()
    dut.send_request("Read", addr(dut, 30))
    until_command(dut, "PRE_A")
    dut.send_request("Read", addr(dut, 40))
    until_command(dut, "PRE_B")
    # Maintenance holds both pre-activation owners while closing both views.
    dut.priority_send("REFab", addr(dut, 30))
    until_command(dut, "REFab")
    until_command(dut, "RD_A")
    # With nRCD < nXACT, A retires before B's ACT is ready. Priority PRE_A
    # closes A and holds B back; now both views are closed and A is unreserved.
    assert not any(
        item.command == "ACT_B" and item.addr_vec[dut.level_names.index("Row")] == 40
        for item in dut.history
    )
    dut.priority_send("PRE_A", addr(dut, 30))
    until_command(dut, "PRE_A")
    dut.assert_commands(["ACT_B", "RD_B"], history=dut.run_until_idle(2048))
    validate_history(dut)


# DDRAM: Maintenance may run between PRE and ACT without releasing the assignment.
@pytest.mark.parametrize(
    "maintenance,precharge",
    [("REFab", "PREab"), ("REFsb", "PREsb"), ("RFMab", "PREab"), ("RFMsb", "PREsb")],
)
def test_maintenance_after_precharge_makes_progress(dut, maintenance, precharge):
    open_two_rows(dut)
    dut.send_request("Read", addr(dut, 30))
    until_command(dut, "PRE_A")
    dut.priority_send(maintenance, addr(dut, 30))
    history = dut.run_until_idle(max_ticks=4096)
    dut.assert_commands([precharge, maintenance, "ACT_A", "RD_A"], history=history)
    # Maintenance closed B as well, so it must be activated on a subsequent access.
    dut.send_request("Read", addr(dut, 20))
    dut.assert_commands(["ACT_B", "RD_B"], history=dut.run_until_idle())


# DDRAM: Refresh must wait for an already activated owner's terminal access.
def test_maintenance_waits_for_active_request(dut):
    dut.send_request("Read", addr(dut, 10))
    until_command(dut, "ACT_A")
    dut.priority_send("REFab", addr(dut, 10))
    dut.assert_commands(["RD_A", "PREab", "REFab"], history=dut.run_until_idle(2048))


# DDRAM: A mode switch after PRE must not strand the owner behind its followers.
@pytest.mark.parametrize("owner,followers,count", [("Read", "Write", 26), ("Write", "Read", 1)])
def test_committed_owner_progresses_across_read_write_mode_switch(dut, owner, followers, count):
    open_two_rows(dut)
    dut.send_request(owner, addr(dut, 30))
    until_command(dut, "PRE_A")
    for column in range(1, count + 1):
        dut.send_request(followers, addr(dut, 30, column=column * 8))
    history = dut.run_until_idle(4096)
    assert history[0].command == "ACT_A"
    assert all(item.command in ("ACT_A", "RD_A", "WR_A") for item in history)
    assert len(history) == count + 2


# DDRAM: Both activation owners must fit in a one-bank device's active queue.
@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_refresh_protects_both_active_views_in_a_single_bank(scheduler):
    dut = make_dut(scheduler=scheduler(), bankgroup=1, bank=1)
    dut.send_request("Read", addr(dut, 10))
    dut.send_request("Read", addr(dut, 20))
    until_command(dut, "ACT_B")
    dut.priority_send("REFab", addr(dut, 10))
    dut.assert_commands(
        ["RD_A", "RD_B", "PREab", "REFab"], history=dut.run_until_idle(2048)
    )
    validate_history(dut)


# DDRAM: Reservations are indexed by physical bank, not the bank-local row ID.
def test_same_row_in_different_banks_is_independent(dut):
    dut.send_request("Read", addr(dut, 10, bank=0))
    dut.send_request("Read", addr(dut, 10, bank=1))
    history = dut.run_until_idle()
    assert [item.command for item in history].count("ACT_A") == 2
    assert [item.command for item in history].count("RD_A") == 2
    assert len(history) == 4


# DDRAM: Reject inherited single-row closure rather than corrupting dual-view state.
def test_unsupported_row_policy_is_rejected():
    with pytest.raises(RuntimeError, match="DDRAM-P currently requires the Open row policy"):
        make_dut(row_policy=ramulator.row_policy.ClosedCAP(cap=1))


# DDRAM: The default identity path preserves DDR5 command translation and completion.
@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_ddr5_identity_path(scheduler):
    dut = make_dut(dram_cls=ramulator.dram.DDR5, scheduler=scheduler())
    dut.send_request("Read", addr(dut, 10))
    dut.assert_commands(["ACT", "RD"], history=dut.run_until_idle())
    dut.send_request("Read", addr(dut, 10, column=8))
    dut.assert_commands(["RD"], history=dut.run_until_idle())
    dut.send_request("Write", addr(dut, 20))
    dut.assert_commands(["PREpb", "ACT", "WR"], history=dut.run_until_idle())
    dut.priority_send("REFab", addr(dut, 20))
    dut.assert_commands(["PREab", "REFab"], history=dut.run_until_idle(2048))


# DDRAM: DDR5 retains its existing auto-precharge policy behavior.
def test_ddr5_closedcap_still_upgrades():
    dut = make_dut(
        dram_cls=ramulator.dram.DDR5, row_policy=ramulator.row_policy.ClosedCAP(cap=1)
    )
    dut.send_request("Read", addr(dut, 10))
    dut.send_request("Read", addr(dut, 10, column=8))
    dut.assert_commands(["ACT", "RD", "RDA"], history=dut.run_until_idle())
