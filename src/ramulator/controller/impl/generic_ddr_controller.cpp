#include "ramulator/base/base.h"
#include "ramulator/base/param.h"
#include "ramulator/controller/controller_base.h"
#include "ramulator/controller/refresh/i_refresh_manager.h"
#include "ramulator/controller/rowpolicy/i_row_policy.h"

namespace Ramulator {

class GenericDDRController : public ControllerBase {
  RAMULATOR_REGISTER_IMPLEMENTATION_DERIVED(IController, GenericDDRController, ControllerBase, "GenericDDR")

 public:
  void init() override {
    init_base();
    // DDRAM: Auto selects TwoView for DDRAM-P and pins DDRAM-O host traffic to A.
    std::string view_selection;
    RAMULATOR_PARSE_PARAM(view_selection, std::string, "view_selection").default_val("Auto");
    init_view_selection(view_selection);

    std::string managed_refresh_mode;
    int managed_refresh_interval;
    int managed_refresh_duration;
    int managed_refresh_rows_per_region;
    int managed_refresh_granularity;
    int managed_refresh_view_count;
    int managed_refresh_ari;
    int managed_refresh_nack_latency;
    int managed_refresh_max_pending;
    bool managed_refresh_preserve_open_rows;
    RAMULATOR_PARSE_PARAM(managed_refresh_mode, std::string, "dram_managed_refresh").default_val("Disabled");
    RAMULATOR_PARSE_PARAM(managed_refresh_interval, int, "dram_refresh_interval").default_val(-1);
    RAMULATOR_PARSE_PARAM(managed_refresh_duration, int, "dram_refresh_duration").default_val(-1);
    RAMULATOR_PARSE_PARAM(managed_refresh_rows_per_region, int, "dram_refresh_rows_per_region").default_val(1);
    RAMULATOR_PARSE_PARAM(managed_refresh_granularity, int, "dram_refresh_granularity").default_val(1);
    RAMULATOR_PARSE_PARAM(managed_refresh_view_count, int, "dram_refresh_view_count").default_val(2);
    RAMULATOR_PARSE_PARAM(managed_refresh_ari, int, "dram_refresh_ari").default_val(1);
    RAMULATOR_PARSE_PARAM(managed_refresh_nack_latency, int, "dram_refresh_nack_latency").default_val(1);
    RAMULATOR_PARSE_PARAM(managed_refresh_max_pending, int, "dram_refresh_max_pending").default_val(8);
    RAMULATOR_PARSE_PARAM(managed_refresh_preserve_open_rows, bool, "dram_refresh_preserve_open_rows").default_val(false);
    if (managed_refresh_preserve_open_rows &&
        (managed_refresh_mode == "Disabled" || managed_refresh_mode == "Off")) {
      throw std::runtime_error(
          "dram_refresh_preserve_open_rows is a counterfactual managed-refresh control; "
          "it requires Oracle or Nack mode");
    }
    if (managed_refresh_mode != "Disabled" && managed_refresh_mode != "Off" &&
        m_config["refresh_manager"]["impl"].as<std::string>() != "NoRefresh") {
      throw std::runtime_error("DRAM-managed refresh must be used with refresh_manager=NoRefresh");
    }
    if (managed_refresh_mode != "Disabled" && managed_refresh_mode != "Off") {
      if (managed_refresh_interval < 0) {
        managed_refresh_interval = m_device.m_spec->get_timing_value("nREFI");
      }
      if (managed_refresh_duration < 0) {
        managed_refresh_duration = m_device.m_spec->get_timing_value("nRFCsb");
      }
    }
    m_device.configure_managed_refresh(
        managed_refresh_mode,
        managed_refresh_interval,
        managed_refresh_duration,
        managed_refresh_rows_per_region,
        managed_refresh_granularity,
        managed_refresh_view_count,
        managed_refresh_ari,
        managed_refresh_nack_latency,
        managed_refresh_max_pending,
        managed_refresh_preserve_open_rows);
  }
  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
    setup_base(frontend, memory_system);
  }
  void tick() override;
};

