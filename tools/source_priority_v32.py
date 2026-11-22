"""Rank sources by recorded category-specific performance, not fabricated estimates."""
from source_metrics_v32 import summarize

DEFAULTS={
    "identity":("KEIRIN.JP","WINTICKET","NETKEIRIN","ODDSPARK"),
    "race":("CHARILOTO","KDREAMS","KEIRIN.JP","ODDSPARK","NETKEIRIN"),
    "formation":("KDREAMS","NETKEIRIN","KEIRIN.JP"),
}
def rank_sources(records, category, min_samples=10):
    if type(min_samples) is not int or min_samples<1:
        raise ValueError("invalid sample threshold")
    default=DEFAULTS.get(category,())
    if not default:
        raise ValueError("unknown category")
    stats={r["source"]:r for r in summarize(records) if r["category"]==category}
    def key(source):
        r=stats.get(source)
        if r is None or r["attempts"]<min_samples or r["compared"]<min_samples:
            return (1,0,0,0,0,default.index(source))
        return (0,-r["matches"]/r["compared"],-r["complete"]/r["attempts"],-r["successes"]/r["attempts"],r["medianMs"] if r["medianMs"] is not None and r["timed"]>=min_samples else float("inf"),default.index(source))
    # Only reorder established candidates relative to one another; retain
    # default slots for sparsely measured sources.
    established=[s for s in default if key(s)[0]==0]
    ordered=iter(sorted(established,key=key))
    return [next(ordered) if s in established else s for s in default]
