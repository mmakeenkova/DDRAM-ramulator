"""DDRAM-P autonomous row-refresh integration tests."""

import pytest

import ramulator
import tests.controller_scheduling.harness as cs

pytestmark = [pytest.mark.controller_scheduling, pytest.mark.ddram_p]


def make_dut(mode, **kwargs):
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN", rank=1
    )
    params = dict(
        dram_managed_refresh=mode,
        dram_refresh_interval=2,
        dram_refresh_duration=4,
        dram_refresh_rows_per_region=4,
        dram_refresh_granularity=1,
        dram_refresh_ari=1,
        dram_refresh_nack_latency=1,
    )
    params.update(kwargs)
    return cs.ControllerUnderTest.make_generic_ddr(dram, **params)


def addr(dut, row, bank=0, column=0):
    return dut.addr_vec(Rank=0, BankGroup=0, Bank=bank, Row=row, Column=column)


def tick_to_first_refresh(dut):
    dut.tick()
    events = dut.tick()
    assert any(event.command.startswith("IREF_") for event in events)
    return events


@pytest.mark.parametrize("mode", ["Oracle", "Nack"])
def test_internal_refresh_is_trace_visible_and_not_a_controller_request(mode):
    dut = make_dut(mode)
    events = tick_to_first_refresh(dut)
    refreshes = [event for event in events if event.command.startswith("IREF_")]
    assert refreshes
    assert all(event.type_id == -1 and event.source_id == -1 for event in refreshes)
    stats = dut.stats()
    assert stats["num_internal_refreshes"] == len(refreshes)
    assert stats["num_maintenance_reqs"] == 0


def test_oracle_waits_for_locked_region_without_nack():
    dut = make_dut("Oracle")
    tick_to_first_refresh(dut)  # row 0, region 0 is locked through cycle 5
    dut.send_request("Read", addr(dut, row=0))
    history = dut.run_until_idle()
    act = next(event for event in history if event.command in ("ACT_A", "ACT_B"))
    assert act.clk >= 6
    assert dut.stats()["num_act_nacks"] == 0


def test_nack_retries_at_ari_until_region_unlocks():
    dut = make_dut("Nack")
    tick_to_first_refresh(dut)
    dut.send_request("Read", addr(dut, row=0))
    history = dut.run_until_idle()
    act = next(event for event in history if event.command in ("ACT_A", "ACT_B"))
    assert act.clk >= 7
    assert dut.stats()["num_act_nacks"] == 2
    assert [event.command for event in history].count("ACT_NACK") == 2


@pytest.mark.parametrize("mode", ["Oracle", "Nack"])
def test_refresh_in_one_view_allows_demand_in_another_region(mode):
    dut = make_dut(mode)
    dut.send_request("Read", addr(dut, row=8))
    first = dut.tick()
    assert any(event.command == "ACT_A" for event in first)
    refresh_cycle = dut.tick()
    bank0_refresh = [
        event for event in refresh_cycle
        if event.command.startswith("IREF_") and event.addr_vec == addr(dut, row=0)
    ]
    assert [event.command for event in bank0_refresh] == ["IREF_B"]
    history = dut.run_until_idle()
    assert any(event.command == "RD_A" for event in history)


def test_single_refresh_view_cannot_bypass_busy_view_a():
    dut = make_dut("Oracle", dram_refresh_view_count=1)
    dut.send_request("Read", addr(dut, row=8))
    first = dut.tick()
    assert any(event.command == "ACT_A" for event in first)

    refresh_cycle = dut.tick()
    bank0_refresh = [
        event for event in refresh_cycle
        if event.command.startswith("IREF_") and event.addr_vec[:4] == addr(dut, row=0)[:4]
    ]
    assert bank0_refresh == []

    history = dut.run_until_idle()
    for _ in range(32):
        history.extend(dut.tick())
        if any(
            event.command == "IREF_A" and event.addr_vec[:4] == addr(dut, row=0)[:4]
            for event in history
        ):
            break
    assert not any(event.command == "IREF_B" for event in history)
    assert any(
        event.command == "IREF_A" and event.addr_vec[:4] == addr(dut, row=0)[:4]
        for event in history
    )


@pytest.mark.parametrize("view_count", [0, 3])
def test_managed_refresh_rejects_invalid_view_count(view_count):
    with pytest.raises(RuntimeError, match="view_count"):
        make_dut("Oracle", dram_refresh_view_count=view_count)


def test_internal_refresh_relinquishes_an_idle_open_view_before_same_row_refresh():
    dut = make_dut("Oracle", dram_refresh_interval=16)
    dut.send_request("Read", addr(dut, row=0))
    dut.run_until_idle()
    target = addr(dut, row=0)
    for _ in range(64):
        events = dut.tick()
        if any(
            event.command.startswith("IREF_") and event.addr_vec[:4] == target[:4]
            for event in events
        ):
            break
    else:
        raise AssertionError("Bank 0 never began its pending internal refresh")

    # IREF implicitly relinquished the idle open row.  A later access must
    # activate it again rather than observing an illegal concurrent row hit.
    for _ in range(8):
        dut.tick()
    dut.send_request("Read", target)
    history = dut.run_until_idle()
    assert any(event.command in ("ACT_A", "ACT_B") for event in history)


@pytest.mark.parametrize("mode", ["Oracle", "Nack"])
def test_preserve_open_rows_keeps_row_open_but_blocks_access_during_refresh(mode):
    dut = make_dut(
        mode,
        dram_refresh_interval=16,
        dram_refresh_duration=4,
        dram_refresh_preserve_open_rows=True,
    )
    target = addr(dut, row=0)
    dut.send_request("Read", target)
    dut.run_until_idle()

    for _ in range(64):
        events = dut.tick()
        refresh = next(
            (
                event for event in events
                if event.command.startswith("IREF_") and event.addr_vec[:4] == target[:4]
            ),
            None,
        )
        if refresh is not None:
            break
    else:
        raise AssertionError("Bank 0 never began its pending internal refresh")

    dut.send_request("Read", target)
    history = dut.run_until_idle()
    assert not any(event.command in ("ACT_A", "ACT_B") for event in history)
    assert any(event.command in ("RD_A", "RD_B") for event in history)
    if mode == "Nack":
        assert any(event.command == "ACT_NACK" for event in history)
    else:
        assert not any(event.command == "ACT_NACK" for event in history)


def test_managed_refresh_rejects_a_controller_refresh_manager():
    # DDR5 lets AllBank initialize far enough for the controller's mutual-
    # exclusion check; the managed engine then rejects it before its own
    # DDRAM-P-only check.
    dram = ramulator.dram.DDR5(
        org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN", rank=1
    )
    with pytest.raises(RuntimeError, match="NoRefresh"):
        cs.ControllerUnderTest.make_generic_ddr(
            dram,
            dram_managed_refresh="Oracle",
            refresh_manager=ramulator.refresh_manager.AllBank(),
        )


def test_preserve_open_rows_requires_explicit_managed_refresh_mode():
    with pytest.raises(RuntimeError, match="counterfactual managed-refresh control"):
        make_dut("Disabled", dram_refresh_preserve_open_rows=True)


def test_internal_events_are_excluded_from_external_command_bus_constraints():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN", rank=1
    )
    config = dram.to_config()
    internal_ids = {
        dram.commands.index(name) for name in ("IREF_A", "IREF_B", "ACT_NACK")
    }
    for constraint in config["timing_constraints"]:
        if constraint[-1] == "command bus":
            assert internal_ids.isdisjoint(constraint[1])
            assert internal_ids.isdisjoint(constraint[2])
