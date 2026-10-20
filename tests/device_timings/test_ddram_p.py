import ramulator
from tests.device_timings.harness import DeviceUnderTest
import pytest

pytestmark = [pytest.mark.device_timings, pytest.mark.ddram_p]

# helper
def make_two_view_dut():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)
    row_a = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row_b = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)

    dut.issue("ACT_A", row_a, clk=0)
    dut.issue("ACT_B", row_b, clk=100)
    timings = dict(zip(dram.timing_params, dram.to_config()["timing"]))
    return dut, row_a, row_b, timings

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
    # DDRAM: A command naming the other view is an invalid assignment.
    with pytest.raises(RuntimeError, match="other view"):
        dut.probe("RD_B", row10, clk=1)

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


@pytest.mark.parametrize(
    "view,auto_command,other_view",
    [("A", "RDA_A", "B"), ("B", "RDA_B", "A")],
)
def test_ddram_p_read_auto_precharge_closes_only_issuing_view(
    view, auto_command, other_view
):
    dut, row_a, row_b, timings = make_two_view_dut()
    rows = {"A": row_a, "B": row_b}
    issue_clk = 200

    assert dut.probe(auto_command, rows[view], clk=issue_clk).row_hit
    dut.issue(auto_command, rows[view], clk=issue_clk)

    assert not dut.probe(f"RD_{view}", rows[view], clk=issue_clk + 1).row_open
    assert dut.probe(f"RD_{other_view}", rows[other_view], clk=issue_clk + 1).row_hit

    next_row = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=30, Column=0)
    ready_clk = issue_clk + timings["nRTP"] + timings["nRP"]
    assert not dut.probe(f"ACT_{view}", next_row, clk=ready_clk - 1).ready
    assert dut.probe(f"ACT_{view}", next_row, clk=ready_clk).ready


@pytest.mark.parametrize(
    "view,auto_command,other_view",
    [("A", "WRA_A", "B"), ("B", "WRA_B", "A")],
)
def test_ddram_p_write_auto_precharge_observes_recovery(
    view, auto_command, other_view
):
    dut, row_a, row_b, timings = make_two_view_dut()
    rows = {"A": row_a, "B": row_b}
    issue_clk = 200

    assert dut.probe(auto_command, rows[view], clk=issue_clk).row_hit
    dut.issue(auto_command, rows[view], clk=issue_clk)

    assert not dut.probe(f"WR_{view}", rows[view], clk=issue_clk + 1).row_open
    assert dut.probe(f"RD_{other_view}", rows[other_view], clk=issue_clk + 1).row_hit

    next_row = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=30, Column=0)
    ready_clk = (
        issue_clk
        + timings["nCWL"]
        + timings["nBL"]
        + timings["nWR"]
        + timings["nRP"]
    )
    assert not dut.probe(f"ACT_{view}", next_row, clk=ready_clk - 1).ready
    assert dut.probe(f"ACT_{view}", next_row, clk=ready_clk).ready


@pytest.mark.parametrize(
    "auto_command,recovery",
    [
        ("RDA_B", lambda timing: timing["nRTP"] + timing["nRP"]),
        (
            "WRA_B",
            lambda timing: timing["nCWL"]
            + timing["nBL"]
            + timing["nWR"]
            + timing["nRP"],
        ),
    ],
)
def test_ddram_p_auto_precharge_completes_before_maintenance(auto_command, recovery):
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)
    row = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    timings = dict(zip(dram.timing_params, dram.to_config()["timing"]))
    issue_clk = 100

    dut.issue("ACT_B", row, clk=0)
    dut.issue(auto_command, row, clk=issue_clk)
    # RDA/WRA occupy two command-bus cycles while REFsb occupies one, so the
    # generated timing edge adds one cycle to the nominal JEDEC interval.
    ready_clk = issue_clk + recovery(timings) + 1

    assert dut.probe("REFsb", row, clk=ready_clk - 1).preq == "REFsb"
    assert not dut.probe("REFsb", row, clk=ready_clk - 1).ready
    assert dut.probe("REFsb", row, clk=ready_clk).ready


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


