#include <vector>

#include "ramulator/controller/controller_base.h"
#include "ramulator/controller/scheduler/i_scheduler.h"

namespace Ramulator {

// DDRAM: FRFCFS-RowHit arbitration with protection scoped to the row buffer that
// a command actually closes. View selection and reservations remain controller policies.
class FRFCFSViewAwareScheduler : public IScheduler, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IScheduler, FRFCFSViewAwareScheduler, "FRFCFS-ViewAware")

  ControllerBase* m_ctrl = nullptr;
  std::vector<const Request*> m_row_hits;

  // DDRAM: Bind the controller once; this scheduler works with conventional DDR too.
  void init() override {
    m_ctrl = cast_parent<ControllerBase>();
  }

  // DDRAM: Prepare both views' candidates without committing assignments, then use
  // readiness and arrival order while preventing destruction of older/equal-age hits.
  ReqBuffer::iterator get_best_request(ReqBuffer& buffer, RequestFilterRef filter) override {
    m_row_hits.clear();
    for (auto& req : buffer.buffer) {
      if (!m_ctrl->prepare_request(req)) {
        continue;
      }
      if (m_ctrl->m_device.check_rowbuffer_hit(req.final_command, req.addr_vec, m_ctrl->m_clk)) {
        m_row_hits.push_back(&req);
      }
    }

    auto candidate = buffer.end();
    bool candidate_ready = false;
    for (auto it = buffer.begin(); it != buffer.end(); ++it) {
      if (it->command == -1 || (filter && !filter(*it)) || would_preempt_rowhit(*it)) {
        continue;
      }
      const bool ready = m_ctrl->check_timing(it->command, it->addr_vec);
      if (candidate == buffer.end() || (ready && !candidate_ready) ||
          (ready == candidate_ready && it->arrive < candidate->arrive)) {
        candidate = it;
        candidate_ready = ready;
      }
    }
    return candidate;
  }

  // DDRAM: Hits in A protect A, hits in B protect B; other banks do not interfere.
  // Match FRFCFS-RowHit's age rule and terminal-command exception for conventional DDR.
  bool would_preempt_rowhit(const Request& req) const {
    const auto& spec = *m_ctrl->m_device.m_spec;
    if (!spec.command_meta[req.command].is_closing || req.command == req.final_command ||
        spec.bank_targets[req.command] != BankTarget::Single) {
      return false;
    }
    for (const auto* hit : m_row_hits) {
      if (hit->arrive <= req.arrive && m_ctrl->command_closes_rowbuffer(req, *hit)) {
        return true;
      }
    }
    return false;
  }
};

}  // namespace Ramulator
