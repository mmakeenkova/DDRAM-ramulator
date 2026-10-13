#pragma once

#include "ramulator/dram/node.h"

namespace Ramulator::DDRAM {

constexpr int CLOSED = -1;

constexpr int VIEW_A = 0;
constexpr int VIEW_B = 1;

inline bool row_hit(const DRAMNode* bank, int view, int row) {
  return bank->m_ddram_active_rows[view] == row;
}

inline bool view_open(const DRAMNode* bank, int view) {
  return bank->m_ddram_active_rows[view] != CLOSED;
}

inline void activate(DRAMNode* bank, int view, int row) {
  bank->m_ddram_active_rows[view] = row;
}

inline void precharge(DRAMNode* bank, int view) {
  bank->m_ddram_active_rows[view] = CLOSED;
}

inline void precharge_all(DRAMNode* bank) {
  precharge(bank, VIEW_A);
  precharge(bank, VIEW_B);
}

inline bool any_view_open(const DRAMNode* bank) {
  return view_open(bank, VIEW_A) ||
         view_open(bank, VIEW_B);
}

}  // namespace Ramulator::DDRAM