def test_ddram_p_shared_activation_constraints():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )

    constraints = dram.timing_constraints

    expected_acts = {"ACT", "ACT_A", "ACT_B"}

    for level, latency in [
        ("Rank", "nRRDS"),
        ("BankGroup", "nRRDL"),
    ]:
        matches = [
            c for c in constraints
            if c.level == level
            and c.latency == latency
            and expected_acts.issubset(c.preceding)
            and expected_acts.issubset(c.following)
        ]
        assert len(matches) == 1

    faw = [
        c for c in constraints
        if c.level == "Rank"
        and c.latency == "nFAW"
        and c.window == 4
        and c.shared_window
    ]

    assert len(faw) == 1
    assert expected_acts.issubset(faw[0].preceding)
    assert expected_acts.issubset(faw[0].following)


def test_ddram_p_nrrds():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    row_bg0 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row_bg1 = dut.addr_vec(Rank=0, BankGroup=1, Bank=0, Row=20, Column=0)

    dut.issue("ACT_A", row_bg0, clk=0)

    nrrds = 8
    assert not dut.probe("ACT_B", row_bg1, clk=nrrds - 1).ready
    assert dut.probe("ACT_B", row_bg1, clk=nrrds).ready



def test_ddram_p_nrrdl():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    row_bank0 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row_bank1 = dut.addr_vec(Rank=0, BankGroup=0, Bank=1, Row=20, Column=0)

    dut.issue("ACT_A", row_bank0, clk=0)

    nrrdl = 8
    assert not dut.probe("ACT_B", row_bank1, clk=nrrdl - 1).ready
    assert dut.probe("ACT_B", row_bank1, clk=nrrdl).ready

def test_ddram_p_nfaw():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    rows = [
        dut.addr_vec(
            Rank=0,
            BankGroup=bg,
            Bank=0,
            Row=10 + bg,
            Column=0,
        )
        for bg in range(5)
    ]

    # four activations, alternating views
    for clk, command, addr in zip(
        [0, 8, 16, 24],
        ["ACT_A", "ACT_B", "ACT_A", "ACT_B"],
        rows[:4],
    ):
        dut.issue(command, addr, clk=clk)

    # tFAW for fifth activation
    assert not dut.probe("ACT_A", rows[4], clk=31).ready
    assert dut.probe("ACT_A", rows[4], clk=32).ready


def test_ddram_p_shared_column_constraints():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )

    constraints = dram.timing_constraints

    def find_constraint(level, latency, preceding, following):
        return any(
            c.level == level
            and c.latency == latency
            and set(preceding).issubset(c.preceding)
            and set(following).issubset(c.following)
            for c in constraints
        )

    assert find_constraint(
        "Channel", "nBL",
        ["RD_A", "RD_B"],
        ["RD_A", "RD_B"],
    )

    assert find_constraint(
        "Rank", "nRTW",
        ["RD_A", "RD_B"],
        ["WR_A", "WR_B"],
    )

    assert find_constraint(
        "Bank", "nCCDL",
        ["RD_A", "RD_B"],
        ["RD_A", "RD_B"],
    )

    assert find_constraint(
        "Bank", "nCWL + nBL + nWTRL",
        ["WR_A", "WR_B"],
        ["RD_A", "RD_B"],
    )


def test_ddram_p_read_to_read_timing():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    row10 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row20 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)

    # same bank
    dut.issue("ACT_A", row10, clk=0)
    dut.issue("ACT_B", row20, clk=100)

    assert dut.probe("RD_A", row10, clk=200).row_hit
    assert dut.probe("RD_B", row20, clk=200).row_hit

    dut.issue("RD_A", row10, clk=200)

    # find the earliest legal read through view B
    # it's 8 cycles btw -> view independence + shared column timings
    # this should be >= max (nBL, nCCDS, nCCDL)
    # nBL (channel, data bus occupancy), ncCDS (rank, column-to-column spacing)
    # nCCDL (bank, column-to-column spacing) -> shared column path for both views
    for clk in range(201, 221):
        result = dut.probe("RD_B", row20, clk=clk)

        print(
            f"clk={clk}: "
            f"preq={result.preq}, "
            f"timing_OK={result.timing_OK}, "
            f"ready={result.ready}"
        )
    config = dram.to_config()
    timings = dict(zip(dram.timing_params, config["timing"]))
    for name in ["nBL", "nCCDS", "nCCDL"]:
        print(f"{name} = {timings[name]}")