void GenericDDRController::tick() {
  // Common bookkeeping: clk advance, req queue stats update, completed reads draining
  tick_prologue();

  // We give refresh requests high priority in the same tick
  m_refresh->tick();

  // Pre-schedule hooks
  m_rowpolicy->pre_schedule();  // e.g., CloseRow policy may inject PREpb here
  for (auto* p : m_plugins) {
    p->pre_schedule();
  }

  // Autonomous refresh advances independently of the command scheduler.  Its
  // pseudo-commands are observable by plugins, but do not occupy this cycle's
  // external command slot.
  std::vector<unsigned char> refresh_protected_views(m_device.m_bank_nodes.size(), 0);
  for (const auto& active : m_active_buffer.buffer) {
    if (active.selected_view >= 0) {
      refresh_protected_views[m_device.get_flat_bank_id(active.addr_vec)] |=
          static_cast<unsigned char>(1U << active.selected_view);
    }
  }
  m_device.tick_managed_refresh(m_clk, refresh_protected_views);
  for (const auto& event : m_device.take_internal_events()) {
    m_device.present_internal_event(event);
    Request internal(event.addr_vec, Request::Cmd, event.command);
    internal.command = event.command;
    for (auto* p : m_plugins) {
      p->on_issue(internal);
    }
    s_num_internal_refreshes++;
  }

  // Try to find a candidate request to schedule
  // Priority: active > priority > read/write
  // 1. Try to schedule from active
  Candidate cand = pick_best_ready_from(m_active_buffer, {});

  // 2. If no candidate found, try to schedule from priority
  if (!cand.valid) {
    cand = pick_priority_if();
  }

  // 3. If no candidate found, try to schedule from read/write (with write mode check)
  if (!cand.valid && m_priority_buffer.size() == 0) {
    // DDRAM: Ready B primitives share arbitration; blocked B work leaves A traffic eligible.
    cand = pick_pud_if();
  }
  if (!cand.valid && m_priority_buffer.size() == 0) {
    cand = pick_rw_if();
  }

  // We have a valid request to serve this cycle
  if (cand.valid) {
    // Rowpolicy *may* upgrade the command to AutoPrecharge version
    m_rowpolicy->try_upgrade_command(*cand.it);

    // In NACK mode an ACT is attempted on the bus, rejected by the DRAM, and
    // retried after response latency plus ARI.  No DRAM timing/state changes
    // occur for the rejected command, and a tentative view remains tentative.
    if (m_device.managed_refresh_should_nack(cand.it->command, cand.it->addr_vec)) {
      cand.it->retry_after = m_clk + m_device.managed_refresh_retry_delay();
      cand.it->act_nack_count++;
      s_num_act_nacks++;
      if (!cand.it->view_committed) {
        cand.it->nacked_view = cand.it->selected_view;
        cand.it->selected_view = -1;
      }
      const int nack_command = m_device.record_act_nack(cand.it->addr_vec, m_clk);
      Request nack(cand.it->addr_vec, Request::Cmd, nack_command);
      nack.command = nack_command;
      for (auto* p : m_plugins) {
        p->on_issue(nack);
      }
      m_rowpolicy->post_schedule();
      for (auto* p : m_plugins) {
        p->post_schedule();
      }
      return;
    }

    if (!cand.it->is_stat_updated) {
      update_request_stats(cand.it);
    }

    // Issue command to DRAM device
    m_device.issue_command(cand.it->command, cand.it->addr_vec, m_clk);
    on_request_issued(*cand.it);

    // Notify row policy and plugins of the issued command
    m_rowpolicy->on_issue(*cand.it);
    for (auto* p : m_plugins) {
      p->on_issue(*cand.it);
    }

    // Advance request
    if (cand.it->command == cand.it->final_command) {
      retire_request(cand.it, *cand.buffer);
    } else if (m_device.m_spec->command_meta[cand.it->command].is_opening) {
      promote_to_active(cand.it, *cand.buffer);
    }
  }

  // Post-schedule hooks
  m_rowpolicy->post_schedule();
  for (auto* p : m_plugins) {
    p->post_schedule();
  }
}

}  // namespace Ramulator
