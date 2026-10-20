"""DDRAM-P queue-aware view placement and replacement tests."""

import pytest

import ramulator
import tests.controller_scheduling.harness as cs
from tests.controller_scheduling.GenericDDRController import test_controller_ddram_p as dual

pytestmark = [pytest.mark.controller_scheduling, pytest.mark.ddram_p]


def make_dut(policy="QueueAware"):
    return cs.ControllerUnderTest.make_generic_ddr(
        ramulator.dram.DDRAM_P(
            org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN", rank=1
        ),
        scheduler=ramulator.scheduler.FRFCFSViewAware(),
        view_selection=policy,
    )


def test_queue_aware_preserves_row_demand_from_other_rw_queue():
    dut = make_dut()
    dual.open_two_rows(dut)  # row 10 in A, row 20 in B

    # The controller remains in read mode, but the write queued for row 10 is
    # still future demand.  QueueAware should preserve A and replace idle B.
    dut.send_request("Write", dual.addr(dut, 10, column=8))
    dut.send_request("Write", dual.addr(dut, 10, column=16))
    dut.send_request("Write", dual.addr(dut, 20, column=8))
    dut.send_request("Read", dual.addr(dut, 30))
    history = dut.run_until_idle(2048)

    row_level = dut.level_names.index("Row")
    replacement = [item.command for item in history if item.addr_vec[row_level] == 30]
    assert replacement == ["PRE_B", "ACT_B", "RD_B"]
    assert any(item.command == "WR_A" for item in history)
    dual.validate_history(dut)


def test_queue_aware_reverses_victim_when_b_has_more_future_hits():
    dut = make_dut()
    dual.open_two_rows(dut)

    dut.send_request("Write", dual.addr(dut, 10, column=8))
    dut.send_request("Write", dual.addr(dut, 20, column=8))
    dut.send_request("Write", dual.addr(dut, 20, column=16))
    dut.send_request("Read", dual.addr(dut, 30))
    history = dut.run_until_idle(2048)

    row_level = dut.level_names.index("Row")
    replacement = [item.command for item in history if item.addr_vec[row_level] == 30]
    assert replacement == ["PRE_A", "ACT_A", "RD_A"]
    assert any(item.command == "WR_B" for item in history)
    dual.validate_history(dut)


def test_equal_utility_retains_deterministic_a_first_replacement():
    dut = make_dut()
    dual.open_two_rows(dut)
    dut.send_request("Read", dual.addr(dut, 30))
    dut.assert_commands(["PRE_A", "ACT_A", "RD_A"], history=dut.run_until_idle())


def test_committed_queue_aware_assignment_does_not_move():
    dut = make_dut()
    dual.open_two_rows(dut)
    dut.send_request("Write", dual.addr(dut, 10, column=8))
    dut.send_request("Read", dual.addr(dut, 30))
    dual.until_command(dut, "PRE_B")

    # Once PRE_B issues, later queue contents cannot redirect row 30 to A.
    dut.send_request("Write", dual.addr(dut, 20, column=16))
    history = dut.run_until_idle(2048)
    row_level = dut.level_names.index("Row")
    target = [item.command for item in history if item.addr_vec[row_level] == 30]
    assert target == ["ACT_B", "RD_B"]
    dual.validate_history(dut)
