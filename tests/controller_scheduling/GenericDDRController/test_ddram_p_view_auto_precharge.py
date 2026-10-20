"""DDRAM-P asymmetric, queue-aware view auto-precharge tests."""

import pytest

import ramulator
import tests.controller_scheduling.harness as cs
from tests.controller_scheduling.GenericDDRController import test_controller_ddram_p as dual

pytestmark = [pytest.mark.controller_scheduling, pytest.mark.ddram_p]


def make_dut(**policy_kwargs):
    return cs.ControllerUnderTest.make_generic_ddr(
        ramulator.dram.DDRAM_P(
            org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN", rank=1
        ),
        scheduler=ramulator.scheduler.FRFCFSViewAware(),
        row_policy=ramulator.row_policy.DDRAMViewAutoPrecharge(**policy_kwargs),
        view_selection="TwoView",
    )


def test_view_b_is_transient_while_view_a_remains_open():
    dut = make_dut()

    dut.send_request("Read", dual.addr(dut, 10))
    dut.assert_commands(["ACT_A", "RD_A"], history=dut.run_until_idle())

    dut.send_request("Read", dual.addr(dut, 20))
    first_b = dut.run_until_idle()
    dut.assert_commands(["ACT_B", "RDA_B"], history=first_b)

    # B's auto-precharge neither closes nor converts an access through A.
    dut.send_request("Read", dual.addr(dut, 10, column=8))
    dut.assert_commands(["RD_A"], history=dut.run_until_idle())

    dut.send_request("Read", dual.addr(dut, 30))
    second_b = dut.run_until_idle()
    dut.assert_commands(["ACT_B", "RDA_B"], history=second_b)
    assert second_b[0].clk - first_b[-1].clk >= dut.timing("nRTP") + dut.timing("nRP")
    dual.validate_history(dut)


def test_queued_read_hit_is_preserved_until_last_access():
    dut = make_dut()
    dut.send_request("Read", dual.addr(dut, 10))  # occupies stable A
    dut.run_until_idle()

    dut.send_request("Read", dual.addr(dut, 20))
    dut.send_request("Read", dual.addr(dut, 20, column=8))
    history = dut.run_until_idle()

    dut.assert_commands(["ACT_B", "RD_B", "RDA_B"], history=history)
    dual.validate_history(dut)


def test_hit_in_other_rw_queue_is_also_preserved():
    dut = make_dut()
    dut.send_request("Read", dual.addr(dut, 10))
    dut.run_until_idle()

    # Read mode serves the read first, but the write queue still protects B.
    dut.send_request("Write", dual.addr(dut, 20, column=8))
    dut.send_request("Read", dual.addr(dut, 20))
    history = dut.run_until_idle()

    dut.assert_commands(["ACT_B", "RD_B", "WRA_B"], history=history)
    dual.validate_history(dut)


def test_preservation_can_be_disabled_for_always_transient_view():
    dut = make_dut(preserve_queued_hits=False)
    dut.send_request("Read", dual.addr(dut, 10))
    dut.run_until_idle()

    dut.send_request("Read", dual.addr(dut, 20))
    dut.send_request("Read", dual.addr(dut, 20, column=8))
    history = dut.run_until_idle(4096)

    dut.assert_commands(["ACT_B", "RDA_B", "ACT_B", "RDA_B"], history=history)
    dual.validate_history(dut)


def test_target_view_a_is_supported_symmetrically():
    dut = make_dut(auto_precharge_view="A")
    dut.send_request("Read", dual.addr(dut, 10))
    dut.assert_commands(["ACT_A", "RDA_A"], history=dut.run_until_idle())
    dual.validate_history(dut)


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"auto_precharge_view": "invalid"}, "must be A or B"),
        ({"min_hits_to_preserve": 0}, "must be at least 1"),
    ],
)
def test_invalid_policy_parameters_are_rejected(kwargs, message):
    with pytest.raises(RuntimeError, match=message):
        make_dut(**kwargs)


def test_policy_is_rejected_for_conventional_ddr5():
    with pytest.raises(RuntimeError, match="requires DDRAM_P"):
        cs.ControllerUnderTest.make_generic_ddr(
            ramulator.dram.DDR5(
                org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN", rank=1
            ),
            row_policy=ramulator.row_policy.DDRAMViewAutoPrecharge(),
        )
