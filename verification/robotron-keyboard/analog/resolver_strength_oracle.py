"""Raw scalar resolution for the native constructor/resolution domain.

A nibble carries a signed drive-strength endpoint. Equal nibbles are a
single definite drive; differing nibbles retain a range of possibilities.
This models native encoding semantics, not physical analogue behaviour.
"""
def scalar(a,b):
    if not 0<=a<=255 or not 0<=b<=255:raise ValueError('Invalid raw scalar')
    if not a&0x77:return b
    if not b&0x77 or a==b:return a
    ends=lambda v:(v&15,v>>4)
    definite=lambda v:len(set(ends(v)))==1
    da,db=definite(a),definite(b)
    if da and db:
        sa,sb=a&7,b&7
        if sa==sb:return sa*17|0x80
        return a if sa>sb else b
    if da or db:
        fixed,uncertain=(a,b) if da else (b,a)
        merged=[f if (f&7)>(u&7) else u for f,u in zip(ends(fixed),ends(uncertain))]
        return merged[0]|merged[1]<<4
    signed=lambda n:(n&7)*(1 if n&8 else -1)
    points=[signed(n) for v in (a,b) for n in ends(v)]
    lo,hi=min(points),max(points)
    low=abs(lo)|(8 if lo>0 else 0)
    high=abs(hi)|(8 if hi>0 else ((a&b)>>4)&8)
    result=low|high<<4
    return result if result&0x77 else 0
