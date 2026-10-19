"""DDRAM: Compare the single-view integration against conventional DDR5."""

import random

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

NORMALIZE = {"ACT_A": "ACT", "PRE_A": "PREpb", "RD_A": "RD", "WR_A": "WR"}
COMMANDS = {"ACT", "PREpb", "RD", "WR", "PREab", "PREsb", "REFab", "REFsb", "RFMab", "RFMsb"}


# DDRAM: Exercise equivalence across representative DDR5 data rates.
@pytest.fixture(params=["DDR5_3200AN", "DDR5_4800AN", "DDR5_6400AN"])
def timing_preset(request):
    return request.param


# DDRAM: Use identical organization, timing presets, queue sizes and scheduler settings.
@pytest.fixture(params=SCHEDULERS)
def pair(request, timing_preset):
    result = []
    for dram_cls in (ramulator.dram.DDR5, ramulator.dram.DDRAM_P):
        dram = dram_cls(org_preset="DDR5_16Gb_x8", timing_preset=timing_preset, rank=2)
        result.append(cs.ControllerUnderTest.make_generic_ddr(
            dram, scheduler=request.param(),
            view_selection="AlwaysA" if dram_cls is ramulator.dram.DDRAM_P else "Auto",
        ))
    return result


# DDRAM: Identify each transaction by its full address and preserve arrival timing.
def address(dut, row=10, column=0, bank=0, group=0, rank=0):
    return dut.addr_vec(Rank=rank, BankGroup=group, Bank=bank, Row=row, Column=column)


# DDRAM: Bound waits and return the actual issued-command boundary for injection tests.
def until(dut, command):
    for _ in range(4096):
        issued = dut.tick()
        if any(NORMALIZE.get(item.command, item.command) == command for item in issued):
            return
    raise AssertionError(f"Never issued {command}")


# DDRAM: Compare exact commands, addresses, issue clocks, callbacks and all controller stats.
def compare(pair, workload):
    results = []
    for dut in pair:
        workload(dut)
        dut.run_until_idle(16384)
        device = DeviceUnderTest(dut.dram)
        trace = []
        for item in dut.history:
            assert not item.command.endswith("_B")
            device.issue(item.command, item.addr_vec, clk=item.clk)
            trace.append((item.clk, NORMALIZE.get(item.command, item.command),
                          item.addr_vec, item.type_id, item.source_id))
        if type(dut.dram) is ramulator.dram.DDRAM_P:
            assert any(item.command in NORMALIZE for item in dut.history)
            assert not any(item.command in NORMALIZE.values() for item in dut.history)
        completions = dut.take_completions()
        stats = dut.stats()
        # DDRAM: Cross-scheduler equivalence compares metrics, not the implementation name.
        stats["scheduler"] = {
            key: value for key, value in stats["scheduler"].items() if key != "impl"
        }
        assert len(completions) == stats["num_read_reqs"] + stats["num_write_reqs"]
        results.append((trace, completions, stats))
    assert results[0][0] == results[1][0], "Normalized command traces differ"
    assert results[0][1] == results[1][1], "Per-request completion clocks differ"
    assert results[0][2] == results[1][2], "Controller statistics differ"
    return results[0]


# DDRAM: Isolate read/write misses, same-row hits and alternating-row replacement.
@pytest.mark.parametrize("operation", ["Read", "Write"])
def test_misses_hits_and_conflicts(pair, operation):
    def workload(dut):
        for row in (10, 10, 20, 10, 20):
            dut.send_request(operation, address(dut, row=row))
            dut.run_until_idle(2048)
    compare(pair, workload)


# DDRAM: Queue row hits and conflicts together so the scheduler must rank them.
def test_queued_hits_and_conflicts(pair):
    def workload(dut):
        for index, row in enumerate((10, 20, 10, 30, 20, 10, 30, 30)):
            dut.send_request("Read", address(dut, row=row, column=index * 8))
    compare(pair, workload)


# DDRAM: Exercise nRRDS/nRRDL/nFAW, column sharing and rank switching under pressure.
@pytest.mark.parametrize("operation", ["Read", "Write"])
def test_banks_groups_and_ranks(pair, operation):
    def workload(dut):
        for rank in range(2):
            for group in range(4):
                for bank in range(3):
                    dut.send_request(operation, address(dut, bank=bank, group=group, rank=rank))
    compare(pair, workload)


# DDRAM: Force write-drain entry and exit while reading/writing different rows and banks.
def test_mixed_traffic_and_mode_switches(pair):
    def workload(dut):
        for index in range(28):
            dut.send_request("Write", address(dut, row=20 + index % 2,
                                              column=index * 8, bank=index % 4))
        for index in range(12):
            dut.send_request("Read", address(dut, row=40 + index % 3,
                                             column=index * 8, bank=index % 4))
        dut.run_until_idle(8192)
        dut.send_request("Read", address(dut, row=60))
    compare(pair, workload)


