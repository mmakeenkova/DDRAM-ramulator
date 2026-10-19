#ifndef RAMULATOR_CONTROLLER_VIEW_SELECTION_I_VIEW_SELECTION_H
#define RAMULATOR_CONTROLLER_VIEW_SELECTION_I_VIEW_SELECTION_H

#include <memory>

#include "ramulator/base/request.h"
#include "ramulator/dram/device.h"

namespace Ramulator {

// DDRAM: View selection is independent of request ranking and row closure.
// Preparation may update a tentative assignment, but only issue reserves a view.
class IViewSelection {
 public:
  // DDRAM: Allow policies to be destroyed through their controller-owned interface.
  virtual ~IViewSelection() = default;
  // DDRAM: Exclusive policies need owner-progress fallback across read/write queues.
  virtual bool uses_reservations() const = 0;
  // DDRAM: Report whether a closing command affects a selected view; unknown views are conservative.
  virtual bool closes_view(int command, int view) const = 0;
  // DDRAM: Set the effective final command; return false when reservations block it.
  virtual bool prepare(Request& req) const = 0;
  // DDRAM: Commit the selected view after its first command successfully issues.
  virtual void on_issue(Request& req) = 0;
  // DDRAM: Release the reservation after the terminal command issues.
  virtual void on_retire(const Request& req) = 0;
};

// DDRAM: Construct the deterministic policy, optionally restricting data requests to A.
std::unique_ptr<IViewSelection> make_ddram_view_selection(DRAMDevice& device, bool always_a = false);

}  // namespace Ramulator

#endif