def test_ddram_p_read_to_read_timing2():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    row10 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    row20 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)

    dut.issue("ACT_A", row10, clk=0)
    dut.issue("ACT_B", row20, clk=100)

    assert dut.probe("RD_A", row10, clk=200).row_hit
    assert dut.probe("RD_B", row20, clk=200).row_hit

    dut.issue("RD_A", row10, clk=200)

    assert not dut.probe("RD_B", row20, clk=207).ready
    assert dut.probe("RD_B", row20, clk=208).ready

    dut.issue("RD_B", row20, clk=208)
    assert dut.probe("RD_A", row10, clk=300).row_hit
    assert dut.probe("RD_B", row20, clk=300).row_hit


def test_ddram_p_read_to_write_turnaround():
    dut, row_a, row_b, t = make_two_view_dut()
    start = 200

    dut.issue("RD_A", row_a, clk=start)
    # shared external data bus
    expected = start + t["nRTW"]
    assert not dut.probe("WR_B", row_b, clk=expected - 1).ready
    assert dut.probe("WR_B", row_b, clk=expected).ready

    dut.issue("WR_B", row_b, clk=expected)
    # don't close view
    assert dut.probe("RD_A", row_a, clk=300).row_hit
    assert dut.probe("RD_B", row_b, clk=300).row_hit


def test_ddram_p_write_to_read_turnaround():
    dut, row_a, row_b, t = make_two_view_dut()
    start = 200

    dut.issue("WR_A", row_a, clk=start)

    rank_delay = t["nCWL"] + t["nBL"] + t["nWTRS"]
    bank_delay = t["nCWL"] + t["nBL"] + t["nWTRL"]

    expected_delay = max(rank_delay, bank_delay)
    expected = start + expected_delay
    assert not dut.probe("RD_B", row_b, clk=expected - 1).ready
    assert dut.probe("RD_B", row_b, clk=expected).ready

    dut.issue("RD_B", row_b, clk=expected)
    assert dut.probe("RD_A", row_a, clk=300).row_hit
    assert dut.probe("RD_B", row_b, clk=300).row_hit


def test_ddram_p_write_to_precharge():
    dut, row_a, row_b, t = make_two_view_dut()
    start = 200
    dut.issue("WR_A", row_a, clk=start)

    # DDR5 write recovery 
    recovery = t["nCWL"] + t["nBL"] + t["nWR"]
    expected = start + recovery

    first_ready = expected + 1  # matches observed DDR5
    assert not dut.probe("PRE_A", row_a, clk=first_ready - 1).ready
    assert dut.probe("PRE_A", row_a, clk=first_ready).ready
    dut.issue("PRE_A", row_a, clk=first_ready)  

    assert not dut.probe("RD_A", row_a, clk=300).row_open
    assert dut.probe("RD_B", row_b, clk=300).row_hit
    dut.issue("RD_B", row_b, clk=300)


def test_ddram_p_read_to_precharge():
    dut, row_a, row_b, t = make_two_view_dut()
    start = 200
    dut.issue("RD_A", row_a, clk=start)
    expected = start + t["nRTP"]

    first_ready = expected + 1  # matches observed DDR5
    assert not dut.probe("PRE_A", row_a, clk=first_ready - 1).ready
    assert dut.probe("PRE_A", row_a, clk=first_ready).ready
    dut.issue("PRE_A", row_a, clk=first_ready)
    assert dut.probe("RD_B", row_b, clk=300).row_hit

def test_ddram_p_write_to_write():
    dut, row_a, row_b, t = make_two_view_dut()
    start = 200
    dut.issue("WR_A", row_a, clk=start)

    delay = max(t["nBL"], t["nCCDS_WR"], t["nCCDL_WR"])
    assert not dut.probe( "WR_B", row_b, clk=start + delay - 1).ready
    assert dut.probe("WR_B", row_b, clk=start + delay).ready
    dut.issue("WR_B", row_b, clk=start + delay)