# DDRAM: Reproduce request arrivals across idle cycles with a fixed random seed.
def test_staggered_arrivals(pair):
    def workload(dut):
        rng = random.Random(90210)
        for index in range(20):
            dut.send_request("Read" if index % 3 else "Write",
                             address(dut, row=rng.randrange(3), column=index * 8,
                                     bank=rng.randrange(4), group=rng.randrange(2)))
            for _ in range(rng.randrange(2, 9)):
                dut.tick()
    compare(pair, workload)


# DDRAM: Maintenance must wait for active reads, close its scope and delay reactivation.
@pytest.mark.parametrize("maintenance", ["REFab", "REFsb", "RFMab", "RFMsb"])
def test_maintenance_with_open_rows(pair, maintenance):
    def workload(dut):
        dut.send_request("Read", address(dut))
        until(dut, "ACT")
        dut.priority_send(maintenance, address(dut))
        dut.run_until_idle(4096)
        dut.send_request("Read", address(dut, row=20))
        dut.send_request("Read", address(dut, row=30, group=1))
    compare(pair, workload)


# DDRAM: A refresh arriving after victim PRE must observe PRE_A-to-maintenance timing.
@pytest.mark.parametrize("maintenance", ["REFab", "REFsb", "RFMab", "RFMsb"])
def test_maintenance_between_pre_and_act(pair, maintenance):
    def workload(dut):
        dut.send_request("Write", address(dut))
        dut.run_until_idle(2048)
        dut.send_request("Read", address(dut, row=20))
        until(dut, "PREpb")
        dut.priority_send(maintenance, address(dut))
    compare(pair, workload)


# DDRAM: Explicit all-bank precharge must delay the next activation even without refresh.
def test_precharge_all_then_activate(pair):
    def workload(dut):
        dut.send_request("Read", address(dut))
        dut.run_until_idle(2048)
        dut.priority_send("PREab", address(dut))
        until(dut, "PREab")
        dut.send_request("Read", address(dut, row=20))
    compare(pair, workload)


# DDRAM: Collapse duplicate timing edges to their effective strongest constraint.
def timing_edges(dram, allowed):
    result = {}
    config = dram.to_config()
    names = type(dram).commands
    levels = list(type(dram).levels)
    for level, preceding, following, latency, *attributes in config["timing_constraints"]:
        for before in preceding:
            for after in following:
                first, second = names[before], names[after]
                if first not in allowed or second not in allowed:
                    continue
                key = (levels[level], NORMALIZE.get(first, first), NORMALIZE.get(second, second),
                       tuple(attributes))
                result[key] = max(result.get(key, 0), latency)
    return result


# DDRAM: Check every A-only timing edge, including maintenance and multi-command windows.
@pytest.mark.parametrize("preset", ["DDR5_3200AN", "DDR5_4800AN", "DDR5_6400AN"])
def test_a_only_timing_constraints_match_ddr5(preset):
    arguments = dict(org_preset="DDR5_16Gb_x8", timing_preset=preset, rank=2)
    baseline = ramulator.dram.DDR5(**arguments)
    alternate = ramulator.dram.DDRAM_P(**arguments)
    allowed = (COMMANDS - set(NORMALIZE.values())) | set(NORMALIZE)
    assert timing_edges(baseline, COMMANDS) == timing_edges(alternate, allowed)
    for single, view in (("ACT", "ACT_A"), ("RD", "RD_A"), ("WR", "WR_A"), ("PREpb", "PRE_A")):
        assert baseline.to_config()["command_cycles"][baseline.commands.index(single)] == (
            alternate.to_config()["command_cycles"][alternate.commands.index(view)]
        )


# DDRAM: Reject misspelled policies and explicit view policies on conventional devices.
@pytest.mark.parametrize("dram_cls,policy,message", [
    (ramulator.dram.DDRAM_P, "Unknown", "Unknown view_selection"),
    (ramulator.dram.DDR5, "AlwaysA", "requires DDRAM_P"),
    (ramulator.dram.DDR5, "TwoView", "requires DDRAM_P"),
])
def test_invalid_view_selection(dram_cls, policy, message):
    with pytest.raises(RuntimeError, match=message):
        cs.ControllerUnderTest.make_generic_ddr(
            dram_cls(org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN"),
            view_selection=policy,
        )


# DDRAM: Both default Auto and explicit TwoView retain the existing dual-view behavior.
@pytest.mark.parametrize("policy", ["Auto", "TwoView"])
def test_two_view_policy_remains_available(policy):
    dut = cs.ControllerUnderTest.make_generic_ddr(
        ramulator.dram.DDRAM_P(org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN"),
        view_selection=policy,
    )
    dut.send_request("Read", address(dut, row=10))
    dut.send_request("Read", address(dut, row=20))
    commands = [item.command for item in dut.run_until_idle()]
    assert sorted(commands) == sorted(["ACT_A", "ACT_B", "RD_A", "RD_B"])
