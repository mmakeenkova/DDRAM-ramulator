#ifndef RAMULATOR_DRAM_DEVICE_H
#define RAMULATOR_DRAM_DEVICE_H

#include <memory>
#include <string>
#include <vector>

#include "ramulator/base/config_node.h"
#include "ramulator/base/type.h"
#include "ramulator/dram/dram_spec.h"
#include "ramulator/dram/node.h"

namespace Ramulator {

/**
 * @brief    DRAM Device — owns the DRAMSpec, node tree, and flat bank array.
 *
 * Provides all device-level operations: command issue (timing + state),
 * prerequisite checks, row buffer queries. The controller delegates here
 * for anything that touches DRAM state or timing.
 *
 * All operations take Clk_t clk as a parameter — the device is stateless
 * with respect to simulation time. The controller owns the clock.
 */
class DRAMDevice {
 public:
  enum class ManagedRefreshMode { Disabled, Oracle, Nack };

  struct InternalCommandEvent {
    int command = -1;
    AddrVec_t addr_vec;
    int64_t event_id = -1;
    TimingCause timing_cause;
    std::vector<TimingCause> timing_causes;
  };

  std::unique_ptr<DRAMSpec> m_spec_owner;  // Owns the polymorphic spec
  DRAMSpec* m_spec = nullptr;              // Non-owning pointer for convenient access
  std::unique_ptr<DRAMNode> m_root;        // Hierarchical node tree (for timing)
  std::vector<DRAMNode*> m_bank_nodes;     // Flat bank view (non-owning, for state dispatch)
  int m_bank_level = -1;                   // Cached level ID for "Bank" (hot-path use)
  int64_t m_last_issue_event_id = -1;
  TimingCause m_last_issue_timing_cause;
  std::vector<TimingCause> m_last_issue_timing_causes;

  void init(std::unique_ptr<DRAMSpec> spec);
  void set_channel_id(int channel_id);

  // DDRAM-P autonomous, row-granular refresh.  Internal refresh commands are
  // emitted for observers but do not consume the controller command bus.
  void configure_managed_refresh(
      const std::string& mode,
      int interval,
      int duration,
      int rows_per_lock_region,
      int refresh_granularity,
      int refresh_view_count,
      int ari,
      int nack_latency,
      int max_pending);
  void tick_managed_refresh(Clk_t clk, const std::vector<unsigned char>& protected_views);
  std::vector<InternalCommandEvent> take_internal_events();
  void present_internal_event(const InternalCommandEvent& event);
  bool managed_refresh_oracle_allows(int command, const AddrVec_t& addr_vec) const;
  bool managed_refresh_should_nack(int command, const AddrVec_t& addr_vec) const;
  bool is_view_refresh_busy(int bank_id, int view) const;
  bool managed_refresh_enabled() const { return m_refresh_mode != ManagedRefreshMode::Disabled; }
  bool managed_refresh_is_nack() const { return m_refresh_mode == ManagedRefreshMode::Nack; }
  int managed_refresh_retry_delay() const { return m_refresh_nack_latency + m_refresh_ari; }
  int record_act_nack(const AddrVec_t& addr_vec, Clk_t clk);
  size_t managed_refresh_count() const { return m_refresh_count; }

  // Reserve a slot on the nodes for one feature's state of type T (call at setup time).
  template <typename T>
  NodeExtensionSlot<T> register_node_extension() {
    return NodeExtensionSlot<T>(m_num_node_extensions++);
  }

  // Issue a command: update timing (hierarchical) then apply state (flat bank dispatch)
  void issue_command(int command, const AddrVec_t& addr_vec, Clk_t clk);

  // Timing-only check — hierarchical (walks node tree)
  bool check_timing(int command, const AddrVec_t& addr_vec, Clk_t clk);

  // Prerequisite check — flat bank dispatch
  int get_preq_command(int command, const AddrVec_t& addr_vec, Clk_t clk);

  // Row buffer hit check — flat bank lookup (always single bank)
  bool check_rowbuffer_hit(int command, const AddrVec_t& addr_vec, Clk_t clk);

  // Row open check — flat bank lookup (always single bank)
  bool check_node_open(int command, const AddrVec_t& addr_vec, Clk_t clk);

