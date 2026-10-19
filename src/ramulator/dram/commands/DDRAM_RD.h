#pragma once

#include "ramulator/dram/node.h"
#include "ramulator/dram/ddram/bank_state.h"
#include <stdexcept>

namespace Ramulator::Cmd {

template <class T, int View>
struct DDRAM_RD {
    static constexpr DRAMCommandMeta meta = {.is_accessing = true};
    static constexpr BankTarget bank_target = BankTarget::Single;

    // DDRAM: Reads and writes must use the view already holding the physical row.
    static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
        const int row = addr_vec[T::Level::Row];
        if (DDRAM::row_open_in_other_view(bank, View, row)) {
            throw std::logic_error("DDRAM-P: request row is open in other view");
        }

        // The requested row is already open in this view.
        if (DDRAM::row_hit(bank, View, row)) {
            return cmd;
        }

        // A different row is currently open in this view.
        if (DDRAM::view_open(bank, View)) {
            return View == DDRAM::VIEW_A
            ? T::Command::PRE_A
            : T::Command::PRE_B;
        }

        // The view is closed, so activate the requested row.
        return View == DDRAM::VIEW_A
            ? T::Command::ACT_A
            : T::Command::ACT_B;
    }

    static bool rowhit(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
        return DDRAM::row_hit(bank, View, addr_vec[T::Level::Row]);
    }

    static bool rowopen( DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
        return DDRAM::view_open(bank, View);
    }
      
};


} // namespace Ramulator::Cmd