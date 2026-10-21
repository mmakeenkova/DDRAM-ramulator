"""DDRAM: Validate A-only DDRAM-O host integration against conventional DDR5."""

import pytest

import ramulator
import tests.controller_scheduling.harness as cs
from tests.device_timings.harness import DeviceUnderTest

pytestmark = [pytest.mark.controller_scheduling, pytest.mark.ddram_o]

NORMALIZE = {"ACT_A": "ACT", "PRE_A": "PREpb", "RD_A": "RD", "WR_A": "WR"}
SCHEDULERS = [
    ramulator.scheduler.FRFCFS,
    ramulator.scheduler.FRFCFSRowHit,
    ramulator.scheduler.FRFCFSViewAware,
]


# DDRAM: Match presets, schedulers, ranks, and arrivals for both host-mapping modes.
@pytest.fixture(params=["Auto", "AlwaysA"])
def pair(request, scheduler, preset):
    result = []
    for dram_cls in (ramulator.dram.DDR5, ramulator.dram.DDRAM_O):
        dram = dram_cls(org_preset="DDR5_16Gb_x8", timing_preset=preset, rank=2)
        result.append(cs.ControllerUnderTest.make_generic_ddr(
            dram, scheduler=scheduler(),
            view_selection=request.param if dram_cls is ramulator.dram.DDRAM_O else "Auto",
        ))
    return result


# DDRAM: Verify mapping independently of request-ranking policy.
@pytest.fixture(params=SCHEDULERS)
def scheduler(request):
    return request.param


# DDRAM: Exercise cycle rounding and inherited DDR5 timing at three data rates.
@pytest.fixture(params=["DDR5_3200AN", "DDR5_4800AN", "DDR5_6400AN"])
def preset(request):
    return request.param


# DDRAM: Address both ranks and multiple bank groups without write forwarding aliases.
def address(dut, row=10, column=0, bank=0, group=0, rank=0):
    return dut.addr_vec(Rank=rank, BankGroup=group, Bank=bank, Row=row, Column=column)


# DDRAM: Inject maintenance at an observed prerequisite boundary rather than a guessed cycle.
def until(dut, command):
    for _ in range(4096):
        if any(NORMALIZE.get(item.command, item.command) == command for item in dut.tick()):
            return
    raise AssertionError(f"Never issued {command}")


# DDRAM: Replay traces independently and compare full timing, callbacks, and statistics.
def compare(pair):
    results = []
    for dut in pair:
        dut.run_until_idle(16384)
        device = DeviceUnderTest(dut.dram)
        trace = []
        for item in dut.history:
            assert not item.command.endswith("_B")
            assert not item.command.startswith("MRA")
            device.issue(item.command, item.addr_vec, clk=item.clk)
            trace.append((item.clk, NORMALIZE.get(item.command, item.command),
                          item.addr_vec, item.type_id, item.source_id))
        if isinstance(dut.dram, ramulator.dram.DDRAM_O):
            assert any(item.command in NORMALIZE for item in dut.history)
            assert not any(item.command in NORMALIZE.values() for item in dut.history)
        completions = dut.take_completions()
        stats = dut.stats()
        assert len(completions) == stats["num_read_reqs"] + stats["num_write_reqs"]
        results.append((trace, completions, stats))
    assert results[0][0] == results[1][0], "Normalized command traces differ"
    assert results[0][1] == results[1][1], "Request completion clocks differ"
    assert results[0][2] == results[1][2], "Controller statistics, including read latency, differ"


# DDRAM: Sequential traffic must replace A even while B is free, and retain same-row hits.
@pytest.mark.parametrize("operation", ["Read", "Write"])
def test_host_hits_and_conflicts_match_ddr5(pair, operation):
    for dut in pair:
        for index, row in enumerate((10, 10, 20, 10, 20)):
            dut.send_request(operation, address(dut, row=row, column=index * 8))
            dut.run_until_idle(2048)
        assert len([item for item in dut.history if item.command in ("ACT", "ACT_A")]) == 4
    compare(pair)


