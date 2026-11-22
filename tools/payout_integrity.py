"""Structural check for ordered payout combinations against confirmed ranks."""
from finish_integrity import validate_finishes
from itertools import permutations

def allowed_orders(rows, length):
    if type(length) is not int or length not in (2,3):
        raise ValueError("unsupported wager length")
    cars=[r["car"] for r in rows]
    if any(type(c) is not int or not 1<=c<=9 for c in cars) or len(set(cars))!=len(cars):
        raise ValueError("invalid cars")
    validate_finishes([r["finish"] for r in rows],len(rows))
    ranked=[(int(r["finish"]),r["car"]) for r in rows if r["finish"].isdigit()]
    if len(ranked)<length:
        return set()
    ordered=sorted(rank for rank,car in ranked)[:length]
    return {tuple(car for rank,car in order) for order in permutations(ranked,length) if [rank for rank,car in order]==ordered}

def matches_order(rows, combination):
    return tuple(combination) in allowed_orders(rows,len(combination))
