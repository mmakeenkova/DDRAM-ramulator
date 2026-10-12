DDRAMBankState state;

state.activate(0, 10);
state.activate(1, 20);

assert(state.is_row_hit(0, 10));
assert(state.is_row_hit(1, 20));
assert(!state.is_row_hit(0, 20));

state.precharge(0);

assert(!state.is_open(0));
assert(state.is_row_hit(1, 20));