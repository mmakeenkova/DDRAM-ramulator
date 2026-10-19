#include <array>
#include <cassert>
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
    if (command == m_precharges[DDRAM::VIEW_A]) {
      return view != DDRAM::VIEW_B;
    }
    if (command == m_precharges[DDRAM::VIEW_B]) {
      return view != DDRAM::VIEW_A;
    }
    return true;
  }

 protected:
  // DDRAM: Cache view-local command IDs once for both selection policies.
  explicit DDRAMViewSelectionBase(const DRAMDevice& device)
      : m_precharges{device.m_spec->get_command_id("PRE_A"), device.m_spec->get_command_id("PRE_B")} {
  }

 private:
  std::array<int, 2> m_precharges;
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
  explicit DDRAMViewSelection(DRAMDevice& device)
      : DDRAMViewSelectionBase(device),
        m_device(device),
        m_row_level(device.m_spec->get_level_id("Row")),
        m_reads{device.m_spec->get_command_id("RD_A"), device.m_spec->get_command_id("RD_B")},
        m_writes{device.m_spec->get_command_id("WR_A"), device.m_spec->get_command_id("WR_B")},
        m_reserved_rows(device.m_bank_nodes.size(), {DDRAM::CLOSED, DDRAM::CLOSED}) {
  }

  // DDRAM: Two-view ownership can block another queue, so owners need progress fallback.
  bool uses_reservations() const override {
    return true;
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
      // Prefer closed, unreserved views; then use A-first victim selection.
      for (int view = 0; view < 2 && req.selected_view == -1; ++view) {
        if (reserved[view] == DDRAM::CLOSED && !DDRAM::view_open(bank, view) &&
            !m_device.is_view_refresh_busy(bank_id, view) && view != req.nacked_view) {
          req.selected_view = view;
        }
      }
      for (int view = 0; view < 2 && req.selected_view == -1; ++view) {
        if (reserved[view] == DDRAM::CLOSED && !m_device.is_view_refresh_busy(bank_id, view) &&
            view != req.nacked_view) {
          req.selected_view = view;
        }
      }
      // Both paths may have been tried across successive NACKs.  Forget the
      // older hint rather than making the request permanently ineligible.
      if (req.selected_view == -1 && req.nacked_view >= 0) {
        req.nacked_view = -1;
        for (int view = 0; view < 2 && req.selected_view == -1; ++view) {
          if (reserved[view] == DDRAM::CLOSED && !m_device.is_view_refresh_busy(bank_id, view)) {
            req.selected_view = view;
          }
        }
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

  DRAMDevice& m_device;
  int m_row_level;
  std::array<int, 2> m_reads;
  std::array<int, 2> m_writes;
  std::vector<std::array<int, 2>> m_reserved_rows;
};

}  // namespace

// DDRAM: Keep the concrete policy outside the controller and scheduler code.
std::unique_ptr<IViewSelection> make_ddram_view_selection(DRAMDevice& device, bool always_a) {
  if (always_a) {
    return std::make_unique<AlwaysAViewSelection>(device);
  }
  return std::make_unique<DDRAMViewSelection>(device);
}

}  // namespace Ramulator