def test_ddram_p_independent_precharge_timing():
    dut, row_a, row_b, t = make_two_view_dut()
    # B has been open long enough to satisfy nRAS
    dut.issue("WR_A", row_a, clk=200)
    # B should be independently prechargeable
    assert dut.probe("PRE_B", row_b, clk=210).ready
    dut.issue("PRE_B", row_b, clk=210)
    # A must remain open
    assert dut.probe("RD_A", row_a, clk=300).row_hit
    assert not dut.probe("RD_B", row_b, clk=300).row_open


def test_ddram_p_view_replacement():
    dut, row_a, row_b, t = make_two_view_dut()
    row30 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=30, Column=0)

    # A was activated at cycle 0, B at cycle 100 
    dut.issue("PRE_A", row_a, clk=200)

    # new ACT must satisfy both nRP and nRC
    # find expected nRP boundary first -> 223
    expected = 200 + t["nRP"]
    for clk in range(expected - 2, expected + 4):
        result = dut.probe("ACT_A", row30, clk=clk)
        print(clk, result.preq, result.timing_OK, result.ready)

    # B must remain open throughout the replacement
    assert dut.probe("RD_B", row_b, clk=300).row_hit


def test_ddram_p_view_replacement():
    # replacing row in view A does not disturb B
    dut, row_a, row_b, t = make_two_view_dut()
    row30 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=30, Column=0)

    dut.issue("PRE_A", row_a, clk=200)

    for clk in range(219, 226):
        result = dut.probe("ACT_A", row30, clk=clk)
        print(
            f"clk={clk}: preq={result.preq}, "
            f"timing_OK={result.timing_OK}, ready={result.ready}"
        )

    matches = [
        c for c in ramulator.dram.DDRAM_P.timing_constraints
        if c.level == "Bank"
        and c.preceding == ["PRE_A"]
        and c.following == ["ACT_A"]
    ]

    assert len(matches) == 1
    print(matches[0])

    expected = 200 + t["nRP"] -1
    assert not dut.probe("ACT_A", row30, clk=expected - 1).ready
    assert dut.probe("ACT_A", row30, clk=expected).ready
    dut.issue("ACT_A", row30, clk=expected)

    assert dut.probe("RD_A", row30, clk=300).row_hit
    assert dut.probe("RD_B", row_b, clk=300).row_hit


def test_ddram_p_write_to_preab():
    dut, row_a, row_b, t = make_two_view_dut()
    dut.issue("WR_B", row_b, clk=200)
    recovery = t["nCWL"] + t["nBL"] + t["nWR"]
    expected = 200 + recovery +1

    assert not dut.probe("PREab", row_b, clk=expected - 1).ready
    assert dut.probe("PREab", row_b, clk=expected).ready
    dut.issue("PREab", row_b, clk=expected)
    assert not dut.probe("RD_A", row_a, clk=300).row_open
    assert not dut.probe("RD_B", row_b, clk=300).row_open


def test_ddram_p_write_to_presb():
    dut, row_a, row_b, t = make_two_view_dut()
    dut.issue("WR_B", row_b, clk=200)

    recovery = t["nCWL"] + t["nBL"] + t["nWR"]
    expected = 200 + recovery

    # PREsb must wait for the outstanding write
    assert not dut.probe("PREsb", row_b, clk=expected - 1).ready
    # find boundary
    for clk in range(expected, expected + 5):
        result = dut.probe("PREsb", row_b, clk=clk)
        print(clk, result.preq, result.timing_OK, result.ready)