# DDRAM: Row-hit arbitration must see only the legal A row buffer for queued requests.
def test_queued_hits_and_conflicts_match_ddr5(pair):
    for dut in pair:
        for index, row in enumerate((10, 20, 10, 30, 20, 10, 30, 30)):
            dut.send_request("Read", address(dut, row=row, column=index * 8))
    compare(pair)


# DDRAM: Saturate bank/rank parallelism and force write-drain transitions on distinct addresses.
def test_mixed_banks_groups_and_ranks_match_ddr5(pair):
    for dut in pair:
        for index in range(28):
            dut.send_request("Write", address(dut, row=20 + index % 2, column=index * 8,
                                              bank=index % 4, group=index % 4, rank=index % 2))
        for index in range(20):
            dut.send_request("Read", address(dut, row=40 + index % 3, column=index * 8,
                                             bank=index % 4, group=(index // 4) % 4, rank=index % 2))
            if index % 5 == 0:
                dut.tick()
    compare(pair)


# DDRAM: Maintenance before and after victim PRE must preserve progress and inherited timings.
@pytest.mark.parametrize("maintenance", ["REFab", "REFsb", "RFMab", "RFMsb"])
@pytest.mark.parametrize("stage", ["after_act", "after_pre"])
def test_maintenance_matches_ddr5(pair, maintenance, stage):
    for dut in pair:
        dut.send_request("Read", address(dut))
        if stage == "after_act":
            until(dut, "ACT")
        else:
            dut.run_until_idle(2048)
            dut.send_request("Read", address(dut, row=20))
            until(dut, "PREpb")
        dut.priority_send(maintenance, address(dut))
        dut.run_until_idle(4096)
        dut.send_request("Read", address(dut, row=30))
    compare(pair)


# DDRAM: Interchangeable-view policies would violate DDRAM-O's host layout contract.
@pytest.mark.parametrize("policy", ["TwoView", "QueueAware"])
def test_rejects_interchangeable_view_policies(policy):
    with pytest.raises(RuntimeError, match="DDRAM_O requires Auto or AlwaysA"):
        cs.ControllerUnderTest.make_generic_ddr(
            ramulator.dram.DDRAM_O(org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN"),
            view_selection=policy,
        )


# DDRAM: Reject unsupported row closure until it explicitly understands the A-only mapping.
def test_rejects_unsupported_row_policy():
    with pytest.raises(RuntimeError, match="DDRAM_O currently requires the Open row policy"):
        cs.ControllerUnderTest.make_generic_ddr(
            ramulator.dram.DDRAM_O(org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN"),
            row_policy=ramulator.row_policy.ClosedCAP(),
        )


# DDRAM: Replay each mixed trace independently across schedulers and both A-only host modes.
@pytest.fixture(params=["Auto", "AlwaysA"])
def pud_dut(request, scheduler):
    dram = ramulator.dram.DDRAM_O(
        org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN", nMRA=180)
    dut = cs.ControllerUnderTest.make_generic_ddr(
        dram, scheduler=scheduler(), view_selection=request.param)
    yield dut
    device = DeviceUnderTest(dram)
    for item in dut.history:
        device.issue(item.command, item.addr_vec, clk=item.clk)


# DDRAM: Keep required metadata explicit in production while sharing a known timing-test layout.
def send_mra(dut, row=20, bank=0, **metadata):
    arguments = dict(required_view=1, layout="BitSerial", layout_id=7, layout_version=1)
    arguments.update(metadata)
    return dut.send_pud(address(dut, row=row, bank=bank), **arguments)


# DDRAM: Issuing the leaf is not completion; idle detection must include its internal service.
def test_mra_completion_uses_service_interval(pud_dut):
    dut = pud_dut
    request_id = send_mra(dut)
    until(dut, "MRA_B")
    issued = dut.history[-1]
    assert not dut.is_idle()
    assert dut.take_completions() == []
    for _ in range(dut.timings["nMRA"] - 1):
        dut.tick()
    assert not dut.is_idle()
    assert dut.take_completions() == []
    dut.tick()
    assert dut.is_idle()
    completion, = dut.take_completions()
    assert completion["clk"] == issued.clk + dut.timings["nMRA"]
    assert completion["request_id"] == request_id
    assert (completion["selected_view"], completion["layout_id"], completion["layout_version"]) == (1, 7, 1)
    stats = dut.stats()
    assert stats["num_pud_reqs"] == stats["num_pud_reqs_served"] == 1
    assert stats["num_maintenance_reqs"] == stats["num_read_reqs"] == 0
    assert stats["read_latency"] == 0


# DDRAM: Equal numeric A/B coordinates do not create an alternate-view row hit or a prerequisite.
def test_mra_stays_on_b_and_preserves_open_a(pud_dut):
    dut = pud_dut
    dut.send_request("Read", address(dut, row=20))
    dut.run_until_idle(2048)
    dut.take_completions()
    send_mra(dut, row=20)
    dut.assert_commands(["MRA_B"], history=dut.run_until_idle(2048))
    dut.send_request("Read", address(dut, row=20, column=8))
    dut.assert_commands(["RD_A"], history=dut.run_until_idle(2048))


# DDRAM: A PRE owner retains B and its target while another primitive queues behind it.
def test_open_b_precharges_without_redirecting_to_free_a(pud_dut):
    dut = pud_dut
    dut.priority_send("ACT_B", address(dut, row=10))
    dut.run_until_idle(2048)
    first = send_mra(dut, row=20)
    until(dut, "PRE_B")
    second = send_mra(dut, row=30)
    dut.send_request("Read", address(dut, row=40))
    dut.run_until_idle(4096)
    pud = [item for item in dut.history if item.command == "MRA_B"]
    row_level = dut.level_names.index("Row")
    assert [item.addr_vec[row_level] for item in pud] == [20, 30]
    assert pud[1].clk >= pud[0].clk + dut.timings["nMRA"]
    assert not any(item.command in ("PRE_A", "MRA_A") for item in dut.history)
    completions = {item["request_id"]: item for item in dut.take_completions() if item["type_id"] == 2}
    assert set(completions) == {first, second}
    assert all(item["selected_view"] == 1 for item in completions.values())


# DDRAM: Independent A commands and read callbacks must progress during B service.
def test_a_traffic_overlaps_b_without_read_completion_blocking(pud_dut):
    dut = pud_dut
    send_mra(dut)
    until(dut, "MRA_B")
    mra = dut.history[-1]
    dut.send_request("Read", address(dut, row=10))
    dut.run_until_idle(4096)
    act = next(item for item in dut.history if item.command == "ACT_A")
    assert mra.clk + dut.timings["nXACTO"] <= act.clk < mra.clk + dut.timings["nMRA"]
    completions = dut.take_completions()
    read, = [item for item in completions if item["type_id"] == 0]
    pud, = [item for item in completions if item["type_id"] == 2]
    assert read["clk"] < pud["clk"]
    assert pud["clk"] == mra.clk + dut.timings["nMRA"]


# DDRAM: Dependencies span banks; an independent leaf may bypass an older blocked consumer.
def test_dependencies_wait_for_service_and_allow_independent_progress(pud_dut):
    dut = pud_dut
    first = send_mra(dut, bank=0)
    dependent = send_mra(dut, bank=1, dependency=first)
    send_mra(dut, bank=2)
    dut.send_request("Read", address(dut, row=30, bank=3), dependency=first)
    dut.run_until_idle(4096)
    events = {item.addr_vec[dut.level_names.index("Bank")]: item
              for item in dut.history if item.command == "MRA_B"}
    done = events[0].clk + dut.timings["nMRA"]
    assert events[2].clk < done <= events[1].clk
    assert next(item.clk for item in dut.history if item.command == "ACT_A") >= done
    completions = {item["request_id"]: item for item in dut.take_completions() if item["type_id"] == 2}
    assert completions[dependent]["clk"] == events[1].clk + dut.timings["nMRA"]


# DDRAM: Pending layout identities cannot be reinterpreted until every referencing primitive completes.
def test_layout_version_is_frozen_until_completion(pud_dut):
    dut = pud_dut
    send_mra(dut)
    until(dut, "MRA_B")
    with pytest.raises(RuntimeError, match="layout version is frozen"):
        send_mra(dut, bank=1, layout_version=2)
    dut.run_until_idle(2048)
    send_mra(dut, bank=1, layout_version=2)
    dut.run_until_idle(2048)


# DDRAM: Missing or incompatible metadata is rejected before issuing any primitive.
@pytest.mark.parametrize("metadata", [
    {"required_view": 0}, {"required_view": -1}, {"layout": "Packed"},
    {"layout": ""}, {"layout_id": -1}, {"layout_version": -1},
])
def test_rejects_incompatible_pud_metadata(pud_dut, metadata):
    with pytest.raises(RuntimeError, match="requires view B, bit-serial layout"):
        send_mra(pud_dut, **metadata)
    assert pud_dut.is_idle()
    assert pud_dut.history == []


# DDRAM: Internal-command admission cannot bypass MRA layout validation or service completion.
@pytest.mark.parametrize("command", ["MRA_A", "MRA_B"])
def test_rejects_untracked_direct_mra(pud_dut, command):
    with pytest.raises(RuntimeError, match="B-only PudMRA request path"):
        pud_dut.priority_send(command, address(pud_dut))


# DDRAM: Adding the universal type must not enable PuD on conventional or DDRAM-P devices.
@pytest.mark.parametrize("dram_cls", [ramulator.dram.DDR5, ramulator.dram.DDRAM_P])
def test_pud_requires_ddram_o(dram_cls):
    dut = cs.ControllerUnderTest.make_generic_ddr(
        dram_cls(org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN"))
    with pytest.raises(RuntimeError, match="PudMRA requests require GenericDDR with DDRAM_O"):
        send_mra(dut)


# DDRAM: Read forwarding and write coalescing must not notify consumers before their dependency.
@pytest.mark.parametrize("operation", ["Read", "Write"])
def test_dependency_cannot_bypass_completion_through_buffered_write(pud_dut, operation):
    dut = pud_dut
    producer = send_mra(dut)
    dut.send_request("Write", address(dut, row=50))
    with pytest.raises(RuntimeError, match="failed to enqueue request"):
        dut.send_request(operation, address(dut, row=50), dependency=producer)
    assert dut.take_completions() == []
    dut.run_until_idle(4096)
    completion = next(item for item in dut.take_completions() if item["type_id"] == 2)
    dut.send_request(operation, address(dut, row=50), dependency=producer)
    dut.run_until_idle(2048)
    assert dut.take_completions()[0]["clk"] >= completion["clk"]


# DDRAM: Failed admission cannot retain a token or layout reference and poison later retries.
def test_pud_queue_backpressure_does_not_freeze_rejected_layout():
    dut = cs.ControllerUnderTest.make_generic_ddr(
        ramulator.dram.DDRAM_O(org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN"),
        read_buffer_size=1)
    send_mra(dut)
    with pytest.raises(RuntimeError, match="failed to enqueue PuD request"):
        send_mra(dut, bank=1, layout_id=8)
    dut.run_until_idle(2048)
    send_mra(dut, bank=1, layout_id=8, layout_version=2)
    dut.run_until_idle(2048)
    device = DeviceUnderTest(dut.dram)
    for item in dut.history:
        device.issue(item.command, item.addr_vec, clk=item.clk)


# DDRAM: B-local decoding validates bounds before the device dereferences a bank or row target.
def test_rejects_out_of_bounds_b_target(pud_dut):
    with pytest.raises(RuntimeError, match="B-local address is out of bounds"):
        send_mra(pud_dut, row=1 << 30)
