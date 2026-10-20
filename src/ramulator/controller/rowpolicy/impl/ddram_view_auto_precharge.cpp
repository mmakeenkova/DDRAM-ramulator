#include <array>
#include <stdexcept>
#include <string>

#include "ramulator/base/param.h"
#include "ramulator/controller/controller_base.h"
#include "ramulator/controller/rowpolicy/i_row_policy.h"
#include "ramulator/dram/ddram/bank_state.h"

namespace Ramulator {

// DDRAM-P asymmetric row-closure policy.
//
// One configured view (B by default) is treated as the transient/replacement
// view, while the other remains an ordinary open-page view. After scheduling
// selects a terminal access in the transient view, the policy converts RD/WR
// to the corresponding view-local RDA/WRA command unless enough same-bank,
// same-row requests remain buffered. This deliberately uses a conservative
// queue-presence test instead of predicting FR-FCFS's literal next winner:
// scheduling stays owned by IScheduler, view placement stays owned by
// IViewSelection, and this policy decides only whether the selected access
// should close its already-committed view.
//
// A queued request need not have a view assignment yet. If it targets the row
// currently accessed through B, DDRAM-P's same-row invariant will make it a B
// hit after the issuing request retires and releases its reservation. Thus the
// physical (bank,row) pair is the stable information on which to decide.
class DDRAMViewAutoPrechargeRowPolicy : public IRowPolicy, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(
      IRowPolicy, DDRAMViewAutoPrechargeRowPolicy, "DDRAMViewAutoPrecharge")

  ControllerBase* m_ctrl = nullptr;
  int m_target_view = DDRAM::VIEW_B;
  bool m_preserve_queued_hits = true;
  int m_min_hits_to_preserve = 1;
  std::array<int, 2> m_reads{};
  std::array<int, 2> m_writes{};
  std::array<int, 2> m_read_auto_precharges{};
  std::array<int, 2> m_write_auto_precharges{};

  void init() override {
    m_ctrl = cast_parent<ControllerBase>();
    const auto* spec = m_ctrl->m_device.m_spec;
    if (spec->standard_name != "DDRAM_P") {
      throw std::runtime_error("DDRAMViewAutoPrecharge requires DDRAM_P");
    }

    std::string target_view;
    RAMULATOR_PARSE_PARAM(target_view, std::string, "auto_precharge_view").default_val("B");
    RAMULATOR_PARSE_PARAM(m_preserve_queued_hits, bool, "preserve_queued_hits").default_val(true);
    RAMULATOR_PARSE_PARAM(m_min_hits_to_preserve, int, "min_hits_to_preserve").default_val(1);
    if (target_view == "A" || target_view == "a") {
      m_target_view = DDRAM::VIEW_A;
    } else if (target_view == "B" || target_view == "b") {
      m_target_view = DDRAM::VIEW_B;
    } else {
      throw std::runtime_error(
          "DDRAMViewAutoPrecharge auto_precharge_view must be A or B");
    }
    if (m_min_hits_to_preserve < 1) {
      throw std::runtime_error(
          "DDRAMViewAutoPrecharge min_hits_to_preserve must be at least 1");
    }

    m_reads = {spec->get_command_id("RD_A"), spec->get_command_id("RD_B")};
    m_writes = {spec->get_command_id("WR_A"), spec->get_command_id("WR_B")};
    m_read_auto_precharges = {
        spec->get_command_id("RDA_A"), spec->get_command_id("RDA_B")};
    m_write_auto_precharges = {
        spec->get_command_id("WRA_A"), spec->get_command_id("WRA_B")};
  }

  void try_upgrade_command(Request& req) override {
    if (req.selected_view != m_target_view) {
      return;
    }

    int upgraded = -1;
    if (req.command == m_reads[m_target_view]) {
      upgraded = m_read_auto_precharges[m_target_view];
    } else if (req.command == m_writes[m_target_view]) {
      upgraded = m_write_auto_precharges[m_target_view];
    } else {
      return;
    }

    if (m_preserve_queued_hits &&
        m_ctrl->count_queued_row_requests(req) >=
            static_cast<size_t>(m_min_hits_to_preserve)) {
      return;
    }

    // The scheduler proved the ordinary access ready. AP variants normally
    // have identical incoming column timing, but keep this check explicit so
    // future timing extensions cannot turn a ready access into an illegal one.
    if (!m_ctrl->check_timing(upgraded, req.addr_vec)) {
      return;
    }
    req.command = upgraded;
    req.final_command = upgraded;
  }
};

}  // namespace Ramulator
