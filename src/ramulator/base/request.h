#ifndef RAMULATOR_BASE_REQUEST_H
#define RAMULATOR_BASE_REQUEST_H

#include <functional>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "ramulator/base/type.h"

namespace Ramulator {

struct Request {
  Addr_t addr = -1;
  Addr_t intra_channel_addr = -1;  // Flat address with channel bits stripped
  AddrVec_t addr_vec{};

  // Universal built-in external request types — always Read = 0, Write = 1.
  // Additional non-negative ids may exist as metadata for future extensions.
  struct Type {
    enum : int { Read = 0, Write = 1, PudMRA = 2 };
  };

  int type_id = -1;        // Request type. -1 is the convention for internal maintenance/direct-command requests.
  int source_id = -1;      // Source identifier (e.g., which core)
  int ingress_id = -1;     // External ingress identifier (e.g., gem5 memory port)
  int64_t request_id = -1; // Controller-local stable identity used by diagnostics/traces

  int size_bytes = -1;     // Request size in bytes. Must be set explicitly by the frontend.

  int command = -1;        // Current command to issue to progress the request
  int final_command = -1;  // Terminal command needed to complete the request
  // DDRAM: Tentative until the first issued prerequisite; copied with the request.
  int selected_view = -1;
  bool view_committed = false;
  // DDRAM: Timing-only PuD leaves require explicit layout identity and a pinned view.
  enum class PudLayout { Unspecified, BitSerial };
  PudLayout pud_layout = PudLayout::Unspecified;
  int required_view = -1;
  int64_t layout_id = -1;
  int64_t layout_version = -1;
  // DDRAM: Shared tokens survive request copies and let dependents wait for service completion.
  struct PudCompletion {
    const void* controller = nullptr;
    bool complete = false;
  };
  std::shared_ptr<PudCompletion> pud_completion;
  std::shared_ptr<const PudCompletion> pud_dependency;
  // Earliest cycle at which an ACT rejected by device-managed refresh may be retried.
  Clk_t retry_after = -1;
  int act_nack_count = 0;
  // Last tentatively selected view rejected by autonomous DRAM.  TwoView may
  // try the alternate view without learning the private lock table.
  int nacked_view = -1;
  bool is_stat_updated = false;

  Clk_t arrive = -1;  // Clock cycle when the request arrives at the memory controller
  Clk_t depart = -1;  // Clock cycle when the request departs the memory controller

  std::function<void(Request&)> callback;

  // Tag type to disambiguate the internal-command constructor from the type_id one.
  struct Cmd_t {};
  static constexpr Cmd_t Cmd{};

  Request() = default;
  Request(Addr_t addr, int type);
  Request(AddrVec_t addr_vec, int type);
  Request(Addr_t addr, int type, int source_id, std::function<void(Request&)> callback);
  Request(AddrVec_t addr_vec, Cmd_t, int final_cmd);  // internal commands (refresh, row close, etc.)
};

}  // namespace Ramulator

#endif  // RAMULATOR_BASE_REQUEST_H
