#include <array>
#include <cassert>
#include <limits>
#include <unordered_map>
#include <vector>

#include "ramulator/controller/view_selection/i_view_selection.h"
#include "ramulator/dram/ddram/bank_state.h"

namespace Ramulator {
namespace {

// DDRAM: Share command-to-view scope information without exposing command names to schedulers.
class DDRAMViewSelectionBase : public IViewSelection {
 public:
  // DDRAM: View-local precharges close only their own view; bank-wide closes affect both.
  bool closes_view(int command, int view) const override {
    if (command == m_precharges[DDRAM::VIEW_A] ||
        command == m_read_auto_precharges[DDRAM::VIEW_A] ||
        command == m_write_auto_precharges[DDRAM::VIEW_A]) {
      return view != DDRAM::VIEW_B;
    }
    if (command == m_precharges[DDRAM::VIEW_B] ||
        command == m_read_auto_precharges[DDRAM::VIEW_B] ||
        command == m_write_auto_precharges[DDRAM::VIEW_B]) {
      return view != DDRAM::VIEW_A;
    }
    return true;
  }

 protected:
  // DDRAM: Cache view-local command IDs once for both selection policies.
  explicit DDRAMViewSelectionBase(const DRAMDevice& device)
      : m_precharges{device.m_spec->get_command_id("PRE_A"), device.m_spec->get_command_id("PRE_B")},
        m_read_auto_precharges{
            device.m_spec->get_command_id("RDA_A"), device.m_spec->get_command_id("RDA_B")},
        m_write_auto_precharges{
            device.m_spec->get_command_id("WRA_A"), device.m_spec->get_command_id("WRA_B")} {
  }

 private:
  std::array<int, 2> m_precharges;
  std::array<int, 2> m_read_auto_precharges;
  std::array<int, 2> m_write_auto_precharges;
};

// DDRAM: Fixed placement needs no exclusive reservation: all requests use A,
// so conventional DDR5 arbitration can continue even between PRE and ACT.
class AlwaysAViewSelection final : public DDRAMViewSelectionBase {
 public:
  // DDRAM: Cache the terminal commands without adding device state or timing rules.
  explicit AlwaysAViewSelection(const DRAMDevice& device)
      : DDRAMViewSelectionBase(device),
        m_read(device.m_spec->get_command_id("RD_A")),
        m_write(device.m_spec->get_command_id("WR_A")) {
  }

  // DDRAM: Fixed placement cannot block another request through view ownership.
  bool uses_reservations() const override {
    return false;
  }

  // DDRAM: Preserve explicit internal commands and map every data request to A.
  bool prepare(Request& req) const override {
    if (req.type_id == Request::Type::Read || req.type_id == Request::Type::Write) {
      req.selected_view = DDRAM::VIEW_A;
      req.final_command = req.type_id == Request::Type::Read ? m_read : m_write;
    }
    return true;
  }

  // DDRAM: Record commitment on actual issue; subsequent preparation still uses A.
  void on_issue(Request& req) override {
    if (req.selected_view == DDRAM::VIEW_A) {
      req.view_committed = true;
    }
  }

  // DDRAM: Fixed placement has no exclusive reservation to release.
  void on_retire(const Request&) override {
  }

 private:
  int m_read;
  int m_write;
};

class DDRAMViewSelection final : public DDRAMViewSelectionBase {
 public:
  // DDRAM: Cache command IDs once; each reservation stores its owner's target row.
  explicit DDRAMViewSelection(DRAMDevice& device, bool queue_aware)
      : DDRAMViewSelectionBase(device),
        m_device(device),
        m_row_level(device.m_spec->get_level_id("Row")),
        m_reads{device.m_spec->get_command_id("RD_A"), device.m_spec->get_command_id("RD_B")},
        m_writes{device.m_spec->get_command_id("WR_A"), device.m_spec->get_command_id("WR_B")},
        m_reserved_rows(device.m_bank_nodes.size(), {DDRAM::CLOSED, DDRAM::CLOSED}),
        m_queue_aware(queue_aware),
        m_row_demand(device.m_bank_nodes.size()) {
  }

  // DDRAM: Two-view ownership can block another queue, so owners need progress fallback.
  bool uses_reservations() const override {
    return true;
  }

  bool uses_queue_state() const override {
    return m_queue_aware;
  }

  // DDRAM: Build a stable snapshot once per controller cycle.  In particular,
  // prepare() must not inspect and mutate queues request-by-request: doing so
  // would make a tentative assignment depend on scheduler traversal order.
  void update_queue_state(const std::vector<const Request*>& requests) override {
    if (!m_queue_aware) {
      return;
    }
    for (auto& bank : m_row_demand) {
      bank.clear();
    }
    for (const auto* req : requests) {
      if (!is_data_request(*req)) {
        continue;
      }
      const int bank_id = m_device.get_flat_bank_id(req->addr_vec);
      const int row = req->addr_vec[m_row_level];
      ++m_row_demand[bank_id][row];
    }
  }