  // Compute flat bank index from addr_vec
  int get_flat_bank_id(const AddrVec_t& addr_vec) const;

  // Check if a bank node matches an addr_vec pattern (wildcards are -1)
  static bool bank_matches(DRAMNode* bank, const AddrVec_t& addr_vec);

  // Get indices into m_bank_nodes for the target banks of a command (cold-path wrapper)
  std::vector<int> get_target_banks(int command, const AddrVec_t& addr_vec) const;

  /// Visit target bank(s) for a command with early-exit support.
  /// Visitor signature: bool(int bank_id) — return true to continue, false to stop.
  /// Returns true if all banks were visited, false if visitor short-circuited.
  template <class Visitor>
  bool for_each_target_bank_while(int command, const AddrVec_t& addr_vec, Visitor&& visitor) const {
    switch (m_spec->bank_targets[command]) {
      case BankTarget::Single:
        return visitor(get_flat_bank_id(addr_vec));

      case BankTarget::All: {
        AddrVec_t target_addr = addr_vec;

        // all banks across all bank groups in the selected rank
        if (m_spec->has_level("BankGroup")) {
          target_addr[m_spec->get_level_id("BankGroup")] = -1;
        }
        target_addr[m_bank_level] = -1;

        for (int i = 0; i < static_cast<int>(m_bank_nodes.size()); ++i) {
          if (!bank_matches(m_bank_nodes[i], target_addr)) continue;
          if (!visitor(i)) return false;
        }
        return true;
      }
      case BankTarget::SameBank: {
        const int target_bank_id = addr_vec[m_bank_level];
        AddrVec_t target_addr = addr_vec;

        // same-bank commands target the same bank index across every bank group in the selected rank
        if (m_spec->has_level("BankGroup")) {
          target_addr[m_spec->get_level_id("BankGroup")] = -1;
        }
        for (int i = 0; i < static_cast<int>(m_bank_nodes.size()); ++i) {
          if (m_bank_nodes[i]->m_node_id != target_bank_id) continue;
          if (!bank_matches(m_bank_nodes[i], target_addr)) continue;
          if (!visitor(i)) return false;
        }
        return true;
      }
    }
    return true;
  }

  /// Visit all target bank(s) for a command. Visitor signature: void(int bank_id).
  template <class Visitor>
  void for_each_target_bank(int command, const AddrVec_t& addr_vec, Visitor&& visitor) const {
    for_each_target_bank_while(command, addr_vec, [&](int bank_id) {
      visitor(bank_id);
      return true;
    });
  }

  AddrVec_t get_timing_addr(
    int command,
    const AddrVec_t& addr_vec
  ) const;

 private:
  struct ManagedBankState {
    int pending = 0;
    int next_row = 0;
    int active_view = -1;
    int active_region = -1;
    Clk_t refresh_done = -1;
    Clk_t next_credit = -1;
    std::vector<Clk_t> region_available_at;
  };

  int m_num_node_extensions = 0;
  int64_t m_next_issue_event_id = 0;
  ManagedRefreshMode m_refresh_mode = ManagedRefreshMode::Disabled;
  int m_refresh_interval = 0;
  int m_refresh_duration = 0;
  int m_refresh_rows_per_region = 1;
  int m_refresh_granularity = 1;
  int m_refresh_view_count = 2;
  int m_refresh_ari = 1;
  int m_refresh_nack_latency = 1;
  int m_refresh_max_pending = 8;
  int m_refresh_row_level = -1;
  int m_iref_commands[2] = {-1, -1};
  int m_act_commands[2] = {-1, -1};
  int m_pre_commands[2] = {-1, -1};
  int m_act_nack_command = -1;
  size_t m_refresh_count = 0;
  std::vector<ManagedBankState> m_managed_banks;
  std::vector<InternalCommandEvent> m_internal_events;

  bool managed_refresh_blocks(int command, const AddrVec_t& addr_vec) const;
  AddrVec_t bank_addr(int bank_id, int row) const;

  // Flat bank dispatch — apply action to target banks
  void apply_action(int command, const AddrVec_t& addr_vec, Clk_t clk);
};

}  // namespace Ramulator

#endif  // RAMULATOR_DRAM_DEVICE_H