def test_ddram_p_presb_bank_targeting():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    # two different bank groups, same bank index
    bg0_bank0_a = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    bg1_bank0_b = dut.addr_vec(Rank=0, BankGroup=1, Bank=0, Row=20, Column=0)

    # different bank index: should not be affected
    bg0_bank1_a = dut.addr_vec(Rank=0, BankGroup=0, Bank=1, Row=30, Column=0)

    dut.issue("ACT_A", bg0_bank0_a, clk=0)
    dut.issue("ACT_B", bg1_bank0_b, clk=100)
    dut.issue("ACT_A", bg0_bank1_a, clk=200)

    # all activations and minimum active times have elapsed
    dut.issue("PREsb", bg0_bank0_a, clk=1000)
    # bank index 0 is closed in both bank groups
    assert not dut.probe("RD_A", bg0_bank0_a, clk=1100).row_open
    assert not dut.probe("RD_B", bg1_bank0_b, clk=1100).row_open
    # bank index 1 remains open
    assert dut.probe("RD_A", bg0_bank1_a, clk=1100).row_hit


def test_ddr5_presb_targeting_diagnostic():
    dram = ramulator.dram.DDR5(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    bg0_bank0 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    bg1_bank0 = dut.addr_vec(Rank=0, BankGroup=1, Bank=0, Row=20, Column=0)

    dut.issue("ACT", bg0_bank0, clk=0)
    dut.issue("ACT", bg1_bank0, clk=100)
    dut.issue("PREsb", bg0_bank0, clk=1000)

    assert not dut.probe("RD", bg0_bank0, clk=1100).row_open
    assert not dut.probe("RD", bg1_bank0, clk=1100).row_open



def test_ddram_p_refresh_to_activate():
    dut, row_a, row_b, t = make_two_view_dut()

    # close both views
    dut.issue("PREab", row_a, clk=200)

    # allow precharge recovery
    dut.issue("REFab", row_a, clk=300)
    new_row = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=30, Column=0)

    # find REFab -> ACT_A recovery boundary
    expected = 300 + t["nRFC"]
    for clk in range(expected - 2, expected + 3):
        p = dut.probe("ACT_A", new_row, clk=clk)
        print(clk, p.preq, p.timing_OK, p.ready)


def test_ddram_p_refresh_activation_constraints():
    constraints = ramulator.dram.DDRAM_P.timing_constraints

    for view in ("ACT_A", "ACT_B"):
        matches = [
            c for c in constraints
            if "REFab" in c.preceding
            and view in c.following
        ]
        assert matches, f"Missing REFab -> {view}"


def test_ddram_p_refresh_constraint_diagnostic():
    print("\nDDR5 refresh-related constraints:")
    for c in ramulator.dram.DDR5.timing_constraints:
        if "REFab" in c.preceding or "REFab" in c.following:
            print(c)

    print("\nDDRAM-P refresh-related constraints:")
    for c in ramulator.dram.DDRAM_P.timing_constraints:
        if "REFab" in c.preceding or "REFab" in c.following:
            print(c)



### parametrized tests  ###
@pytest.mark.parametrize(
    "maintenance,precharge",
    [
        ("REFab", "PREab"),
        ("RFMab", "PREab"),
        ("REFsb", "PREsb"),
        ("RFMsb", "PREsb"),
    ],
)
def test_ddram_p_maintenance_prerequisites(maintenance, precharge):
    dut, row_a, row_b, _ = make_two_view_dut()

    # Both A and B are open.
    p = dut.probe(maintenance, row_a, clk=200)
    assert p.preq == precharge
    assert not p.ready

    # Close only A. B must still block maintenance.
    dut.issue("PRE_A", row_a, clk=200)

    p = dut.probe(maintenance, row_a, clk=250)
    assert p.preq == precharge
    assert not p.ready

    # Close B as well.
    dut.issue("PRE_B", row_b, clk=250)

    # Prerequisite should now be satisfied.
    p = dut.probe(maintenance, row_a, clk=300)
    assert p.preq == maintenance


