#pragma once

#include "ramulator/dram/node.h"
#include "ramulator/dram/ddram/bank_state.h"

namespace Ramulator::Cmd {
template <class T, int View>

struct DDRAM_PRE {
    static constexpr DRAMCommandMeta meta = {.is_closing = true};
    static constexpr BankTarget bank_target = BankTarget::Single;

    static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec,Clk_t clk) {
        DDRAM::precharge(bank, View);

        // the bank is closed only if BOTH views are closed
        bank->m_state =
            (!DDRAM::view_open(bank, DDRAM::VIEW_A) &&
            !DDRAM::view_open(bank, DDRAM::VIEW_B)) ? T::State::Closed : T::State::Opened;
    }


    //static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    //    return cmd; 
    //}

};


} // namespace Ramulator::Cmd