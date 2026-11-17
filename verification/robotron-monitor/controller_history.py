"""Opt-in controller experiment; not qualified for converter or full-path use."""


def experimental_model(text):
    """Replace only reset regeneration, retaining the pin contract and protection.

    The 20 ns edge and its crossing tolerance are numerical assumptions. Scaling
    tda_regularization refines both. Requires the pinned crt_schmitt code model.
    """
    old='''Breset reset_switch vss V={.5+.5*tanh((v(cx,vss)-5.7+4.4*v(reset,vss))/(.001*tda_regularization))}
Rreset_delay reset_switch reset 1000
Creset_delay reset vss {20p*tda_regularization}'''
    if text.count(old)!=1:raise ValueError('controller reset definition changed; review variant')
    return text.replace(old,'''* Experimental solver-history reset; converter acceptance remains pending.
Areset %vd(cx vss) %vd(reset vss) CRT_RESET_HISTORY
.model CRT_RESET_HISTORY crt_schmitt(low=1.3 high=5.7 edge_s={20n*tda_regularization})''')
