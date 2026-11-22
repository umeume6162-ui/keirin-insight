"""Validate ranked finish sequences, including competition-ranking ties.
This is structural validation, not independent source authentication.
"""
from collections import Counter

def validate_finishes(finishes, field_size):
    if type(field_size) is not int or not 1 <= field_size <= 9:
        raise ValueError("invalid field size")
    if len(finishes) != field_size:
        raise ValueError("incomplete field")
    ranks=[]
    for f in finishes:
        if isinstance(f,str) and f in ("失格","欠場","棄権","落車","中止"):
            continue
        if not isinstance(f,str) or f not in tuple(str(i) for i in range(1,field_size+1)):
            raise ValueError("invalid finish")
        ranks.append(int(f))
    expected=1
    for rank,count in sorted(Counter(ranks).items()):
        if rank != expected:
            raise ValueError("invalid competition rank sequence")
        expected+=count
    return True
