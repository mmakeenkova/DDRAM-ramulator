#pragma once

#include "ramulator/dram/node.h"
#include <assert.h>

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

inline bool row_open_in_other_view(const DRAMNode* bank, int view, int row) {
  assert(view == VIEW_A || view == VIEW_B);

  const int other_view = (view == VIEW_A) ? VIEW_B : VIEW_A;
  return row_hit(bank, other_view, row);
}

inline void activate(DRAMNode* bank, int view, int row) {
  assert(view == VIEW_A || view == VIEW_B);
  assert(!view_open(bank, view));
  // View conflict: a row can only be open in ONE view
  assert(!row_open_in_other_view(bank, view, row));
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