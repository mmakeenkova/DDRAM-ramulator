#include "ramulator/dram/node.h"

namespace Ramulator {

namespace {

void record_timing_cause(Clk_t& ready_clk, TimingCause& primary,
                         std::vector<TimingCause>& causes, const TimingCause& cause) {
  if (cause.ready_at > ready_clk) {
    ready_clk = cause.ready_at;
    primary = cause;
    causes = {cause};
    return;
  }
  if (cause.ready_at != ready_clk) return;
  for (const auto& existing : causes) {
    if (existing.source_event_id == cause.source_event_id &&
        existing.constraint_id == cause.constraint_id && existing.level == cause.level) {
      return;
    }
  }
  causes.push_back(cause);
}

void merge_latest_causes(std::vector<TimingCause>& result,
                         const std::vector<TimingCause>& candidate) {
  if (candidate.empty()) return;
  if (result.empty() || candidate.front().ready_at > result.front().ready_at) {
    result = candidate;
    return;
  }
  if (candidate.front().ready_at < result.front().ready_at) return;
  for (const auto& cause : candidate) {
    bool duplicate = false;
    for (const auto& existing : result) {
      duplicate = duplicate ||
                  (existing.source_event_id == cause.source_event_id &&
                   existing.constraint_id == cause.constraint_id && existing.level == cause.level);
    }
    if (!duplicate) result.push_back(cause);
  }
}

}  // namespace

DRAMNode::DRAMNode(DRAMSpec* spec, DRAMNode* parent, int level, int id)
    : m_spec(spec), m_parent_node(parent), m_level(level), m_node_id(id) {
  int num_cmds = spec->command_count;
  m_cmd_ready_clk.resize(num_cmds, -1);
  m_cmd_ready_cause.resize(num_cmds);
  m_cmd_ready_causes.resize(num_cmds);
  m_cmd_history.resize(num_cmds);
  m_cmd_history_events.resize(num_cmds);
  int shared_window_group_count = 0;
  for (int cmd = 0; cmd < num_cmds; cmd++) {
    int window = 0;
    for (const auto& t : spec->timing_cons[level][cmd]) {
      window = std::max(window, t.window);
      if (t.history_group >= 0) {
        shared_window_group_count = std::max(shared_window_group_count, t.history_group + 1);
      }
    }
    if (window != 0) {
      m_cmd_history[cmd].resize(window, -1);
      m_cmd_history_events[cmd].resize(window, -1);
    } else {
      m_cmd_history[cmd].clear();
      m_cmd_history_events[cmd].clear();
    }
  }
  m_shared_window_history.resize(shared_window_group_count);
  m_shared_window_history_events.resize(shared_window_group_count);
  for (int cmd = 0; cmd < num_cmds; cmd++) {
    for (const auto& t : spec->timing_cons[level][cmd]) {
      if (t.history_group >= 0 && m_shared_window_history[t.history_group].size() < t.window) {
        m_shared_window_history[t.history_group].resize(t.window, -1);
        m_shared_window_history_events[t.history_group].resize(t.window, -1);
      }
    }
  }

  m_state = spec->init_states[m_level];

  // Recursively construct next levels
  int next_level = level + 1;
  int last_level = spec->get_level_id("Row");
  if (next_level == last_level) {
    return;
  } else {
    int next_level_size = m_spec->organization.level_sizes[next_level];
    if (next_level_size == 0) {
      return;
    } else {
      for (int i = 0; i < next_level_size; i++) {
        m_child_nodes.push_back(std::make_unique<DRAMNode>(spec, this, next_level, i));
      }
    }
  }
}

void DRAMNode::update_timing(int command, const AddrVec_t& addr_vec, Clk_t clk, int64_t event_id) {
  /************************************************
   *         Update Sibling Node Timing
   ***********************************************/
  if (m_node_id != addr_vec[m_level] && addr_vec[m_level] != -1) {
    for (const auto& t : m_spec->timing_cons[m_level][command]) {
      if (!t.sibling) {
        continue;
      }
      Clk_t future = clk + t.val;
      record_timing_cause(m_cmd_ready_clk[t.cmd], m_cmd_ready_cause[t.cmd],
                          m_cmd_ready_causes[t.cmd],
                          {future, event_id, t.constraint_id, m_level});
    }
    return;
  }

  /************************************************
   *          Update Target Node Timing
   ***********************************************/
  if (m_cmd_history[command].size()) {
    m_cmd_history[command].pop_back();
    m_cmd_history[command].push_front(clk);
    m_cmd_history_events[command].pop_back();
    m_cmd_history_events[command].push_front(event_id);
  }

  std::vector<bool> shared_window_updated(m_shared_window_history.size(), false);
  for (const auto& t : m_spec->timing_cons[m_level][command]) {
    if (t.history_group < 0 || shared_window_updated[t.history_group]) {
      continue;
    }
    auto& history = m_shared_window_history[t.history_group];
    history.pop_back();
    history.push_front(clk + m_spec->command_cycles[command] - 1);
    auto& event_history = m_shared_window_history_events[t.history_group];
    event_history.pop_back();
    event_history.push_front(event_id);
    shared_window_updated[t.history_group] = true;
  }

  for (const auto& t : m_spec->timing_cons[m_level][command]) {
    if (t.sibling) {
      continue;
    }
    Clk_t past = t.history_group >= 0
                     ? m_shared_window_history[t.history_group][t.window - 1]
                     : m_cmd_history[command][t.window - 1];
    int64_t source_event = t.history_group >= 0
                               ? m_shared_window_history_events[t.history_group][t.window - 1]
                               : m_cmd_history_events[command][t.window - 1];
    if (past < 0) {
      continue;
    }
    Clk_t future = past + t.val;
    record_timing_cause(m_cmd_ready_clk[t.cmd], m_cmd_ready_cause[t.cmd],
                        m_cmd_ready_causes[t.cmd],
                        {future, source_event, t.constraint_id, m_level});
  }

  if (m_child_nodes.empty()) {
    return;
  }

  // Skip traversal that does not have sibling timing constraints
  int child_level = m_level + 1;
  int target_child_id = addr_vec[child_level];
  bool children_have_sibling_cons = m_spec->has_sibling_cons[child_level][command];

  if (children_have_sibling_cons || target_child_id == -1) {
    for (auto& child : m_child_nodes) {
      child->update_timing(command, addr_vec, clk, event_id);
    }
  } else {
    m_child_nodes[target_child_id]->update_timing(command, addr_vec, clk, event_id);
  }
}

TimingCause DRAMNode::get_timing_cause(int command, const AddrVec_t& addr_vec) const {
  auto causes = get_timing_causes(command, addr_vec);
  return causes.empty() ? TimingCause{} : causes.front();
}

std::vector<TimingCause> DRAMNode::get_timing_causes(int command, const AddrVec_t& addr_vec) const {
  std::vector<TimingCause> result = m_cmd_ready_causes[command];
  if (m_child_nodes.empty()) {
    return result;
  }

  const int child_id = addr_vec[m_level + 1];
  if (child_id == -1) {
    for (const auto& child : m_child_nodes) {
      merge_latest_causes(result, child->get_timing_causes(command, addr_vec));
    }
  } else {
    merge_latest_causes(result, m_child_nodes[child_id]->get_timing_causes(command, addr_vec));
  }
  return result;
}

bool DRAMNode::check_timing(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  if (m_cmd_ready_clk[command] != -1 && clk < m_cmd_ready_clk[command]) {
    return false;
  }

  int child_id = addr_vec[m_level + 1];
  if (m_child_nodes.empty()) {
    return true;
  }

  if (child_id == -1) {
    bool timing_ok = true;
    for (auto& child : m_child_nodes) {
      timing_ok = timing_ok && child->check_timing(command, addr_vec, clk);
    }
    return timing_ok;
  } else {
    return m_child_nodes[child_id]->check_timing(command, addr_vec, clk);
  }
}

}  // namespace Ramulator
