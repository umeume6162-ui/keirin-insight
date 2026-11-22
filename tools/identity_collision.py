"""Detect same-name riders without merging distinct registrations."""
from collections import defaultdict
from quality_v2 import identity

def collisions(records):
    by_name=defaultdict(set)
    by_id=defaultdict(set)
    for record in records:
        name,pref,period,number=identity(record)
        by_name[name].add((number,pref,period))
        by_id[number].add((name,pref,period))
    return {
        "sameName":[{"name":name,"identities":sorted(values)} for name,values in sorted(by_name.items()) if len({v[0] for v in values})>1],
        "registrationConflicts":[{"registration":number,"identities":sorted(values)} for number,values in sorted(by_id.items()) if len(values)>1],
        "autoMergeAllowed":False
    }