  // DDRAM: Reconsider tentative assignments, but preserve an issued request's view.
  // No reservation or replacement state changes during scheduler scans.
  bool prepare(Request& req) const override {
    if (!is_data_request(req)) {
      return true;
    }
    const int bank_id = m_device.get_flat_bank_id(req.addr_vec);
    const int row = req.addr_vec[m_row_level];
    const auto* bank = m_device.m_bank_nodes[bank_id];
    const auto& reserved = m_reserved_rows[bank_id];

    if (!req.view_committed) {
      req.selected_view = -1;
      // A reserved target row may not be opened in the other view. Followers wait.
      if (reserved[0] == row || reserved[1] == row) {
        return false;
      }

      // A physical row hit must use that view, even if the other view is free.
      for (int view = 0; view < 2; ++view) {
        if (DDRAM::row_hit(bank, view, row)) {
          if (m_device.is_view_refresh_busy(bank_id, view)) {
            return false;
          }
          if (reserved[view] != DDRAM::CLOSED) {
            return false;
          }
          req.selected_view = view;
          break;
        }
      }
      // Prefer closed, unreserved views before considering any replacement.
      for (int view = 0; view < 2 && req.selected_view == -1; ++view) {
        if (reserved[view] == DDRAM::CLOSED && !DDRAM::view_open(bank, view) &&
            !m_device.is_view_refresh_busy(bank_id, view) && view != req.nacked_view) {
          req.selected_view = view;
        }
      }
      if (req.selected_view == -1) {
        req.selected_view = choose_victim(bank_id, bank, reserved, req.nacked_view);
      }
      // Both paths may have been tried across successive NACKs.  Forget the
      // older hint rather than making the request permanently ineligible.
      if (req.selected_view == -1 && req.nacked_view >= 0) {
        req.nacked_view = -1;
        req.selected_view = choose_victim(bank_id, bank, reserved, -1);
      }
      if (req.selected_view == -1) {
        return false;
      }
    } else {
      assert(req.selected_view >= 0 && req.selected_view < 2);
      assert(reserved[req.selected_view] == row);
    }

    req.final_command = req.type_id == Request::Type::Read ? m_reads[req.selected_view] : m_writes[req.selected_view];
    return true;
  }

  // DDRAM: Reserve on actual issue, including PRE, before the request can be copied.
  void on_issue(Request& req) override {
    if (!is_data_request(req) || req.view_committed) {
      return;
    }
    assert(req.selected_view >= 0 && req.selected_view < 2);
    auto& reserved = m_reserved_rows[m_device.get_flat_bank_id(req.addr_vec)];
    const int row = req.addr_vec[m_row_level];
    assert(reserved[req.selected_view] == DDRAM::CLOSED);
    assert(reserved[1 - req.selected_view] != row);
    reserved[req.selected_view] = row;
    req.view_committed = true;
  }

  // DDRAM: Exclusive ownership lets a copied Request release its original slot.
  void on_retire(const Request& req) override {
    if (!is_data_request(req) || !req.view_committed) {
      return;
    }
    auto& reserved = m_reserved_rows[m_device.get_flat_bank_id(req.addr_vec)];
    assert(reserved[req.selected_view] == req.addr_vec[m_row_level]);
    reserved[req.selected_view] = DDRAM::CLOSED;
  }

 private:
  // DDRAM: Internal maintenance/direct commands retain their explicit command IDs.
  static bool is_data_request(const Request& req) {
    return req.type_id == Request::Type::Read || req.type_id == Request::Type::Write;
  }

  size_t queued_demand(int bank_id, int row) const {
    const auto found = m_row_demand[bank_id].find(row);
    return found == m_row_demand[bank_id].end() ? 0 : found->second;
  }

  // DDRAM QueueAware scheduling strategy:
  //
  // The scheduler still decides *which request* is oldest/ready and protects
  // older row hits.  This policy decides only *where a selected miss should
  // go*.  Once both views are open, replacing a row discards the opportunity
  // for every queued access to that row to become a row hit.  QueueAware
  // therefore assigns each open row a preservation utility equal to the
  // number of demand requests for (physical bank, row) in the controller's
  // read and write queues, and evicts the eligible view with the lower value.
  // Equal values deliberately choose A, making results deterministic and
  // retaining TwoView's historical A-first behavior when the queue provides
  // no preference.
  //
  // Reservations, autonomous-refresh occupancy, NACK hints, existing hits,
  // and closed views are handled before this comparison.  A tentative choice
  // may be recomputed from the next cycle's snapshot, but on_issue() commits
  // and reserves it as soon as its first prerequisite issues.  Consequently a
  // changing queue can improve an unstarted placement but can never redirect
  // an in-flight PRE/ACT sequence to the other view.
  int choose_victim(
      int bank_id,
      const DRAMNode* bank,
      const std::array<int, 2>& reserved,
      int excluded_view) const {
    int victim = -1;
    size_t victim_utility = std::numeric_limits<size_t>::max();
    for (int view = 0; view < 2; ++view) {
      if (reserved[view] != DDRAM::CLOSED || m_device.is_view_refresh_busy(bank_id, view) ||
          view == excluded_view) {
        continue;
      }
      // A cleared NACK hint can make a previously excluded closed view eligible
      // here; it remains preferable to replacing either open row.
      if (!DDRAM::view_open(bank, view)) {
        return view;
      }
      if (!m_queue_aware) {
        return view;
      }
      const size_t utility = queued_demand(bank_id, bank->m_ddram_active_rows[view]);
      if (victim == -1 || utility < victim_utility) {
        victim = view;
        victim_utility = utility;
      }
    }
    return victim;
  }

  DRAMDevice& m_device;
  int m_row_level;
  std::array<int, 2> m_reads;
  std::array<int, 2> m_writes;
  std::vector<std::array<int, 2>> m_reserved_rows;
  bool m_queue_aware;
  std::vector<std::unordered_map<int, size_t>> m_row_demand;
};

}  // namespace

// DDRAM: Keep the concrete policy outside the controller and scheduler code.
std::unique_ptr<IViewSelection> make_ddram_view_selection(DRAMDevice& device, const std::string& policy) {
  if (policy == "AlwaysA") {
    return std::make_unique<AlwaysAViewSelection>(device);
  }
  return std::make_unique<DDRAMViewSelection>(device, policy == "QueueAware");
}

}  // namespace Ramulator