@pytest.mark.parametrize("maintenance", ["REFsb", "RFMsb"])
def test_ddram_p_same_bank_maintenance_prerequisite(maintenance):
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    bg0_bank0 = dut.addr_vec(
        Rank=0, BankGroup=0, Bank=0, Row=10, Column=0
    )
    bg1_bank0 = dut.addr_vec(
        Rank=0, BankGroup=1, Bank=0, Row=20, Column=0
    )

    # Leave the addressed bank closed.
    # Open another bank in the same-bank set.
    dut.issue("ACT_B", bg1_bank0, clk=0)

    p = dut.probe(maintenance, bg0_bank0, clk=200)

    assert p.preq == "PREsb"
    assert not p.ready

    # Close the bank in the other bank group.
    dut.issue("PRE_B", bg1_bank0, clk=200)

    p = dut.probe(maintenance, bg0_bank0, clk=300)
    assert p.preq == maintenance



def test_ddram_p_presb_cross_bankgroup_write_recovery():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    bg0 = dut.addr_vec(
        Rank=0, BankGroup=0, Bank=0, Row=10, Column=0
    )
    bg1 = dut.addr_vec(
        Rank=0, BankGroup=1, Bank=0, Row=20, Column=0
    )

    # Only BG1/Bank0 is active.
    dut.issue("ACT_B", bg1, clk=0)
    dut.issue("WR_B", bg1, clk=200)

    # PREsb is addressed to BG0, but also targets BG1.
    # BG1's write recovery must prevent premature precharge.
    assert not dut.probe("PREsb", bg0, clk=210).ready


def test_ddram_p_preab_bank_targeting():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)
    bg0_bank0 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    bg1_bank1 = dut.addr_vec(Rank=0, BankGroup=1, Bank=1, Row=20, Column=0)

    dut.issue("ACT_A", bg0_bank0, clk=0)
    dut.issue("ACT_B", bg1_bank1, clk=100)
    dut.issue("PREab", bg0_bank0, clk=1000)

    assert not dut.probe("RD_A", bg0_bank0, clk=1100).row_open

    assert not dut.probe("RD_B", bg1_bank1, clk=1100).row_open


def test_ddram_p_preab_cross_bank_write_recovery():
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8",
        timing_preset="DDR5_3200AN",
        rank=1,
    )
    dut = DeviceUnderTest(dram)

    bg0_bank0 = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    bg1_bank1 = dut.addr_vec(Rank=0, BankGroup=1, Bank=1, Row=20, Column=0)

    dut.issue("ACT_B", bg1_bank1, clk=0)
    dut.issue("WR_B", bg1_bank1, clk=200)

    # PREab is addressed through a different bank
    assert not dut.probe("PREab", bg0_bank0, clk=210).ready


# DDRAM: The physical-row invariant is symmetric and applies before any PRE/ACT.
@pytest.mark.parametrize("source,target", [("A", "B"), ("B", "A")])
@pytest.mark.parametrize("target_occupied", [False, True])
@pytest.mark.parametrize("operation", ["ACT", "RD", "WR"])
def test_ddram_p_rejects_same_row_in_other_view(source, target, target_occupied, operation):
    dram = ramulator.dram.DDRAM_P(
        org_preset="DDR5_16Gb_x8", timing_preset="DDR5_3200AN", rank=1
    )
    dut = DeviceUnderTest(dram)
    row = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    other = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=0)
    dut.issue(f"ACT_{source}", row, clk=0)
    if target_occupied:
        dut.issue(f"ACT_{target}", other, clk=100)

    with pytest.raises(RuntimeError, match="other view"):
        dut.probe(f"{operation}_{target}", row, clk=1000)
    with pytest.raises(RuntimeError, match="other view"):
        dut.issue(f"{operation}_{target}", row, clk=1000)

    assert dut.probe(f"RD_{source}", row, clk=1001).row_hit
    if target_occupied:
        assert dut.probe(f"RD_{target}", other, clk=1001).row_hit
        dut.issue(f"PRE_{target}", other, clk=1100)
    else:
        assert not dut.probe(f"RD_{target}", other, clk=1001).row_open

    # Once the source is closed, the same physical row may move to the other view.
    dut.issue(f"PRE_{source}", row, clk=1200)
    dut.issue(f"ACT_{target}", row, clk=1400)
    assert dut.probe(f"RD_{target}", row, clk=1500).row_hit
    assert not dut.probe(f"RD_{source}", other, clk=1500).row_open
